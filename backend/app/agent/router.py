from typing import Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from .model import model
from .state import AgentState, RouteName


class RouteDecision(BaseModel):
    route: Literal["general", "summarize", "support_reply"] = Field(
        description="The single workflow that should handle the latest user request."
    )


router_model = model.with_structured_output(RouteDecision)


async def router_node(state: AgentState, config: RunnableConfig) -> dict[str, RouteName]:
    """Classify the latest request. The router does not answer the user."""
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

    return {"route": decision.route}
