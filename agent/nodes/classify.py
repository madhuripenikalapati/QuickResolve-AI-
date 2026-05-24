"""Intent classification node."""

import json
import re
from agent.llm_client import chat_with_rotation, get_classify_model
from agent.prompts.classify import CLASSIFY_PROMPT
from agent.state import AgentState
from tools.catalog import CATALOG_COLORS, CATALOG_CATEGORIES

VALID_INTENTS = {"product_search", "policy_question", "place_order", "order_support", "general", "unclear"}
_SIZE_PATTERN = re.compile(r'^(XS|S|M|L|XL|XXL|FREE\s*SIZE)$', re.IGNORECASE)
_POLICY_PATTERN = re.compile(
    r'\b(cod available|cash on delivery available|refund policy|return policy|exchange policy|'
    r'cancellation policy|shipping time|delivery time|kab tak|kitne din|how many days|'
    r'is cod|cod par|cod milega|cod hoga|return mil|refund milega|'
    r'what is your (return|refund|exchange|cancellation|shipping|delivery)|'
    r'do you (accept|allow|have|offer) (return|exchange|refund|gift wrap|wrap)|'
    r'gift wrap|gift wrapping)\b',
    re.IGNORECASE
)
_HINDI_BROWSE_PATTERNS = ["dikhao", "dikhaiye", "dikha", "batao", "kuch acha", "kuch accha",
                           "kuch sundar", "kuch dikhao", "collection dikhao", "products dikhao"]

_COLOR_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(c) for c in sorted(CATALOG_COLORS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)
_BROWSE_INTENT_WORDS = {"show", "want", "looking for", "need", "find", "search"}
_BROWSE_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in _BROWSE_INTENT_WORDS | CATALOG_CATEGORIES) + r')\b',
    re.IGNORECASE
)


_CONFIRM_WORDS = {"yes", "yeah", "yep", "yup", "ok", "okay", "sure", "go ahead",
                  "confirm", "proceed", "place it", "order it", "done", "fine", "haan", "theek hai"}
_ORDER_PHRASES = ("place the order", "place order", "order it", "order karo", "order kar do",
                  "book it", "book karo", "confirm order", "yes order")
_SIZE_IN_MSG = re.compile(r'\b(XS|S|M|L|XL|XXL|FREE\s*SIZE)\b', re.IGNORECASE)
_ADDRESS_PATTERN = re.compile(r'\b\d{6}\b|road|street|nagar|colony|sector|flat|house|apartment|lane|floor', re.IGNORECASE)


