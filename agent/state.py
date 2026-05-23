"""Agent and session state definitions."""

from typing import TypedDict, Annotated, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    session: dict
    tool_to_call: Optional[str]
    tool_args: Optional[dict]
    tool_result: Optional[dict]
    needs_secondary_tool: bool
    secondary_tool: Optional[str]
    secondary_args: Optional[dict]
    secondary_result: Optional[dict]
    needs_clarification: bool
    clarification_message: Optional[str]
    should_escalate: bool
    confidence_score: float
    current_tool_calls: List[dict]
    error: Optional[str]
    streaming_mode: bool
    response_prompt: Optional[dict]


@dataclass
class SessionState:
    buyer_name: Optional[str] = None
    stage: str = "discovery"
    active_product: Optional[dict] = None
    active_order_id: Optional[str] = None
    cart: List[dict] = field(default_factory=list)
    payment_preference: Optional[str] = None
    pending_size: Optional[str] = None
    delivery_address: Optional[str] = None
    pending_clarification: Optional[str] = None
    tool_call_history: List[dict] = field(default_factory=list)
    turn_count: int = 0
    recent_messages: List[dict] = field(default_factory=list)
    last_shown_products: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "buyer_name": self.buyer_name,
            "stage": self.stage,
            "active_product": self.active_product,
            "active_order_id": self.active_order_id,
            "cart": self.cart,
            "payment_preference": self.payment_preference,
            "pending_size": self.pending_size,
            "delivery_address": self.delivery_address,
            "pending_clarification": self.pending_clarification,
            "turn_count": self.turn_count,
            "recent_messages": self.recent_messages[-10:],
            "last_shown_products": self.last_shown_products,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        state = cls()
        for key, value in data.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state

    def update_after_turn(self, user_msg: str, agent_response: str, tool_calls: List[dict]) -> None:
        self.turn_count += 1
        self.recent_messages.append({
            "user": user_msg,
            "agent": agent_response,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self.recent_messages) > 10:
            self.recent_messages.pop(0)

        self.tool_call_history.extend(tool_calls)

        for call in tool_calls:
            result = call.get("result", {})
            if call["tool"] in ("search_catalog", "use_session_data") and result:
                if isinstance(result, list) and len(result) == 1:
                    self.active_product = result[0]
                    self.last_shown_products = result  # keep last_shown current for follow-up turns
                elif isinstance(result, list) and len(result) > 1:
                    args = call.get("args", {}) or {}
                    # Size-only filter on existing results: user already selected a product,
                    # don't clear active_product just because filtered list has many items
                    if not (call["tool"] == "use_session_data" and args.get("size") and not args.get("product_id")):
                        self.active_product = None
                    self.last_shown_products = result
            elif call["tool"] == "get_product" and result:
                self.active_product = result
            elif call["tool"] == "create_order" and result and result.get("order_id"):
                self.active_order_id = result["order_id"]
                self.stage = "post_order"
            elif call["tool"] == "get_order" and result and isinstance(result, dict) and result.get("order_id"):
                self.active_order_id = result.get("order_id") or call.get("args", {}).get("order_id")
                self.stage = "post_order"
