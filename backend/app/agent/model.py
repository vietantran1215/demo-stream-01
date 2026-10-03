import os

from langchain_openai import ChatOpenAI


# GPT-6 Luna tool calling through Chat Completions requires reasoning disabled.
# Keeping this explicit also avoids unsupported sampling-parameter combinations.
model = ChatOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL") or None,
    model=os.getenv("OPENAI_MODEL", "gpt-6-luna"),
    # reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "none"),
)
