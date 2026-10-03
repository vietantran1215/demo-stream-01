import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.skills.loader import load_skill

from .model import model
from .state import AgentState


OUTBOX_PATH = Path(__file__).resolve().parents[2] / "data" / "outbox.jsonl"


def message_text(message: object) -> str:
    """Normalize LangChain text content into a plain string for state/storage."""
    text = getattr(message, "text", None)
    if isinstance(text, str):
        return text

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)

    return str(content)


async def general_node(state: AgentState, config: RunnableConfig) -> dict:
    """Handle requests that do not need a specialized skill."""
    response = await model.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are a concise technical assistant. Answer the user's latest request "
                    "directly. Do not claim to have executed external actions."
                )
            ),
            *state["messages"],
        ],
        config,
    )
    return {"messages": [response]}


async def summarize_node(state: AgentState, config: RunnableConfig) -> dict:
    """Load the summarize skill only after the router selects this node."""
    skill = load_skill("summarize")
    response = await model.ainvoke(
        [SystemMessage(content=skill), *state["messages"]],
        config,
    )
    return {"messages": [response]}


async def support_reply_node(state: AgentState, config: RunnableConfig) -> dict:
    """Generate a customer-facing draft but do not execute the side effect."""
    skill = load_skill("support-reply")
    response = await model.ainvoke(
        [SystemMessage(content=skill), *state["messages"]],
        config,
    )
    return {
        "messages": [response],
        "draft": message_text(response),
    }


def approval_node(state: AgentState) -> dict[str, bool]:
    """
    Pause the graph until a human approves or rejects the generated draft.

    LangGraph re-runs this node from the beginning when execution resumes, so no
    irreversible side effect is allowed before interrupt().
    """
    decision = interrupt(
        {
            "type": "approval_required",
            "action": "send_support_reply",
            "draft": state["draft"],
        }
    )

    if not isinstance(decision, dict) or not isinstance(decision.get("approved"), bool):
        raise ValueError("Resume payload must contain an 'approved' boolean.")

    return {"approved": decision["approved"]}


def send_reply_node(state: AgentState) -> dict[str, str]:
    """Demo-only fake send: append the approved draft to a local JSONL outbox."""
    OUTBOX_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "message": state["draft"],
    }

    with OUTBOX_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {"action_result": "Reply written to data/outbox.jsonl"}
