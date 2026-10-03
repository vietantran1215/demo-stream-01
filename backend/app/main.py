import asyncio
import json
import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.agent.graph import graph
from app.schemas import ChatRequest, ResumeRequest


app = FastAPI(
    title="LangGraph Streaming HITL Demo",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# The router also calls an LLM, but its structured-output tokens are internal.
# Only these user-facing generation nodes should become SSE token events.
USER_FACING_MODEL_NODES = {"general", "summarize", "support_reply"}


def sse(event: str, data: object) -> str:
    """Encode one JSON payload as a Server-Sent Event frame."""
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def map_custom_event(custom: object) -> tuple[str, dict] | None:
    """Map domain-level LangGraph custom events to the browser SSE contract."""
    if not isinstance(custom, dict):
        return None

    custom_type = custom.get("type")

    if custom_type == "route_selected":
        return (
            "route",
            {
                "route": custom.get("route"),
                "expected_skill": custom.get("expected_skill"),
            },
        )

    if custom_type == "skill_loaded":
        return (
            "skill",
            {
                "name": custom.get("name"),
                "source": custom.get("source"),
            },
        )

    if custom_type == "skill_skipped":
        return (
            "skill_skipped",
            {
                "reason": custom.get("reason"),
            },
        )

    if custom_type in {"tool_started", "tool_progress", "tool_completed"}:
        return (
            "tool",
            {
                "phase": custom_type.removeprefix("tool_"),
                "tool": custom.get("tool"),
                "message": custom.get("message"),
                "progress": custom.get("progress"),
            },
        )

    return None


async def stream_graph(input_value: object, thread_id: str) -> AsyncIterator[str]:
    """
    Adapt LangGraph Event Streaming v3 to the app's small SSE protocol.

    Native projections have clear responsibilities:
    - run.messages: LLM text deltas
    - run.custom: route, skill and tool-progress domain events
    - run.interrupts: pending HITL requests after the run pauses
    """
    config = {"configurable": {"thread_id": thread_id}}

    try:
        run = await graph.astream_events(
            input_value,
            config=config,
            version="v3",
        )

        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def consume_messages() -> None:
            try:
                async for message in run.messages:
                    async for text in message.text:
                        # Do not leak structured-output/router model tokens into
                        # the end-user assistant message.
                        if message.node in USER_FACING_MODEL_NODES and text:
                            await queue.put(("token", {"content": text}))
            except Exception as exc:
                await queue.put(("__error__", exc))
            finally:
                await queue.put(("__done__", "messages"))

        async def consume_custom() -> None:
            try:
                async for custom in run.custom:
                    mapped = map_custom_event(custom)
                    if mapped is not None:
                        await queue.put(mapped)
            except Exception as exc:
                await queue.put(("__error__", exc))
            finally:
                await queue.put(("__done__", "custom"))

        async with run:
            consumers = [
                asyncio.create_task(consume_messages()),
                asyncio.create_task(consume_custom()),
            ]

            completed_consumers = 0
            stream_error: Exception | None = None

            while completed_consumers < len(consumers):
                event, data = await queue.get()

                if event == "__done__":
                    completed_consumers += 1
                    continue

                if event == "__error__":
                    if stream_error is None and isinstance(data, Exception):
                        stream_error = data
                    continue

                if stream_error is None:
                    yield sse(event, data)

            results = await asyncio.gather(*consumers, return_exceptions=True)

            if stream_error is not None:
                raise stream_error

            for result in results:
                if isinstance(result, Exception):
                    raise result

            interrupted = run.interrupted
            interrupts = list(run.interrupts)

        for pending_interrupt in interrupts:
            yield sse(
                "interrupt",
                {
                    "id": pending_interrupt.id,
                    "value": pending_interrupt.value,
                },
            )

        yield sse("done", {"interrupted": interrupted})

    except Exception as exc:
        # The HTTP stream may already be 200, so failures are application-level
        # SSE events. Do not emit "done" after an error; the client treats error
        # as terminal.
        yield sse("error", {"message": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat/{thread_id}")
async def chat(thread_id: str, body: ChatRequest) -> StreamingResponse:
    stream = stream_graph(
        {"messages": [HumanMessage(content=body.message)]},
        thread_id,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/{thread_id}/resume")
async def resume(thread_id: str, body: ResumeRequest) -> StreamingResponse:
    stream = stream_graph(
        Command(resume={"approved": body.approved}),
        thread_id,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
