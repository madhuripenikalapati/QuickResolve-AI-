"""Tool execution node with error handling."""

import logging
from agent.state import AgentState
from tools.catalog import search_catalog, check_availability, get_product
from tools.orders import get_order, create_order, update_order
from tools.policy_rag import get_policy

logger = logging.getLogger(__name__)

TOOLS = {
    "search_catalog": search_catalog,
    "check_availability": check_availability,
    "get_product": get_product,
    "get_order": get_order,
    "create_order": create_order,
    "update_order": update_order,
    "get_policy": get_policy,
}


def execute_tool(state: AgentState) -> dict:
    tool_name = state.get("tool_to_call")
    tool_args = state.get("tool_args", {})
    tool_calls = []

    if tool_name == "use_session_data":
        last_shown = state.get("session", {}).get("last_shown_products", [])
        result = last_shown or []

        # Apply size/product filter from tool_args
        requested_size = (tool_args or {}).get("size", "").upper()
        product_id = (tool_args or {}).get("product_id")

        if product_id:
            matched = [p for p in result if p.get("product_id") == product_id]
            if matched:
                result = matched

        if requested_size and result:
            filtered = [
                p for p in result
                if requested_size == "FREE SIZE"
                or p.get("sizes", {}).get(requested_size, 0) > 0
                or p.get("sizes", {}).get("FREE SIZE", 0) > 0
            ]
            if filtered:
                result = filtered
            else:
                # Return a plain error dict — NOT a product list — so the LLM cannot hallucinate availability
                available = {}
                for p in result:
                    for sz, qty in p.get("sizes", {}).items():
                        if qty > 0:
                            available[sz] = available.get(sz, 0) + qty
                result = {
                    "size_not_available": True,
                    "requested_size": requested_size,
                    "message": f"None of the shown products are available in size {requested_size}.",
                    "sizes_that_are_available": sorted(available.keys()),
                }

        tool_calls = [{"tool": "use_session_data", "args": tool_args or {}, "result": result, "error": None}]
        return {"tool_result": result, "secondary_result": None, "current_tool_calls": tool_calls, "error": None}

    if not tool_name or tool_name not in TOOLS:
        return {
            "tool_result": None,
            "current_tool_calls": [],
            "error": f"Unknown tool: {tool_name}" if tool_name else "No tool selected",
        }

    try:
        result = TOOLS[tool_name](**tool_args)
        tool_calls.append({"tool": tool_name, "args": tool_args, "result": result, "error": None})
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        result = {"error": str(e)}
        tool_calls.append({"tool": tool_name, "args": tool_args, "result": None, "error": str(e)})

    secondary_result = None
    if state.get("needs_secondary_tool") and state.get("secondary_tool"):
        sec_tool = state["secondary_tool"]
        sec_args = state.get("secondary_args", {})
        try:
            secondary_result = TOOLS[sec_tool](**sec_args)
            tool_calls.append({"tool": sec_tool, "args": sec_args, "result": secondary_result, "error": None})
        except Exception as e:
            logger.error(f"Secondary tool {sec_tool} failed: {e}")
            tool_calls.append({"tool": sec_tool, "args": sec_args, "result": None, "error": str(e)})

    return {
        "tool_result": result,
        "secondary_result": secondary_result,
        "current_tool_calls": tool_calls,
        "error": None,
    }
