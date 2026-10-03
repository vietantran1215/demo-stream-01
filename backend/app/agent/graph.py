from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    approval_node,
    general_node,
    send_reply_node,
    summarize_node,
    support_reply_node,
)
from .router import router_node
from .state import AgentState, RouteName


def route_after_router(state: AgentState) -> RouteName:
    return state["route"]


def route_after_approval(state: AgentState) -> str:
    return "send" if state.get("approved") else "reject"


builder = StateGraph(AgentState)

builder.add_node("router", router_node)
builder.add_node("general", general_node)
builder.add_node("summarize", summarize_node)
builder.add_node("support_reply", support_reply_node)
builder.add_node("approval", approval_node)
builder.add_node("send", send_reply_node)

builder.add_edge(START, "router")

builder.add_conditional_edges(
    "router",
    route_after_router,
    {
        "general": "general",
        "summarize": "summarize",
        "support_reply": "support_reply",
    },
)

builder.add_edge("general", END)
builder.add_edge("summarize", END)
builder.add_edge("support_reply", "approval")

builder.add_conditional_edges(
    "approval",
    route_after_approval,
    {
        "send": "send",
        "reject": END,
    },
)

builder.add_edge("send", END)

# Demo-only persistence. Use a durable checkpointer in production.
graph = builder.compile(checkpointer=InMemorySaver())
