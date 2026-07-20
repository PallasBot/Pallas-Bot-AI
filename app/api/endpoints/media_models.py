from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import media_models

router = APIRouter(prefix="/media/models", tags=["media-models"])


class SingDefaultsBody(BaseModel):
    default_speaker: str | None = Field(default=None, max_length=64)
    preferred_backend: str | None = Field(
        default=None,
        max_length=64,
        description="优先 SVC backend；空字符串恢复 registry fallback_order",
    )


class TtsDefaultsBody(BaseModel):
    ref_audio_path: str | None = None
    prompt_text: str | None = None
    prompt_lang: str | None = None
    text_lang: str | None = None


@router.get("/sing/speakers")
async def sing_speakers() -> dict:
    return media_models.list_sing_speakers()


@router.get("/sing/backends")
async def sing_backends() -> dict:
    return media_models.list_svc_backends()


@router.get("/sing/defaults")
async def sing_defaults_get() -> dict:
    return media_models.get_sing_defaults()


@router.put("/sing/defaults")
async def sing_defaults_put(body: SingDefaultsBody) -> dict:
    try:
        return media_models.set_sing_defaults(
            default_speaker=body.default_speaker,
            preferred_backend=body.preferred_backend,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tts/voices")
async def tts_voices() -> dict:
    return media_models.list_tts_voices()


@router.get("/tts/defaults")
async def tts_defaults_get() -> dict:
    return media_models.get_tts_defaults()


@router.put("/tts/defaults")
async def tts_defaults_put(body: TtsDefaultsBody) -> dict:
    try:
        return media_models.set_tts_defaults(
            ref_audio_path=body.ref_audio_path,
            prompt_text=body.prompt_text,
            prompt_lang=body.prompt_lang,
            text_lang=body.text_lang,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
