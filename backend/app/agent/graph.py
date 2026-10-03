from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import general_node, summarize_node, support_skill_node
from .router import router_node
from .state import AgentState, RouteName
from .support_agent import support_agent


def route_after_router(state: AgentState) -> RouteName:
    return state["route"]


builder = StateGraph(AgentState)

builder.add_node("router", router_node)
builder.add_node("general", general_node)
builder.add_node("summarize", summarize_node)
builder.add_node("support_skill", support_skill_node)

# create_agent returns a compiled LangGraph. Because both graphs share the
# messages state key, it can be embedded directly as a subgraph node.
builder.add_node("support_agent", support_agent)

builder.add_edge(START, "router")

builder.add_conditional_edges(
    "router",
    route_after_router,
    {
        "general": "general",
        "summarize": "summarize",
        "support_reply": "support_skill",
    },
)

builder.add_edge("general", END)
builder.add_edge("summarize", END)
builder.add_edge("support_skill", "support_agent")
builder.add_edge("support_agent", END)

# The support-agent subgraph intentionally has no checkpointer of its own.
# It inherits this parent checkpointer for HITL pause/resume within each call.
graph = builder.compile(checkpointer=InMemorySaver())
