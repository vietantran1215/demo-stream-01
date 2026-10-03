import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from app.skills.loader import load_skill

from .model import model
from .state import AgentState


OUTBOX_PATH = Path(__file__).resolve().parents[2] / "data" / "outbox.jsonl"


def message_text(message: object) -> str:
    """Normalize LangChain message content into a plain string."""
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
    get_stream_writer()(
        {
            "type": "skill_skipped",
            "reason": "The general route does not require a specialized skill.",
        }
    )

    # LangGraph's messages/event stream surfaces model tokens even though this
    # node uses ainvoke(). The node stays responsible for the final AIMessage;
    # the transport layer is responsible for streaming its deltas.
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


async def support_reply_node(state: AgentState, config: RunnableConfig) -> dict:
    """Generate a customer-facing draft but do not execute the side effect."""
    skill_name = "support-reply"
    skill = load_skill(skill_name)

    get_stream_writer()(
        {
            "type": "skill_loaded",
            "name": skill_name,
            "source": "skills/support-reply/SKILL.md",
        }
    )

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
    Pause this deterministic workflow until a human approves or rejects.

    HumanInTheLoopMiddleware is designed for create_agent tool calls. This
    graph has an explicit support_reply -> approval -> send path, so direct
    interrupt() is the smaller and more precise primitive.
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


async def send_reply_node(state: AgentState) -> dict[str, str]:
    """Demo-only fake tool with observable three-second progress."""
    writer = get_stream_writer()
    tool_name = "send_support_reply"

    writer(
        {
            "type": "tool_started",
            "tool": tool_name,
            "message": "Starting fake support-reply send",
            "progress": 0,
        }
    )

    for step in range(1, 4):
        # Non-blocking sleep lets the custom event stream flush progress while
        # the operation is still running.
        await asyncio.sleep(1)

        writer(
            {
                "type": "tool_progress",
                "tool": tool_name,
                "message": f"Processing step {step}/3",
                "progress": step * 30,
            }
        )

    OUTBOX_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "message": state["draft"],
    }

    with OUTBOX_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 100% means the side effect itself succeeded, not merely that the timer
    # finished.
    writer(
        {
            "type": "tool_completed",
            "tool": tool_name,
            "message": "Reply written to data/outbox.jsonl",
            "progress": 100,
        }
    )

    return {"action_result": "Reply written to data/outbox.jsonl"}
