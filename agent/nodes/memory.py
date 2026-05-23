"""Memory update node – updates session state after each turn."""

import re
from agent.state import AgentState, SessionState
from tools.catalog import CATALOG_COLORS


def _extract_size(msg: str):
    for s in ["XXL", "XL", "XS", "FREE SIZE", "S", "M", "L"]:
        if re.search(rf'\b{s}\b', msg.upper()):
            return s
    return None


def _extract_payment(msg: str):
    msg_lower = msg.lower()
    if "cod" in msg_lower or "cash on delivery" in msg_lower:
        return "COD"
    if "upi" in msg_lower or "gpay" in msg_lower or "phonepay" in msg_lower:
        return "UPI"
    if "card" in msg_lower or "credit" in msg_lower or "debit" in msg_lower:
        return "Card"
    return None


def _extract_address(msg: str):
    if re.search(r'\b\d{6}\b', msg):
        return msg.strip()
    address_signals = ["road", "street", "nagar", "colony", "sector", "block",
                       "floor", "flat", "house", "apartment", "lane"]
    if any(signal in msg.lower() for signal in address_signals):
        return msg.strip()
    return None


def update_memory(state: AgentState) -> dict:
    session_dict = state.get("session", {})
    session = SessionState.from_dict(session_dict)

    messages = state["messages"]
    last_user_msg = ""
    last_agent_msg = ""

    for msg in reversed(messages):
        if hasattr(msg, "content"):
            if getattr(msg, "type", None) == "human" and not last_user_msg:
                last_user_msg = msg.content
            elif getattr(msg, "type", None) == "ai" and not last_agent_msg:
                last_agent_msg = msg.content
        elif isinstance(msg, dict):
            if msg.get("role") == "user" and not last_user_msg:
                last_user_msg = msg["content"]
            elif msg.get("role") == "assistant" and not last_agent_msg:
                last_agent_msg = msg["content"]

    session.update_after_turn(
        user_msg=last_user_msg,
        agent_response=last_agent_msg,
        tool_calls=state.get("current_tool_calls", []),
    )

    # Persist order-relevant info extracted from any message so future turns don't re-ask
    if last_user_msg:
        size = _extract_size(last_user_msg)
        if size:
            session.pending_size = size

        payment = _extract_payment(last_user_msg)
        if payment:
            session.payment_preference = payment

        address = _extract_address(last_user_msg)
        if address:
            session.delivery_address = address

        # Pin active_product if user names/colors/ordinal-references a product from last_shown_products
        if not session.active_product and session.last_shown_products:
            msg_lower = last_user_msg.lower()
            for product in session.last_shown_products:
                name_parts = product.get("name", "").lower().split()
                meaningful = [w for w in name_parts if len(w) > 3]
                if meaningful and sum(1 for w in meaningful if w in msg_lower) >= min(2, len(meaningful)):
                    session.active_product = product
                    break
            # Color-based pin: "the green one", "order that orange kurta"
            if not session.active_product:
                for _c in sorted(CATALOG_COLORS, key=len, reverse=True):
                    if _c in msg_lower:
                        _cm = [p for p in session.last_shown_products
                               if any(_c == pc.lower() for pc in p.get("colors", []))]
                        if len(_cm) == 1:
                            session.active_product = _cm[0]
                            break
            # Ordinal-based pin: "the first one", "option 2", "second product"
            if not session.active_product:
                _ord = re.search(
                    r'\b(first|second|third|1st|2nd|3rd)\b|\b(?:option|number|item)\s*([123])\b',
                    msg_lower
                )
                if _ord:
                    _w, _n = _ord.group(1), _ord.group(2)
                    _imap = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}
                    _i = (int(_n) - 1) if _n else _imap.get(_w, -1)
                    if 0 <= _i < len(session.last_shown_products):
                        session.active_product = session.last_shown_products[_i]

    if state.get("needs_clarification"):
        session.pending_clarification = state.get("clarification_message")
    else:
        session.pending_clarification = None

    # If create_order failed due to payment (COD rejected), flag clarification so next
    # message like "UPI" is correctly routed as place_order, not order_support.
    for tc in state.get("current_tool_calls", []):
        if tc.get("tool") == "create_order":
            err = (tc.get("result") or {}).get("error", "")
            if err and ("cod" in err.lower() or "payment" in err.lower()):
                session.pending_clarification = "payment method (COD not available — please choose UPI or Card)"
                break

    intent = state.get("intent")
    if intent == "place_order" and not state.get("needs_clarification"):
        session.stage = "ordering"
    elif intent == "order_support":
        session.stage = "post_order"
    elif intent == "policy_question" and session.stage in ("discovery", "pre_order"):
        session.stage = "pre_order"

    return {"session": session.to_dict()}


def escalate_to_seller(state: AgentState) -> dict:
    escalation_msg = (
        "\n\nI want to make sure you get the best help. "
        "Let me connect you with the seller who can assist you directly. "
        "They'll respond shortly! 🙏"
    )

    messages = state["messages"]
    for msg in reversed(messages):
        if hasattr(msg, "content") and getattr(msg, "type", None) == "ai":
            return {"messages": [{"role": "assistant", "content": msg.content + escalation_msg}]}
        elif isinstance(msg, dict) and msg.get("role") == "assistant":
            return {"messages": [{"role": "assistant", "content": msg["content"] + escalation_msg}]}

    return {"messages": [{"role": "assistant", "content": "Let me connect you with the seller for this. They'll help you out! 🙏"}]}
