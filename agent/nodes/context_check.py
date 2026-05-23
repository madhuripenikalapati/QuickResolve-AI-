from __future__ import annotations
"""Context sufficiency check node."""

import re
from agent.state import AgentState
from tools.catalog import CATALOG_CATEGORIES

REQUIRED_CONTEXT = {
    "place_order": {
        "needs_product": True,
        "needs_size": True,
        "needs_address": True,
        "needs_payment": True,
    },
    "order_support": {
        "needs_order_id": True,
    },
    "product_search": {},
    "policy_question": {},
    "general": {},
    "unclear": {},
}


def check_context(state: AgentState) -> dict:
    intent = state["intent"]
    session = state.get("session", {})
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""

    required = REQUIRED_CONTEXT.get(intent, {})
    missing = []

    if required.get("needs_product"):
        has_product = (
            session.get("active_product")
            or _message_contains_product_ref(last_message)
            or _message_references_shown_product(last_message, session.get("last_shown_products", []))
            or len(session.get("last_shown_products", [])) == 1  # unambiguous: only 1 product in context
        )
        if not has_product:
            missing.append("product (which item would you like?)")

    if required.get("needs_size"):
        active_prod = session.get("active_product") or {}
        prod_sizes = active_prod.get("sizes", {})
        available_sizes = [s for s, qty in prod_sizes.items() if qty > 0] if prod_sizes else []

        # Skip asking for size when product only has one option (e.g. FREE SIZE sarees)
        if len(available_sizes) == 1:
            size_ok = True
        else:
            # Validate any cached pending_size against this product's actual sizes
            pending = session.get("pending_size", "")
            in_message = _extract_size(last_message)
            candidate = in_message or pending
            if candidate and prod_sizes:
                size_ok = candidate.upper() in prod_sizes
            else:
                size_ok = bool(candidate)
        if not size_ok:
            missing.append("size")

    if required.get("needs_address"):
        if not _extract_address(last_message) and not session.get("delivery_address"):
            missing.append("delivery address")

    if required.get("needs_payment"):
        if not _extract_payment(last_message) and not session.get("payment_preference"):
            missing.append("payment method (COD, UPI, or Card)")

    if required.get("needs_order_id"):
        if not session.get("active_order_id") and not _extract_order_id(last_message):
            missing.append("order ID")

    if missing:
        return {
            "needs_clarification": True,
            "clarification_message": f"Missing: {', '.join(missing)}",
        }

    return {"needs_clarification": False, "clarification_message": None}


def _message_contains_product_ref(msg: str) -> bool:
    msg_lower = msg.lower()
    if "prod-" in msg_lower:
        return True
    return any(cat in msg_lower for cat in CATALOG_CATEGORIES)


def _message_references_shown_product(msg: str, last_shown: list) -> bool:
    """Returns True if the message names any product from last_shown_products."""
    if not last_shown:
        return False
    msg_lower = msg.lower()
    for product in last_shown:
        name_parts = product.get("name", "").lower().split()
        meaningful = [w for w in name_parts if len(w) > 3]
        if meaningful and sum(1 for w in meaningful if w in msg_lower) >= min(2, len(meaningful)):
            return True
        # Color reference: "the green one", "orange dress", "order the blue kurta"
        for c in product.get("colors", []):
            if c.lower() in msg_lower:
                return True
    return False


def _extract_size(msg: str):
    sizes = ["XS", "S", "M", "L", "XL", "XXL", "FREE SIZE", "Free Size"]
    msg_upper = msg.upper()
    for size in sizes:
        if size in msg_upper:
            return size
    return None


def _extract_address(msg: str):
    if re.search(r'\b\d{6}\b', msg):
        return msg
    address_signals = ["road", "street", "nagar", "colony", "sector", "block",
                       "floor", "flat", "house", "apartment", "lane"]
    if any(signal in msg.lower() for signal in address_signals):
        return msg
    return None


def _extract_order_id(msg: str):
    match = re.search(r'ORD-\d+', msg, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _extract_payment(msg: str):
    msg_lower = msg.lower()
    if "cod" in msg_lower or "cash on delivery" in msg_lower:
        return "COD"
    if "upi" in msg_lower or "gpay" in msg_lower or "phonepay" in msg_lower:
        return "UPI"
    if "card" in msg_lower or "credit" in msg_lower or "debit" in msg_lower:
        return "Card"
    return None
