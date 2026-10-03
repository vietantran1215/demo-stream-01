from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from .model import model
from .state import AgentState, RouteName


class RouteDecision(BaseModel):
    route: Literal["general", "summarize", "support_reply"] = Field(
        description="The single workflow that should handle the latest user request."
    )


ROUTE_TO_SKILL: dict[RouteName, str | None] = {
    "general": None,
    "summarize": "summarize",
    "support_reply": "support-reply",
}

router_model = model.with_structured_output(RouteDecision)


async def router_node(state: AgentState, config: RunnableConfig) -> dict[str, RouteName]:
    """Classify the latest request and expose the decision through the custom stream."""
    decision = await router_model.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "Classify the latest user request into exactly one route.\n"
                    "general: normal question or conversation.\n"
                    "summarize: user explicitly asks to summarize supplied content.\n"
                    "support_reply: user asks to draft, write, reply, respond, or send a "
                    "customer-support message.\n"
                    "Choose support_reply whenever the requested output is a customer-facing reply."
                ),
            },
            *state["messages"],
        ],
        config,
    )

    route = decision.route
    writer = get_stream_writer()

    # This event explains the router's decision before the target node starts.
    writer(
        {
            "type": "route_selected",
            "route": route,
            "expected_skill": ROUTE_TO_SKILL[route],
        }
    )

    return {"route": route}
