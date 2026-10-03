from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


RouteName = Literal["general", "summarize", "support_reply"]


class AgentState(TypedDict, total=False):
    # The parent graph and create_agent subgraph communicate through messages.
    messages: Annotated[list[AnyMessage], add_messages]
    route: RouteName
