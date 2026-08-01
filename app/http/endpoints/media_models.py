from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.media import models as media_models
from app.media.sing.ensure_backend import (
    describe_backend_install,
    ensure_job_status,
    ensure_svc_backend,
    schedule_ensure_svc_backend,
)

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


class TtsTranslatorBody(BaseModel):
    enable: bool | None = None
    provider: str | None = Field(default=None, max_length=16)
    baidu_app_id: str | None = None
    baidu_secret_key: str | None = None
    youdao_app_key: str | None = None
    youdao_app_secret: str | None = None


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


@router.post("/sing/backends/{backend_id}/ensure")
async def sing_backend_ensure(backend_id: str) -> dict:
    """按需拉取 DDSP-SVC 对应分支（约 1.6G）；已存在则直接返回。"""
    backend_id = (backend_id or "").strip()
    if not backend_id:
        raise HTTPException(status_code=400, detail="backend_id 不能为空")
    # 控制台点一次：后台拉，避免网关超时
    started = schedule_ensure_svc_backend(backend_id)
    if started.get("status") == "unsupported":
        # 非 DDSP 自动源：仍尝试同步探测（会明确报错）
        return ensure_svc_backend(backend_id)
    return started


@router.get("/sing/backends/{backend_id}/ensure")
async def sing_backend_ensure_status(backend_id: str) -> dict:
    backend_id = (backend_id or "").strip()
    job = ensure_job_status(backend_id)
    info = describe_backend_install(backend_id)
    return {"install": info, "job": job}


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


@router.get("/tts/translator")
async def tts_translator_get() -> dict:
    return media_models.get_tts_translator()


@router.put("/tts/translator")
async def tts_translator_put(body: TtsTranslatorBody) -> dict:
    try:
        return media_models.set_tts_translator(
            enable=body.enable,
            provider=body.provider,
            baidu_app_id=body.baidu_app_id,
            baidu_secret_key=body.baidu_secret_key,
            youdao_app_key=body.youdao_app_key,
            youdao_app_secret=body.youdao_app_secret,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
