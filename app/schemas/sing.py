from pydantic import BaseModel


class SingRequest(BaseModel):
    speaker: str
    song_id: int
    sing_length: int
    chunk_index: int
    key: int


class RequestMusicRequest(BaseModel):
    song_id: int


class SingResponse(BaseModel):
    task_id: str
    status: str
