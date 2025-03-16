from pydantic import BaseModel


class SingRequest(BaseModel):
    speaker: str
    song_id: int
    sing_length: int
    chunk_index: int
    key: int


class SingResponse(BaseModel):
    task_id: str
    status: str
