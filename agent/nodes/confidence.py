"""Confidence scoring and escalation decision node."""

from agent.state import AgentState


def check_confidence(state: AgentState) -> dict:
    score = 1.0

    for tc in state.get("current_tool_calls", []):
        if tc.get("error"):
            score -= 0.3

    intent = state.get("intent")
    if intent in ("product_search", "order_support", "policy_question"):
        if not state.get("current_tool_calls"):
            score -= 0.4

    if state.get("tool_result") is None and not state.get("needs_clarification"):
        score -= 0.2

    result = state.get("tool_result", {})
    if isinstance(result, dict) and result.get("error"):
        score -= 0.2

    score = max(0.0, min(1.0, score))
    should_escalate = score < 0.4

    return {"confidence_score": round(score, 2), "should_escalate": should_escalate}
