from pydantic import BaseModel, Field


class OllamaChatRequest(BaseModel):
    session: str
    text: str
    system_prompt: str = Field(min_length=1)
    model: str | None = None


class OllamaResponse(BaseModel):
    task_id: str
    status: str


class OllamaModelResponse(BaseModel):
    model: str


class OllamaModelUpdateRequest(BaseModel):
    model: str = Field(min_length=1)
    pull: bool = True
