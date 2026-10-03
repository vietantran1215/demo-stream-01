from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from .model import model
from .state import AgentState, RouteName


class RouteDecision(BaseModel):
    route: Literal["general", "support_reply"] = Field(
        description="The single workflow that should handle the latest user request."
    )


router_model = model.with_structured_output(RouteDecision)


async def router_node(state: AgentState, config: RunnableConfig) -> dict[str, RouteName]:
    """Route support-reply requests to the agent; everything else is general."""
    decision = await router_model.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "Classify the latest user request into exactly one route.\n"
                    "general: any normal question, conversation, explanation, summary, "
                    "or other request that does not require sending a customer-support reply.\n"
                    "support_reply: the user asks to draft, write, reply, respond, or send a "
                    "customer-facing support message.\n"
                    "Choose support_reply whenever the requested output is a customer-facing reply."
                ),
            },
            *state["messages"],
        ],
        config,
    )

    route = decision.route

    get_stream_writer()(
        {
            "type": "route_selected",
            "route": route,
        }
    )

    return {"route": route}
