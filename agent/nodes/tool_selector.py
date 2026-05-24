"""Tool selection node – decides which tool to call based on intent and context."""

import re
from difflib import get_close_matches
from agent.state import AgentState
from tools.catalog import CATALOG_COLORS, CATALOG_CATEGORIES


def select_tool(state: AgentState) -> dict:
    intent = state["intent"]
    session = state.get("session", {})
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""

    if intent == "product_search":
        return _select_catalog_tool(last_message, session)
    elif intent == "policy_question":
        return _select_policy_tool(last_message)
    elif intent == "place_order":
        return _select_order_tool(last_message, session)
    elif intent == "order_support":
        return _select_support_tool(last_message, session)

    return {"tool_to_call": None, "tool_args": None}


def _select_catalog_tool(message: str, session: dict) -> dict:
    msg_lower = message.lower()
    args = {}

    _category_aliases = {
        "kurti": "kurta", "kurtas": "kurta",
        "sari": "saree", "sarees": "saree",
        "lehnga": "lehenga", "lhenga": "lehenga", "lenga": "lehenga", "lehengas": "lehenga",
        "shawl": "stole", "palazzo": "palazzo_set",
        "dupattas": "dupatta",
    }
    for keyword in list(CATALOG_CATEGORIES) + list(_category_aliases.keys()):
        if keyword in msg_lower:
            args["category"] = _category_aliases.get(keyword, keyword)
            break

    # Fuzzy fallback: catch typos like "sarres"→"saree", "anrakali"→"anarkali"
    # Skip color words — "blue" fuzzy-matches "blouse" at 0.75, causing wrong category
    if not args.get("category"):
        all_cat_names = list(CATALOG_CATEGORIES) + list(_category_aliases.keys())
        for word in msg_lower.split():
            if len(word) >= 4 and word not in CATALOG_COLORS:
                matches = get_close_matches(word, all_cat_names, n=1, cutoff=0.75)
                if matches:
                    matched = matches[0]
                    args["category"] = _category_aliases.get(matched, matched)
                    break

    price_match = (
        re.search(r'under\s*₹?\s*(\d+)', msg_lower)
        or re.search(r'below\s*₹?\s*(\d+)', msg_lower)
        or re.search(r'within\s*₹?\s*(\d+)', msg_lower)
    )
    if price_match:
        args["max_price"] = int(price_match.group(1))

    detected_size = None
    for s in ["XS", "S", "M", "L", "XL", "XXL", "FREE SIZE"]:
        # Lookbehind prevents matching S in contractions like "what's", "it's", "I'm"
        if re.search(rf"(?<![A-Za-z'])\b{re.escape(s)}\b(?!')", message.upper()):
            detected_size = s
            break
    if detected_size:
        args["size"] = detected_size

    # Fuzzy typo correction for colors (handles "ornage"→"orange", "blakc"→"black" etc.)
    _corrected_words = []
    for word in msg_lower.split():
        if len(word) >= 4 and word not in CATALOG_COLORS:
            close = get_close_matches(word, [c for c in CATALOG_COLORS if len(c.split()) == 1], n=1, cutoff=0.80)
            _corrected_words.append(close[0] if close else word)
        else:
            _corrected_words.append(word)
    msg_lower = " ".join(_corrected_words)
    # Match longest color names first so "mint green" doesn't also count as "green"
    _sorted_colors = sorted(CATALOG_COLORS, key=len, reverse=True)
    found_colors = []
    _remaining = msg_lower
    for _c in _sorted_colors:
        if _c in _remaining:
            found_colors.append(_c)
            _remaining = _remaining.replace(_c, " " * len(_c))
    if len(found_colors) > 1:
        # Multi-color OR query — skip name-matching, search all colors at once
        args["colors"] = [c.title() for c in found_colors]
        args["top_k"] = min(8, len(found_colors) * 3)
        # Infer category from browsing context (e.g. viewing kurtas → "orange or blue" → kurtas only)
        if not args.get("category"):
            _ls = session.get("last_shown_products", [])
            if _ls:
                _sc = {p.get("category", "").lower() for p in _ls if p.get("category")}
                if len(_sc) == 1:
                    args["category"] = _sc.pop()
        return {"tool_to_call": "search_catalog", "tool_args": args}
    elif len(found_colors) == 1:
        args["color"] = found_colors[0].title()

    last_shown = session.get("last_shown_products", [])
    product = session.get("active_product")

    # Infer category from context: "this in red?" after browsing kurtas → search red kurtas
    if not args.get("category") and last_shown and (found_colors or detected_size):
        shown_cats = {p.get("category", "").lower() for p in last_shown if p.get("category")}
        if len(shown_cats) == 1:
            args["category"] = shown_cats.pop()

    # Name-match against shown products — pick highest score, not first match
    if last_shown:
        best_match = None
        best_score = 0
        for shown_product in last_shown:
            name_parts = shown_product.get("name", "").lower().split()
            meaningful = [w for w in name_parts if len(w) > 3]
            if meaningful:
                score = sum(1 for w in meaningful if w in msg_lower)
                if score >= min(2, len(meaningful)) and score > best_score:
                    best_match = shown_product
                    best_score = score

        # Color-based product identification: if name-match failed and user mentioned a color
        # that uniquely identifies one product in last_shown, use that product
        if not best_match and found_colors:
            color_matched = [
                p for p in last_shown
                if any(c.lower() in [pc.lower() for pc in p.get("colors", [])] for c in found_colors)
            ]
            if len(color_matched) == 1:
                best_match = color_matched[0]

        # Ordinal selection: "the first one", "option 2", "second product"
        if not best_match:
            _ord_re = re.search(
                r'\b(first|second|third|1st|2nd|3rd)\b|\b(?:option|number|item)\s*([123])\b',
                msg_lower
            )
            if _ord_re:
                _word, _num = _ord_re.group(1), _ord_re.group(2)
                _idx_map = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}
                _idx = (int(_num) - 1) if _num else _idx_map.get(_word, -1)
                if 0 <= _idx < len(last_shown):
                    best_match = last_shown[_idx]

        if best_match:
            if detected_size:
                # User named a specific product AND asked about a size → check availability
                return {
                    "tool_to_call": "check_availability",
                    "tool_args": {"product_id": best_match.get("product_id"), "size": detected_size},
                }
            return {
                "tool_to_call": "use_session_data",
                "tool_args": {"product_id": best_match.get("product_id")},
            }

    # User said color+category but name match failed — cap search to 1 result
    if last_shown and args.get("color") and args.get("category"):
        args["top_k"] = 1
        args.setdefault("query", message)

    # "what sizes?" or "I want size L" after products were shown → read from existing data
    # Each product in last_shown has a `sizes` dict with stock counts — no new search needed
    size_question_patterns = [
        "eh size", "which size", "sizes available", "sizes unnay", "evari size",
        "size unte", "sizes undi", "sizes unnayi", "eh sizes", "what size",
        "size cheppandi", "konni sizes",
        "what are the size", "available size", "size do you have", "sizes do you",
    ]
    # Active product already selected + user picks a size → check that specific product's availability
    # Skip if category is in args — "show me kurtas in XXL" is a catalog search, not an availability check
    if product and detected_size and not args.get("category"):
        return {
            "tool_to_call": "check_availability",
            "tool_args": {"product_id": product.get("product_id"), "size": detected_size},
        }

    if last_shown and (
        any(p in msg_lower for p in size_question_patterns)
        or (detected_size and not args.get("category"))
    ):
        return {"tool_to_call": "use_session_data", "tool_args": {"size": detected_size} if detected_size else {}}

    # Single product in session + size/availability query → check_availability
    if product and (detected_size or any(kw in msg_lower for kw in ["available", "stock", "size"])):
        if detected_size:
            return {
                "tool_to_call": "check_availability",
                "tool_args": {"product_id": product.get("product_id"), "size": detected_size},
            }

    # "any other options", "show more", "something else" → use active category or broader search
    more_patterns = ["other option", "more option", "something else", "anything else",
                     "show more", "other product", "what else", "more choices", "alternatives"]
    if any(p in msg_lower for p in more_patterns):
        if product and product.get("category"):
            args["category"] = product["category"]
        if not args.get("category") and last_shown:
            _lsc = {p.get("category", "").lower() for p in last_shown if p.get("category")}
            if len(_lsc) == 1:
                args["category"] = _lsc.pop()
        args["top_k"] = 8
        if not args.get("category"):
            args["query"] = "popular indian ethnic wear"
        return {"tool_to_call": "search_catalog", "tool_args": args}

    # Generic browse ("catalog", "show me everything", "what do you have", Hindi variants)
    browse_patterns = ["catalog", "show me", "what do you have", "what do you sell",
                       "everything", "all product", "browse", "see your collection",
                       "dikhao", "dikhaiye", "batao"]
    if any(p in msg_lower for p in browse_patterns) and not args:
        args["query"] = "indian ethnic wear kurta saree lehenga"
        args["top_k"] = 8
        return {"tool_to_call": "search_catalog", "tool_args": args}

    # Detail/price queries with products in context → return existing session data, no new search
    _detail_patterns = ["price", "cost", "how much", "kitna", "tell me more", "more detail",
                        "about this", "more info", "describe", "which one is", "which is better",
                        "which one should", "compare"]
    if last_shown and not args and any(p in msg_lower for p in _detail_patterns):
        return {"tool_to_call": "use_session_data", "tool_args": {}}

    if not args:
        args["query"] = message

    # Category-only browse (no color/price/size filter) → show all, no cap
    if args.get("category") and not args.get("color") and not args.get("max_price") and not args.get("size"):
        args.setdefault("top_k", 50)
    else:
        args.setdefault("top_k", 5)
    return {"tool_to_call": "search_catalog", "tool_args": args}


