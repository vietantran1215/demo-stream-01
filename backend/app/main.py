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
from langraph.types import Command

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


def sse(event: str, data: object) -> str:
    """Encode one JSON payload as a Server-Sent Event frame."""
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def message_chunk_text(message: object) -> str:
    """Read only textual content from a streamed LangChain message chunk."""
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

    return ""


async def stream_graph(input_value: object, thread_id: str) -> AsyncIterator[str]:
    """Translate LangGraph stream parts into a tiny frontend-facing SSE protocol."""
    config = {"configurable": {"thread_id": thread_id}}

    try:
        async for part in graph.astream(
            input_value,
            config=config,
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            if part["type"] == "messages":
                message, metadata = part["data"]

                # Router model tokens are implementation detail, not user output.
                if metadata.get("langgraph_node") == "router":
                    continue

                chunk = message_chunk_text(message)
                if chunk:
                    yield sse("token", {"content": chunk})

            elif part["type"] == "updates":
                for node_name, update in part["data"].items():
                    yield sse("node", {"name": node_name})

                    if node_name == "send" and isinstance(update, dict):
                        result = update.get("action_result")
                        if result:
                            yield sse("action", {"message": result})

        # A normal stream ends when the graph either finishes or pauses.
        # Inspect checkpoint tasks to surface pending HITL interrupts.
        snapshot = await graph.aget_state(config)
        interrupted = False

        for task in snapshot.tasks:
            for pending_interrupt in task.interrupts:
                interrupted = True
                yield sse(
                    "interrupt",
                    {
                        "id": pending_interrupt.id,
                        "value": pending_interrupt.value,
                    },
                )

        yield sse("done", {"interrupted": interrupted})

    except Exception as exc:
        # Keep the demo debuggable without leaking stack traces through the API.
        yield sse("error", {"message": str(exc)})
        yield sse("done", {"interrupted": False})


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
