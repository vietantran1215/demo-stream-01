from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import general_node, summarize_node
from .router import router_node
from .state import AgentState, RouteName
from .support_agent import support_agent


def route_after_router(state: AgentState) -> RouteName:
    return state["route"]


builder = StateGraph(AgentState)

builder.add_node("router", router_node)
builder.add_node("general", general_node)
builder.add_node("summarize", summarize_node)

# create_agent returns a compiled LangGraph. The parent graph and this subgraph
# share the messages state key, so the agent can be embedded directly.
builder.add_node("support_agent", support_agent)

builder.add_edge(START, "router")

builder.add_conditional_edges(
    "router",
    route_after_router,
    {
        "general": "general",
        "summarize": "summarize",
        "support_reply": "support_agent",
    },
)

builder.add_edge("general", END)
builder.add_edge("summarize", END)
builder.add_edge("support_agent", END)

# Demo-only persistence. The support-agent subgraph inherits this parent
# checkpointer so HITL pause/resume works under the same thread_id.
graph = builder.compile(checkpointer=InMemorySaver())
