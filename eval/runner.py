from __future__ import annotations
"""Evaluation suite runner."""

import json
from pathlib import Path
from agent.graph import agent
from agent.state import SessionState
from langchain_core.messages import HumanMessage
from eval.scorers import (
    score_task_completion,
    check_tool_hallucination,
    check_tool_validity,
    check_graceful_handling,
)


async def run_eval_suite(test_case_ids: list[str] | None = None) -> dict:
    test_path = Path("eval/test_cases.json")
    with open(test_path) as f:
        all_tests = json.load(f)

    tests = [t for t in all_tests if t["id"] in test_case_ids] if test_case_ids else all_tests

    results = {
        "total": len(tests),
        "task_completion": {"pass": 0, "partial": 0, "fail": 0},
        "tool_hallucination": {"clean": 0, "hallucinated": 0},
        "invalid_tool_use": {"valid": 0, "invalid": 0},
        "graceful_failure": {"graceful": 0, "crashed": 0, "not_applicable": 0},
        "by_workflow": {},
        "details": [],
    }

    for test in tests:
        session = SessionState()
        setup = test.get("setup", {})
        if setup.get("active_product"):
            session.active_product = setup["active_product"]
        if setup.get("active_order_id"):
            session.active_order_id = setup["active_order_id"]
        if setup.get("stage"):
            session.stage = setup["stage"]

        conversation = test["conversation"]
        final_response = ""
        all_tool_calls = []

        for msg in conversation:
            if msg["role"] == "user":
                initial_state = {
                    "messages": [HumanMessage(content=msg["content"])],
                    "session": session.to_dict(),
                    "intent": "",
                    "tool_to_call": None,
                    "tool_args": None,
                    "tool_result": None,
                    "needs_secondary_tool": False,
                    "secondary_tool": None,
                    "secondary_args": None,
                    "secondary_result": None,
                    "needs_clarification": False,
                    "clarification_message": None,
                    "should_escalate": False,
                    "confidence_score": 1.0,
                    "current_tool_calls": [],
                    "error": None,
                }

                try:
                    final_state = agent.invoke(initial_state)

                    messages = final_state.get("messages", [])
                    for m in reversed(messages):
                        if hasattr(m, "content") and getattr(m, "type", None) == "ai":
                            final_response = m.content
                            break
                        elif isinstance(m, dict) and m.get("role") == "assistant":
                            final_response = m["content"]
                            break

                    all_tool_calls.extend(final_state.get("current_tool_calls", []))
                    session = SessionState.from_dict(final_state.get("session", {}))

                except Exception as e:
                    final_response = f"ERROR: {str(e)}"
                    all_tool_calls.append({"tool": "CRASH", "args": {}, "error": str(e)})

        expected = test["expected"]
        detail = {
            "test_id": test["id"],
            "workflow": test.get("workflow", "unknown"),
            "category": test.get("category", "unknown"),
            "response": final_response,
            "tool_calls": [{"tool": tc["tool"], "args": tc.get("args", {})} for tc in all_tool_calls],
            "scores": {},
        }

        tc_score = score_task_completion(final_response, all_tool_calls, expected)
        detail["scores"]["task_completion"] = tc_score
        results["task_completion"][tc_score] += 1

        is_clean = check_tool_hallucination(final_response, all_tool_calls, expected)
        detail["scores"]["tool_hallucination"] = "clean" if is_clean else "hallucinated"
        results["tool_hallucination"]["clean" if is_clean else "hallucinated"] += 1

        is_valid = check_tool_validity(all_tool_calls, expected.get("tools_called", []))
        detail["scores"]["tool_validity"] = "valid" if is_valid else "invalid"
        results["invalid_tool_use"]["valid" if is_valid else "invalid"] += 1

        if test.get("category") in ("edge_case", "adversarial"):
            is_graceful = check_graceful_handling(final_response, expected)
            detail["scores"]["graceful_failure"] = "graceful" if is_graceful else "crashed"
            results["graceful_failure"]["graceful" if is_graceful else "crashed"] += 1
        else:
            detail["scores"]["graceful_failure"] = "n/a"
            results["graceful_failure"]["not_applicable"] += 1

        workflow = test.get("workflow", "unknown")
        if workflow not in results["by_workflow"]:
            results["by_workflow"][workflow] = {"pass": 0, "partial": 0, "fail": 0}
        results["by_workflow"][workflow][tc_score] += 1

        results["details"].append(detail)

    return results
