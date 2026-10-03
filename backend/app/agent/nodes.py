from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

from app.skills.loader import load_skill

from .model import model
from .state import AgentState


async def general_node(state: AgentState, config: RunnableConfig) -> dict:
    """Handle requests that do not need a specialized skill."""
    get_stream_writer()(
        {
            "type": "skill_skipped",
            "reason": "The general route does not require a specialized skill.",
        }
    )

    response = await model.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are a concise technical assistant. Answer the user's latest request "
                    "directly. Use Markdown when structure improves readability. "
                    "Do not claim to have executed external actions."
                )
            ),
            *state["messages"],
        ],
        config,
    )
    return {"messages": [response]}


async def summarize_node(state: AgentState, config: RunnableConfig) -> dict:
    """Load the summarize skill only after the router selects this node."""
    skill_name = "summarize"
    skill = load_skill(skill_name)

    get_stream_writer()(
        {
            "type": "skill_loaded",
            "name": skill_name,
            "source": "skills/summarize/SKILL.md",
        }
    )

    response = await model.ainvoke(
        [SystemMessage(content=skill), *state["messages"]],
        config,
    )
    return {"messages": [response]}


def support_skill_node(state: AgentState) -> dict:
    """Resolve and announce the support skill before entering the agentic branch."""
    skill_name = "support-reply"
    load_skill(skill_name)

    get_stream_writer()(
        {
            "type": "skill_loaded",
            "name": skill_name,
            "source": "skills/support-reply/SKILL.md",
        }
    )

    return {}
