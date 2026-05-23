"""Chat endpoint."""

import json
import logging
import time
import uuid
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from api.models import ChatRequest, ChatResponse, ToolCallInfo
from agent.graph import agent
from agent.state import SessionState
from agent.llm_client import chat_stream_with_rotation, get_model
from agent.nodes.response_gen import _rule_based_fallback
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)
router = APIRouter()

sessions: dict[str, dict] = {}


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    trace_id = str(uuid.uuid4())[:8]
    t_start = time.time()
    session_data = sessions.get(request.session_id, SessionState().to_dict())

    initial_state = {
        "messages": [HumanMessage(content=request.message)],
        "session": session_data,
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
    except Exception as e:
        latency_ms = int((time.time() - t_start) * 1000)
        logger.error({
            "trace_id": trace_id,
            "session_id": request.session_id,
            "event": "agent_error",
            "error": str(e),
            "latency_ms": latency_ms,
        })
        return ChatResponse(
            response="Sorry, something went wrong on my end. Please try again.",
            session_id=request.session_id,
            intent="error",
            confidence_score=0.0,
            tool_calls=[],
            session_state=session_data,
            escalated=False,
        )

    messages = final_state.get("messages", [])
    agent_response = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and getattr(msg, "type", None) == "ai":
            agent_response = msg.content
            break
        elif isinstance(msg, dict) and msg.get("role") == "assistant":
            agent_response = msg["content"]
            break

    sessions[request.session_id] = final_state.get("session", session_data)

    tool_calls = [
        ToolCallInfo(
            tool=tc["tool"],
            args=tc["args"],
            result=tc.get("result"),
            error=tc.get("error"),
        )
        for tc in final_state.get("current_tool_calls", [])
    ]

    latency_ms = int((time.time() - t_start) * 1000)
    intent = final_state.get("intent", "unknown")
    confidence = final_state.get("confidence_score", 0.0)
    tools_used = [tc["tool"] for tc in final_state.get("current_tool_calls", [])]
    errors = [tc["error"] for tc in final_state.get("current_tool_calls", []) if tc.get("error")]

    logger.info({
        "trace_id": trace_id,
        "session_id": request.session_id,
        "event": "turn_complete",
        "intent": intent,
        "confidence": round(confidence, 3),
        "tools": tools_used,
        "tool_errors": errors,
        "escalated": final_state.get("should_escalate", False),
        "latency_ms": latency_ms,
    })

    return ChatResponse(
        response=agent_response,
        session_id=request.session_id,
        intent=intent,
        confidence_score=confidence,
        tool_calls=tool_calls,
        session_state=final_state.get("session", {}),
        escalated=final_state.get("should_escalate", False),
    )


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    import asyncio
    loop = asyncio.get_event_loop()

    session_data = sessions.get(request.session_id, SessionState().to_dict())

    initial_state = {
        "messages": [HumanMessage(content=request.message)],
        "session": session_data,
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
        "streaming_mode": True,
        "response_prompt": None,
    }

    try:
        # Run blocking graph in thread pool so we don't block the event loop
        final_state = await loop.run_in_executor(None, agent.invoke, initial_state)
    except Exception as e:
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    sessions[request.session_id] = final_state.get("session", session_data)

    prompt_data = final_state.get("response_prompt") or {}
    tool_calls_raw = final_state.get("current_tool_calls", [])
    tool_calls_serializable = [
        {"tool": tc["tool"], "args": tc["args"], "result": tc.get("result"), "error": tc.get("error")}
        for tc in tool_calls_raw
    ]
    meta = {
        "type": "done",
        "intent": final_state.get("intent", "unknown"),
        "confidence": final_state.get("confidence_score", 0.0),
        "tool_calls": tool_calls_serializable,
        "session_state": final_state.get("session", {}),
        "escalated": final_state.get("should_escalate", False),
    }

    async def generate():
        if not prompt_data:
            yield f"data: {json.dumps({'type': 'token', 'content': 'Sorry, something went wrong.'})}\n\n"
            yield f"data: {json.dumps(meta)}\n\n"
            return

        _SENTINEL = object()
        queue: asyncio.Queue = asyncio.Queue()

        def stream_into_queue():
            try:
                stream = chat_stream_with_rotation(
                    model=get_model(),
                    messages=[
                        {"role": "system", "content": prompt_data["system"]},
                        {"role": "user", "content": prompt_data["user"]},
                    ],
                    temperature=0.3,
                    max_tokens=150,
                )
                for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        asyncio.run_coroutine_threadsafe(queue.put(content), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(queue.put(e), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(_SENTINEL), loop)

        loop.run_in_executor(None, stream_into_queue)

        has_content = False
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            if isinstance(item, Exception):
                logger.error(f"Stream failed: {item}")
                if not has_content:
                    has_content = True
                    fallback = _rule_based_fallback(final_state)
                    yield f"data: {json.dumps({'type': 'token', 'content': fallback})}\n\n"
                break
            has_content = True
            yield f"data: {json.dumps({'type': 'token', 'content': item})}\n\n"

        if not has_content:
            fallback = _rule_based_fallback(final_state)
            yield f"data: {json.dumps({'type': 'token', 'content': fallback})}\n\n"

        yield f"data: {json.dumps(meta, default=str)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
