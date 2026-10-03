import os

from langchain_openai import ChatOpenAI


# One shared model instance is enough for this demo.
# Override OPENAI_MODEL in .env without touching application code.
model = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
    temperature=0,
)
