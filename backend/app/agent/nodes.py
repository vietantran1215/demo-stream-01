from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from .model import model
from .state import AgentState


GENERAL_PROMPT = (
    "You are a concise technical assistant. Answer the user's latest request "
    "directly. Use Markdown when structure improves readability. "
    "Do not claim to have executed external actions."
)

SUMMARIZE_PROMPT = """
Summarize only the information supplied by the user.

Return these sections when the source supports them:
1. Main issue
2. Important facts
3. Impact
4. Next actions

Rules:
- Do not invent missing facts.
- Preserve concrete numbers, times, statuses, and named systems.
- Call out uncertainty explicitly.
- Keep the result concise.
""".strip()


async def general_node(state: AgentState, config: RunnableConfig) -> dict:
    """Handle normal questions with a direct model call."""
    response = await model.ainvoke(
        [SystemMessage(content=GENERAL_PROMPT), *state["messages"]],
        config,
    )
    return {"messages": [response]}


async def summarize_node(state: AgentState, config: RunnableConfig) -> dict:
    """Summarize user-provided content with a small inline system prompt."""
    response = await model.ainvoke(
        [SystemMessage(content=SUMMARIZE_PROMPT), *state["messages"]],
        config,
    )
    return {"messages": [response]}
