from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class ResumeRequest(BaseModel):
    approved: bool
