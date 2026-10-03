import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import tool
from langgraph.config import get_stream_writer

from app.skills.loader import load_skill

from .model import model


OUTBOX_PATH = Path(__file__).resolve().parents[2] / "data" / "outbox.jsonl"

SUPPORT_SKILL = load_skill("support-reply")

SUPPORT_AGENT_PROMPT = f"""{SUPPORT_SKILL}

Agent behavior:

- Every request routed to you is a customer-support reply task.
- Draft exactly one customer-facing reply from the user's supplied facts.
- Call send_support_reply exactly once with that draft.
- The tool call is only a proposed side effect until human approval is granted.
- Never claim the reply was sent before the tool succeeds.
- If the human rejects the tool call, acknowledge that it was not sent and do not retry.
- After a successful tool result, confirm briefly that the reply was sent.
"""


@tool
async def send_support_reply(message: str) -> str:
    """Send one approved customer-support reply.

    The tool simulates a three-second external operation, streams progress, and
    writes the approved message to the demo JSONL outbox.
    """
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
        "message": message,
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

    return "Reply sent successfully."


support_agent = create_agent(
    model=model,
    tools=[send_support_reply],
    system_prompt=SUPPORT_AGENT_PROMPT,
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "send_support_reply": {
                    "allowed_decisions": ["approve", "reject"],
                }
            }
        )
    ],
    name="support_agent",
)
