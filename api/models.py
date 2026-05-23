from __future__ import annotations
"""Pydantic models for API requests and responses."""

from pydantic import BaseModel
from typing import Optional, Any


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ToolCallInfo(BaseModel):
    tool: str
    args: dict
    result: Optional[Any] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: str
    confidence_score: float
    tool_calls: list[ToolCallInfo]
    session_state: dict
    escalated: bool


class EvalRequest(BaseModel):
    test_case_ids: Optional[list[str]] = None


class EvalResult(BaseModel):
    total_tests: int
    task_completion: dict
    tool_hallucination: dict
    invalid_tool_use: dict
    graceful_failure: dict
    details: list[dict]
