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

# Router output is internal. Only root model calls from these deterministic
# nodes become assistant text. support_agent text is consumed from its subgraph.
ROOT_USER_FACING_MODEL_NODES = {"general", "summarize"}


def sse(event: str, data: object) -> str:
    """Encode one JSON payload as a Server-Sent Event frame."""
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def map_custom_event(custom: object) -> tuple[str, dict] | None:
    """Map domain-level custom events to the browser SSE contract."""
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


def normalize_hitl_interrupt(pending_interrupt: object) -> dict:
    """
    Keep the browser contract framework-agnostic.

    HumanInTheLoopMiddleware emits action_requests/review_configs. The React UI
    only needs the single proposed action and the message that would be sent.
    """
    interrupt_id = getattr(pending_interrupt, "id", "")
    value = getattr(pending_interrupt, "value", {})

    if not isinstance(value, dict):
        raise ValueError("Unexpected HITL interrupt payload.")

    action_requests = value.get("action_requests")
    if not isinstance(action_requests, list) or len(action_requests) != 1:
        raise ValueError("This demo expects exactly one tool call under review.")

    action = action_requests[0]
    if not isinstance(action, dict):
        raise ValueError("Unexpected HITL action request.")

    arguments = action.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}

    return {
        "id": interrupt_id,
        "value": {
            "action": action.get("name", "unknown"),
            "draft": arguments.get("message", ""),
        },
    }


async def stream_graph(input_value: object, thread_id: str) -> AsyncIterator[str]:
    """
    Adapt LangGraph Event Streaming v3 to a small SSE protocol.

    Root projections carry deterministic graph events. The support create_agent
    runs as a subgraph, so its model text and tool custom events are consumed
    from the nested subgraph handle.
    """
    config = {"configurable": {"thread_id": thread_id}}

    try:
        run = await graph.astream_events(
            input_value,
            config=config,
            version="v3",
        )

        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def emit_custom(custom: object) -> None:
            mapped = map_custom_event(custom)
            if mapped is not None:
                await queue.put(mapped)

        async def consume_root_messages() -> None:
            try:
                async for message in run.messages:
                    async for text in message.text:
                        if message.node in ROOT_USER_FACING_MODEL_NODES and text:
                            await queue.put(("token", {"content": text}))
            except Exception as exc:
                await queue.put(("__error__", exc))
            finally:
                await queue.put(("__done__", "root_messages"))

        async def consume_root_custom() -> None:
            try:
                async for custom in run.custom:
                    await emit_custom(custom)
            except Exception as exc:
                await queue.put(("__error__", exc))
            finally:
                await queue.put(("__done__", "root_custom"))

        async def consume_support_subgraph(subgraph: object) -> None:
            async def consume_messages() -> None:
                async for message in subgraph.messages:
                    async for text in message.text:
                        if text:
                            await queue.put(("token", {"content": text}))

            async def consume_custom() -> None:
                async for custom in subgraph.custom:
                    await emit_custom(custom)

            try:
                await asyncio.gather(
                    consume_messages(),
                    consume_custom(),
                )
            except Exception as exc:
                await queue.put(("__error__", exc))

        async def consume_subgraphs() -> None:
            tasks: list[asyncio.Task] = []

            try:
                async for subgraph in run.subgraphs:
                    tasks.append(
                        asyncio.create_task(
                            consume_support_subgraph(subgraph)
                        )
                    )

                if tasks:
                    await asyncio.gather(*tasks)
            except Exception as exc:
                await queue.put(("__error__", exc))
            finally:
                await queue.put(("__done__", "subgraphs"))

        async with run:
            consumers = [
                asyncio.create_task(consume_root_messages()),
                asyncio.create_task(consume_root_custom()),
                asyncio.create_task(consume_subgraphs()),
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
                normalize_hitl_interrupt(pending_interrupt),
            )

        yield sse("done", {"interrupted": interrupted})

    except Exception as exc:
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
    decision = (
        {"type": "approve"}
        if body.approved
        else {
            "type": "reject",
            "message": (
                "The user rejected this support reply. "
                "Do not call send_support_reply again unless the user explicitly asks."
            ),
        }
    )

    stream = stream_graph(
        Command(resume={"decisions": [decision]}),
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
