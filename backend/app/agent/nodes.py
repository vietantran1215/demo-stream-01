from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from .model import model
from .state import AgentState


GENERAL_PROMPT = (
    "You are a concise technical assistant. Answer the user's latest request "
    "directly. Use Markdown when structure improves readability. "
    "If the user asks for a summary, summarize the supplied content directly. "
    "Do not claim to have executed external actions."
)


async def general_node(state: AgentState, config: RunnableConfig) -> dict:
    """Handle every request that does not need the support-send agent."""
    response = await model.ainvoke(
        [SystemMessage(content=GENERAL_PROMPT), *state["messages"]],
        config,
    )
    return {"messages": [response]}
