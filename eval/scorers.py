from __future__ import annotations
"""Scoring functions for the 4 eval metrics."""

import re


def score_task_completion(response: str, tool_calls: list[dict], expected: dict) -> str:
    """Returns: pass | partial | fail"""
    if "ERROR" in response or "CRASH" in response:
        return "fail"

    response_lower = response.lower()

    must_contain = expected.get("response_must_contain", [])
    contains_all = all(term.lower() in response_lower for term in must_contain)

    must_contain_any = expected.get("response_must_contain_any", [])
    contains_any = not must_contain_any or any(term.lower() in response_lower for term in must_contain_any)

    must_not_contain = expected.get("response_must_not_contain", [])
    avoids_all = all(term.lower() not in response_lower for term in must_not_contain)

    expected_tools = set(expected.get("tools_called", []))
    actual_tools = set(tc["tool"] for tc in tool_calls if not tc.get("error"))
    tools_match = expected_tools.issubset(actual_tools) if expected_tools else True

    if contains_all and contains_any and avoids_all and tools_match:
        return "pass"
    elif (contains_all or contains_any) and tools_match:
        return "partial"
    else:
        return "fail"


def check_tool_hallucination(response: str, tool_calls: list[dict], expected: dict) -> bool:
    """Returns True if response is clean (not hallucinated)."""
    response_lower = response.lower()
    actual_tools = [tc["tool"] for tc in tool_calls if not tc.get("error")]

    has_price = bool(re.search(r'₹\s*\d+', response))
    has_catalog_call = any(t in actual_tools for t in ["search_catalog", "check_availability", "get_product"])
    if has_price and not has_catalog_call:
        return False

    availability_words = ["in stock", "available", "out of stock", "not available", "units left"]
    mentions_availability = any(w in response_lower for w in availability_words)
    if mentions_availability and not has_catalog_call:
        return False

    policy_words = ["7 day", "7-day", "10 day", "10-day", "refund window", "exchange window",
                    "₹5000", "custom-stitched", "non-refundable", "5-7 business"]
    mentions_policy = any(w in response_lower for w in policy_words)
    has_policy_call = "get_policy" in actual_tools
    if mentions_policy and not has_policy_call:
        return False

    return True


def check_tool_validity(tool_calls: list[dict], expected_tools: list[str]) -> bool:
    """Returns True if tool usage is valid."""
    actual_tools = [tc["tool"] for tc in tool_calls if not tc.get("error")]

    for expected in expected_tools:
        if expected not in actual_tools:
            return False

    seen_calls = set()
    for tc in tool_calls:
        call_sig = f"{tc['tool']}:{tuple(sorted(tc.get('args', {}).items()))}"
        if call_sig in seen_calls:
            return False
        seen_calls.add(call_sig)

    return True


def check_graceful_handling(response: str, expected: dict) -> bool:
    """Returns True if agent handled failure gracefully."""
    response_lower = response.lower()

    must_not_contain = expected.get("response_must_not_contain", [])
    if any(term.lower() in response_lower for term in must_not_contain):
        return False

    must_contain_any = expected.get("response_must_contain_any", [])
    if must_contain_any:
        if not any(term.lower() in response_lower for term in must_contain_any):
            return False

    if "traceback" in response_lower or "exception" in response_lower:
        return False

    return True
