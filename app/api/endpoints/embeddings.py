from __future__ import annotations

import hashlib

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()


def _stub_embedding(text: str, *, dims: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    for i in range(dims):
        byte = digest[i % len(digest)]
        out.append((byte / 255.0) * 2.0 - 1.0)
    return out


@router.post("/v1/embeddings")
async def embeddings_endpoint(body: dict = Body(...)):
    raw_input = body.get("input")
    if isinstance(raw_input, str):
        inputs = [raw_input]
    elif isinstance(raw_input, list):
        inputs = [str(item) for item in raw_input]
    else:
        raise HTTPException(status_code=400, detail="input must be string or string[]")
    if not inputs:
        raise HTTPException(status_code=400, detail="input is empty")
    model = str(body.get("model") or "stub")
    data = [
        {
            "object": "embedding",
            "index": idx,
            "embedding": _stub_embedding(text),
        }
        for idx, text in enumerate(inputs)
    ]
    return {
        "object": "list",
        "model": model,
        "data": data,
        "usage": {"prompt_tokens": sum(len(text) for text in inputs), "total_tokens": sum(len(text) for text in inputs)},
    }