def _select_policy_tool(message: str) -> dict:
    return {"tool_to_call": "get_policy", "tool_args": {"query": message}}


def _select_order_tool(message: str, session: dict) -> dict:
    product = session.get("active_product") or {}

    size = None
    for s in ["XXL", "XL", "XS", "FREE SIZE", "S", "M", "L"]:
        if re.search(rf'\b{s}\b', message.upper()):
            size = s
            break
    if not size:
        size = session.get("pending_size", "")

    # Validate size against the active product — don't use a cached size from a different product.
    # E.g. pending_size="XXL" from an earlier kurta search should not carry over to a FREE SIZE saree.
    if size and product:
        prod_sizes = product.get("sizes", {})
        if prod_sizes and size.upper() not in prod_sizes:
            size = ""  # let create_order auto-select the one valid size

    payment = None
    msg_lower = message.lower()
    if "cod" in msg_lower or "cash" in msg_lower:
        payment = "COD"
    elif "upi" in msg_lower or "gpay" in msg_lower:
        payment = "UPI"
    elif "card" in msg_lower:
        payment = "Card"
    if not payment:
        payment = session.get("payment_preference") or "COD"

    address = ""
    address_match = re.search(r'address[:\s]+(.+?)(?:\.|$)', message, re.IGNORECASE)
    if address_match:
        address = address_match.group(1).strip()
    elif re.search(r'\b\d{6}\b', message):
        address = message
    if not address:
        address = session.get("delivery_address", "")

    name = session.get("buyer_name") or "Customer"

    product_id = product.get("product_id", "")
    if not product_id:
        last_shown = session.get("last_shown_products", [])
        if len(last_shown) == 1:
            product_id = last_shown[0].get("product_id", "")
        elif last_shown:
            _msg_l = message.lower()
            # Color-based match: "order the green one" → find green product
            for _c in sorted(CATALOG_COLORS, key=len, reverse=True):
                if _c in _msg_l:
                    _cm = [p for p in last_shown if any(_c == pc.lower() for pc in p.get("colors", []))]
                    if len(_cm) == 1:
                        product_id = _cm[0].get("product_id", "")
                        break
            # Name-based fallback — pick best scoring product, not first match
            if not product_id:
                _best_id, _best_score = "", 0
                for p in last_shown:
                    _pts = [w for w in p.get("name", "").lower().split() if len(w) > 3]
                    if _pts:
                        _sc = sum(1 for w in _pts if w in _msg_l)
                        if _sc >= min(2, len(_pts)) and _sc > _best_score:
                            _best_id, _best_score = p.get("product_id", ""), _sc
                product_id = _best_id

    return {
        "tool_to_call": "create_order",
        "tool_args": {
            "customer_name": name,
            "product_id": product_id,
            "size": size or "",
            "quantity": 1,
            "payment_method": payment,
            "address": address,
        },
        "needs_secondary_tool": False,
    }


