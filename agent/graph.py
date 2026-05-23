"""LangGraph agent assembly – the state machine."""

from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.classify import classify_intent
from agent.nodes.context_check import check_context
from agent.nodes.tool_selector import select_tool
from agent.nodes.tool_executor import execute_tool
from agent.nodes.response_gen import generate_response
from agent.nodes.confidence import check_confidence
from agent.nodes.memory import update_memory, escalate_to_seller


def route_after_classify(state: AgentState) -> str:
    intent = state.get("intent", "unclear")
    if intent in ("general", "unclear"):
        return "generate_response"
    return "check_context"


def route_after_context(state: AgentState) -> str:
    if state.get("needs_clarification"):
        return "generate_response"
    return "select_tool"


def route_after_confidence(state: AgentState) -> str:
    if state.get("should_escalate"):
        return "escalate"
    return "update_memory"


def build_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("classify_intent", classify_intent)
    workflow.add_node("check_context", check_context)
    workflow.add_node("select_tool", select_tool)
    workflow.add_node("execute_tool", execute_tool)
    workflow.add_node("generate_response", generate_response)
    workflow.add_node("check_confidence", check_confidence)
    workflow.add_node("update_memory", update_memory)
    workflow.add_node("escalate", escalate_to_seller)

    workflow.set_entry_point("classify_intent")

    workflow.add_conditional_edges("classify_intent", route_after_classify, {
        "check_context": "check_context",
        "generate_response": "generate_response",
    })

    workflow.add_conditional_edges("check_context", route_after_context, {
        "generate_response": "generate_response",
        "select_tool": "select_tool",
    })

    workflow.add_edge("select_tool", "execute_tool")
    workflow.add_edge("execute_tool", "generate_response")
    workflow.add_edge("generate_response", "check_confidence")

    workflow.add_conditional_edges("check_confidence", route_after_confidence, {
        "escalate": "escalate",
        "update_memory": "update_memory",
    })

    workflow.add_edge("update_memory", END)
    workflow.add_edge("escalate", END)

    return workflow.compile()


agent = build_agent()
