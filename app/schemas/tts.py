from pydantic import BaseModel


class TTSRequest(BaseModel):
    text: str


class TTSResponse(BaseModel):
    task_id: str
    status: str