def _select_support_tool(message: str, session: dict) -> dict:
    order_id = session.get("active_order_id")
    match = re.search(r'ORD-\d+', message, re.IGNORECASE)
    if match:
        order_id = match.group(0).upper()

    msg_lower = message.lower()

    # Detect explicit payment method change request
    new_payment = None
    change_patterns = ["change to upi", "change to cod", "change to card",
                       "switch to upi", "switch to cod", "upi instead", "cod instead",
                       "pay via upi", "pay via cod", "pay by upi", "pay by card"]
    if any(p in msg_lower for p in change_patterns):
        if "upi" in msg_lower or "gpay" in msg_lower:
            new_payment = "UPI"
        elif "cod" in msg_lower or "cash" in msg_lower:
            new_payment = "COD"
        elif "card" in msg_lower:
            new_payment = "Card"

    # "yes" / "confirm" after agent proposed a payment change — read from last agent message
    confirmation_words = {"yes", "yeah", "yep", "ok", "okay", "sure", "go ahead", "confirm", "proceed"}
    if not new_payment and msg_lower.strip() in confirmation_words:
        recent = session.get("recent_messages", [])
        if recent:
            last_agent = recent[-1].get("agent", "").lower()
            if "upi" in last_agent and ("change" in last_agent or "update" in last_agent or "send" in last_agent):
                new_payment = "UPI"
            elif "cod" in last_agent and ("change" in last_agent or "update" in last_agent):
                new_payment = "COD"
            elif "card" in last_agent and ("change" in last_agent or "update" in last_agent):
                new_payment = "Card"

    if new_payment and order_id:
        return {
            "tool_to_call": "update_order",
            "tool_args": {"order_id": order_id, "updates": {"payment_method": new_payment}},
            "needs_secondary_tool": False,
        }

    needs_policy = any(kw in msg_lower for kw in ["refund", "return", "exchange", "cancel"])

    # Carry refund/exchange context from previous turn (e.g. user said "refund" then provided order ID)
    if not needs_policy:
        recent = session.get("recent_messages", [])
        for m in reversed(recent):
            prev_user = m.get("user", "").lower()
            if any(kw in prev_user for kw in ["refund", "return", "exchange", "cancel"]):
                needs_policy = True
                break

    result = {
        "tool_to_call": "get_order",
        "tool_args": {"order_id": order_id or ""},
    }

    if needs_policy:
        policy_query = (
            "refund policy conditions" if "refund" in msg_lower or "return" in msg_lower
            else "exchange policy conditions" if "exchange" in msg_lower
            else "cancellation policy"
        )
        result["needs_secondary_tool"] = True
        result["secondary_tool"] = "get_policy"
        result["secondary_args"] = {"query": policy_query}

    return result