def _fast_classify(message: str, session: dict):
    """Rule-based pre-classifier for unambiguous cases — skips LLM call."""
    msg = message.strip()
    msg_lower = msg.lower().rstrip("!. ")
    last_shown = session.get("last_shown_products", [])
    active_product = session.get("active_product")

    # 6-digit pincode = Indian delivery address — always place_order in this context
    if re.search(r'\b\d{6}\b', msg) and not re.search(r'\b(order|ORD)-?\d{6}\b', msg, re.IGNORECASE):
        return "place_order"

    # Explicit order phrases — use word boundaries to avoid "order karo" matching inside "order karoon"
    if any(re.search(rf'\b{re.escape(phrase)}\b', msg_lower) for phrase in _ORDER_PHRASES):
        return "place_order"

    # "order L" / "order XL" / "book M" etc. with a size
    if re.search(r'\b(order|book)\s+(xs|s|m|l|xl|xxl|free\s*size)\b', msg_lower):
        return "place_order"

    # "order [color/product]" with products in context — standalone order verb
    # Exclude "my order", "order status", "where is order" which are order_support
    if re.search(r'\border\b', msg_lower) and (last_shown or active_product):
        if not re.search(r'\b(my order|order status|order id|where is|track|cancel)\b', msg_lower):
            return "place_order"

    # Standalone payment method with active ordering context → always place_order
    # Catches "UPI", "COD", "Card" after a failed payment or mid-order clarification
    _PAYMENT_WORDS = {"upi", "cod", "card", "gpay", "phonepay", "cash", "credit card", "debit card"}
    if msg_lower.strip() in _PAYMENT_WORDS and (active_product or session.get("pending_clarification")):
        return "place_order"

    # Confirmation words — infer intent from what the agent last asked
    if msg_lower in _CONFIRM_WORDS:
        recent = session.get("recent_messages", [])
        if recent:
            last_agent = recent[-1].get("agent", "").lower()
            if any(kw in last_agent for kw in ("place order", "proceed", "purchase", "confirm your order", "would you like to order")):
                return "place_order"
            if any(kw in last_agent for kw in ("size", "which size", "what size")):
                return "product_search"
            if any(kw in last_agent for kw in ("refund", "return", "cancel", "exchange")):
                return "order_support"
        if active_product:
            return "place_order"

    # Address, size, or payment provided while a clarification was pending → continue ordering
    if session.get("pending_clarification"):
        if _ADDRESS_PATTERN.search(msg):
            return "place_order"
        if _SIZE_IN_MSG.search(msg):
            return "place_order"
        msg_lower_full = msg.lower()
        if any(kw in msg_lower_full for kw in ("cod", "cash", "upi", "gpay", "card", "credit", "debit")):
            return "place_order"

    # Name reply when agent asked for it — route back to ordering flow
    if active_product and len(msg.split()) <= 4 and re.match(r'^[a-zA-Z\s]+$', msg):
        _recent = session.get("recent_messages", [])
        if _recent:
            _last_agent = _recent[-1].get("agent", "").lower()
            if "your name" in _last_agent:
                return "place_order"

    # Size mentioned in a short message while products are in context
    if _SIZE_IN_MSG.search(msg) and (last_shown or active_product) and len(msg.split()) <= 6:
        return "product_search"

    # Bare size token while products are in context → size query on existing results
    if _SIZE_PATTERN.match(msg) and (last_shown or active_product):
        return "product_search"

    # Order-ID pattern
    if re.search(r'\bORD-\d+\b', msg, re.IGNORECASE):
        return "order_support"

    # Policy keywords — must check BEFORE order_support so "return policy" / "can I exchange?" aren't misrouted
    if _POLICY_PATTERN.search(msg):
        return "policy_question"
    # "can I exchange/return X?" with no active order → policy enquiry, not order action
    if re.search(r'\bcan\s+i\s+(exchange|return|get\s+a?\s*refund)\b', msg_lower) and not session.get("active_order_id"):
        return "policy_question"

    # Post-order action words — always order_support regardless of product context
    if re.search(r'\b(refund|return|exchange|cancel|cancellation|where is my order|track my order)\b', msg_lower):
        return "order_support"

    # Ordinal product selection while products are in context: "first one", "option 2"
    if last_shown and re.search(
        r'\b(first|second|third|1st|2nd|3rd)\b|\b(?:option|number|item)\s*[123]\b', msg_lower
    ):
        return "product_search"

    # Hindi/Hinglish product browse requests
    if any(p in msg_lower for p in _HINDI_BROWSE_PATTERNS):
        return "product_search"

    # Color/fabric/category mention + browse intent → product search
    if _COLOR_PATTERN.search(msg) and _BROWSE_PATTERN.search(msg):
        return "product_search"

    # Pure category mention (e.g. "kurtas", "sarees", "lehengas")
    if _BROWSE_PATTERN.search(msg) and len(msg.split()) <= 4:
        return "product_search"

    return None


def classify_intent(state: AgentState) -> dict:
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    session = state.get("session", {})

    # Skip LLM for clear-cut cases
    fast = _fast_classify(last_message, session)
    if fast:
        return {"intent": fast}

    recent_msgs = session.get("recent_messages", [])
    if recent_msgs:
        last = recent_msgs[-1]
        recent_context = f'Agent: "{last.get("agent", "")[:200]}"\nBuyer: "{last_message}"'
    else:
        recent_context = f'Buyer: "{last_message}"'

    last_shown = session.get("last_shown_products", [])
    last_shown_summary = (
        ", ".join(p.get("name", "") for p in last_shown[:5]) if last_shown else "None"
    )

    prompt = CLASSIFY_PROMPT.format(
        stage=session.get("stage", "discovery"),
        active_product=json.dumps(session.get("active_product")) if session.get("active_product") else "None",
        active_order_id=session.get("active_order_id", "None"),
        pending_clarification=session.get("pending_clarification", "None"),
        last_shown_products=last_shown_summary,
        recent_context=recent_context,
        message=last_message,
    )

    try:
        response = chat_with_rotation(
            model=get_classify_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        intent = response.choices[0].message.content.strip().lower()
    except Exception:
        intent = "unclear"

    if intent not in VALID_INTENTS:
        intent = "unclear"

    return {"intent": intent}
