"""Response generation node – generates grounded response from tool results."""

import json
import logging
from agent.llm_client import chat_with_rotation, get_model
from agent.prompts.response import RESPONSE_WITH_TOOL_RESULT, CLARIFICATION_PROMPT
from agent.prompts.system import SYSTEM_PROMPT
from agent.language_detect import detect_language
from agent.state import AgentState

logger = logging.getLogger(__name__)


def _rule_based_fallback(state: AgentState) -> str:
    """Constructs a minimal response from tool results without any LLM call.
    Used when all API keys are exhausted or the LLM is unavailable."""
    # Clarification needed — ask for missing info directly
    if state.get("needs_clarification"):
        missing = (state.get("clarification_message") or "").lower()
        if "address" in missing:
            return "To place your order, I just need your delivery address (include pin code). What is it?"
        if "size" in missing:
            return "Which size would you like? (S, M, L, XL, XXL)"
        if "payment" in missing:
            return "How would you like to pay? We support COD, UPI, and Card."
        return f"Just need a few more details: {state.get('clarification_message', 'please provide missing info')}."

    tool_calls = state.get("current_tool_calls", [])
    for tc in tool_calls:
        result = tc.get("result")
        tool = tc.get("tool", "")

        if tool in ("search_catalog", "use_session_data") and isinstance(result, list) and result:
            names = ", ".join(p["name"] for p in result[:5])
            suffix = f" and {len(result) - 5} more" if len(result) > 5 else ""
            return f"We have {names}{suffix}. Which one would you like?"

        if tool == "check_availability" and isinstance(result, dict):
            if result.get("available"):
                return f"{result['product_name']} is available in size {result['size']}. Want to place an order?"
            return f"Sorry, {result.get('product_name', 'that item')} is out of stock in size {result.get('size', '')}."

        if tool == "get_order" and isinstance(result, dict) and result.get("order_id"):
            return f"Your order {result['order_id']} is currently {result.get('status', 'being processed')}."

        if tool == "create_order" and isinstance(result, dict):
            if result.get("order_id"):
                return f"Order placed! Your order ID is {result['order_id']}. You'll receive a confirmation shortly."
            if result.get("error"):
                err = result["error"]
                if "out of stock" in err.lower() or "stock" in err.lower():
                    sizes = result.get("available_sizes", {})
                    if sizes:
                        return f"Sorry, that size is out of stock. Available sizes: {', '.join(sizes.keys())}. Which size would you like?"
                    return "Sorry, that size is currently out of stock. Would you like a different size?"
                if "not found" in err.lower():
                    return "I couldn't find that product. Could you tell me which item you'd like to order?"
                if "cod" in err.lower():
                    return f"COD isn't available for this order. Would you like to pay by UPI or Card instead?"
                return f"I couldn't place the order right now. {err}. Please try again."

        if tool == "get_policy" and isinstance(result, dict):
            text = result.get("answer") or result.get("content") or ""
            return text[:300] if text else "Please check our policy page for details."

    return "I'm having trouble fetching that right now. Please try again in a moment."


def build_response_prompt(state: AgentState) -> dict:
    """Builds the system + user prompt from state. Used by both streaming and non-streaming paths."""
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    session = state.get("session", {})

    detected_lang = detect_language(last_message)
    # Only inherit non-English language from recent turns if current message is very short
    # (e.g. "ok", "yes", "L size") — not if it's a clear English sentence
    if detected_lang == "English" and len(last_message.split()) <= 4:
        recent = session.get("recent_messages", [])
        for prev in reversed(recent):
            prev_lang = detect_language(prev.get("user", ""))
            if prev_lang != "English":
                detected_lang = prev_lang
                break

    lang_instruction = (
        f"CRITICAL LANGUAGE RULE: The buyer's message is in {detected_lang}. "
        f"You MUST reply in {detected_lang} only. Do NOT use Hindi if the buyer wrote in {detected_lang}.\n\n"
    )

    if state.get("needs_clarification"):
        prompt = CLARIFICATION_PROMPT.format(
            missing_fields=state.get("clarification_message", ""),
            session_state=json.dumps(session, indent=2, default=str),
            message=last_message,
        )
    elif state.get("intent") in ("general", "unclear") and not state.get("tool_result"):
        prompt = (
            f'The buyer said: "{last_message}"\n\n'
            f"Session context: {json.dumps(session, indent=2, default=str)}\n\n"
            "Generate a warm, natural response. If it's a greeting, greet back and ask how you can help. "
            "If it's unclear, ask what they're looking for (products, order help, etc.). Keep it under 50 words."
        )
    else:
        tool_results_str = ""
        for tc in state.get("current_tool_calls", []):
            tool_results_str += f"\n--- {tc['tool']}({json.dumps(tc['args'])}) ---\n"
            if tc.get("error"):
                tool_results_str += f"ERROR: {tc['error']}\n"
            else:
                tool_results_str += json.dumps(tc["result"], indent=2, default=str) + "\n"

        # Strip last_shown_products AND recent_messages from session context.
        # Both cause the LLM to pull product names from prior turns and invent availability claims.
        session_for_prompt = {k: v for k, v in session.items()
                              if k not in ("last_shown_products", "recent_messages")}
        prompt = RESPONSE_WITH_TOOL_RESULT.format(
            tool_results=tool_results_str,
            session_state=json.dumps(session_for_prompt, indent=2, default=str),
            message=last_message,
        )

    # Strip heavy fields from session before injecting into system prompt to stay under TPM limits
    session_for_system = {k: v for k, v in session.items()
                          if k not in ("last_shown_products", "recent_messages")}
    system_content = SYSTEM_PROMPT.format(session_state=json.dumps(session_for_system, indent=2, default=str))

    return {
        "system": system_content,
        "user": lang_instruction + prompt,
    }


def generate_response(state: AgentState) -> dict:
    # In streaming mode, skip the LLM call — the endpoint streams directly
    if state.get("streaming_mode"):
        return {
            "response_prompt": build_response_prompt(state),
            "messages": [{"role": "assistant", "content": ""}],
        }

    prompt_data = build_response_prompt(state)

    try:
        response = chat_with_rotation(
            model=get_model(),
            messages=[
                {"role": "system", "content": prompt_data["system"]},
                {"role": "user", "content": prompt_data["user"]},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        agent_response = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM call failed, using rule-based fallback: {e}")
        agent_response = _rule_based_fallback(state)

    return {"messages": [{"role": "assistant", "content": agent_response}]}
