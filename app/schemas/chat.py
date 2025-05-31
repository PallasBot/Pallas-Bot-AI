from pydantic import BaseModel


class ChatRequest(BaseModel):
    session: str
    text: str
    token_count: int
    tts: bool


class ChatResponse(BaseModel):
    task_id: str
    status: str
