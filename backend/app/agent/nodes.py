from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

from .model import model
from .state import AgentState


GENERAL_PROMPT = (
    "You are a concise technical assistant. Answer the user's latest request "
    "directly. Use Markdown when structure improves readability. "
    "If the user asks for a summary, summarize the supplied content directly. "
    "Do not claim to have executed external actions."
)


def chunk_text(chunk: object) -> str:
    """Normalize a streamed chat-model chunk into plain user-facing text."""
    content = getattr(chunk, "content", "")

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


async def general_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Stream the model explicitly, then return one final AIMessage to graph state.

    This path deliberately demonstrates model-level streaming with
    model.astream(). The FastAPI adapter receives each chunk through
    get_stream_writer() rather than through the graph's messages projection.
    """
    writer = get_stream_writer()
    text_parts: list[str] = []

    async for chunk in model.astream(
        [SystemMessage(content=GENERAL_PROMPT), *state["messages"]],
        config,
    ):
        text = chunk_text(chunk)
        if not text:
            continue

        text_parts.append(text)
        writer(
            {
                "type": "model_token",
                "content": text,
                "source": "model_astream",
            }
        )

    return {"messages": [AIMessage(content="".join(text_parts))]}
