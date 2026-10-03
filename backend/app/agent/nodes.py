import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from app.skills.loader import load_skill

from .model import model
from .state import AgentState


OUTBOX_PATH = Path(__file__).resolve().parents[2] / "data" / "outbox.jsonl"


def message_text(message: object) -> str:
    """Normalize LangChain text content into a plain string."""
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


async def stream_model(messages: list, config: RunnableConfig) -> AIMessage:
    """
    Stream the provider response explicitly and mirror every text chunk into
    LangGraph's custom stream channel.

    Why not rely only on stream_mode="messages"?
    Custom OpenAI-compatible gateways can behave differently around callback
    propagation. Explicit model.astream() makes the streaming boundary visible
    and deterministic for this teaching demo.
    """
    writer = get_stream_writer()
    parts: list[str] = []

    async for chunk in model.astream(messages, config):
        text = message_text(chunk)
        if not text:
            continue

        parts.append(text)

        # The FastAPI layer subscribes to stream_mode="custom" and converts
        # this payload into an SSE "token" event for the browser.
        writer(
            {
                "type": "token",
                "content": text,
            }
        )

    return AIMessage(content="".join(parts))


async def general_node(state: AgentState, config: RunnableConfig) -> dict:
    """Handle requests that do not need a specialized skill."""
    writer = get_stream_writer()
    writer(
        {
            "type": "skill_skipped",
            "reason": "The general route does not require a specialized skill.",
        }
    )

    response = await stream_model(
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

    # Emit this only after the file was actually loaded successfully.
    get_stream_writer()(
        {
            "type": "skill_loaded",
            "name": skill_name,
            "source": "skills/summarize/SKILL.md",
        }
    )

    response = await stream_model(
        [SystemMessage(content=skill), *state["messages"]],
        config,
    )
    return {"messages": [response]}


async def support_reply_node(state: AgentState, config: RunnableConfig) -> dict:
    """Generate a customer-facing draft but do not execute the side effect."""
    skill_name = "support-reply"
    skill = load_skill(skill_name)

    # Emit this only after the file was actually loaded successfully.
    get_stream_writer()(
        {
            "type": "skill_loaded",
            "name": skill_name,
            "source": "skills/support-reply/SKILL.md",
        }
    )

    response = await stream_model(
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


async def send_reply_node(state: AgentState) -> dict[str, str]:
    """
    Demo-only fake tool.

    Simulate a three-second external operation and stream progress while it is
    running. Only after the simulated work completes do we execute the side
    effect by appending the approved draft to the local outbox.
    """
    writer = get_stream_writer()
    tool_name = "send_support_reply"
    total_steps = 3

    writer(
        {
            "type": "tool_started",
            "tool": tool_name,
            "message": "Starting fake support-reply send",
            "progress": 0,
        }
    )

    for step in range(1, total_steps + 1):
        # asyncio.sleep keeps the event loop free, so progress is delivered to
        # the browser while the fake tool is still running.
        await asyncio.sleep(1)

        # 100% is reserved for a successfully completed side effect.
        progress = step * 30
        writer(
            {
                "type": "tool_progress",
                "tool": tool_name,
                "message": f"Processing step {step}/{total_steps}",
                "progress": progress,
            }
        )

    OUTBOX_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "message": state["draft"],
    }

    with OUTBOX_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    writer(
        {
            "type": "tool_completed",
            "tool": tool_name,
            "message": "Reply written to data/outbox.jsonl",
            "progress": 100,
        }
    )

    return {"action_result": "Reply written to data/outbox.jsonl"}
