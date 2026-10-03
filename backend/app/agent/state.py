from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


RouteName = Literal["general", "summarize", "support_reply"]


class AgentState(TypedDict, total=False):
    # add_messages appends new messages instead of overwriting the conversation.
    messages: Annotated[list[AnyMessage], add_messages]
    route: RouteName
    draft: str
    approved: bool
    action_result: str
