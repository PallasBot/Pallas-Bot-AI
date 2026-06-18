"""含图消息：拉取 URL 并组装 Ollama 多模态 messages。"""

from __future__ import annotations

import base64
import re
from typing import Any

import httpx

from app.core.logger import logger
from app.providers.categorizer import needs_vision_for_request
from app.providers.router import vision_model_for_provider

_CQ_VISION_SEGMENT_RE = re.compile(r"\[CQ:(?:image|mface)[^\]]*\]", re.IGNORECASE)
_DEFAULT_VISION_PROMPT = "请看看这张图。"
_VISION_FETCH_TIMEOUT_SEC = 15.0
_VISION_MAX_BYTES = 8_000_000
_VISION_MAX_IMAGES = 3


def should_enrich_local_vision_messages(
    metadata: dict[str, Any] | None,
    *,
    user_text: str,
    provider_id: str,
) -> bool:
    if not needs_vision_for_request(user_text, metadata=metadata):
        return False
    if not vision_model_for_provider(provider_id):
        return False
    meta = metadata if isinstance(metadata, dict) else {}
    urls = meta.get("vision_image_urls")
    return isinstance(urls, list) and bool(urls)


def vision_user_plain_text(metadata: dict[str, Any] | None, user_text: str) -> str:
    meta = metadata if isinstance(metadata, dict) else {}
    plain = str(meta.get("vision_plain_text") or "").strip()
    if plain:
        return plain
    raw = str(user_text or "")
    if _CQ_VISION_SEGMENT_RE.search(raw):
        plain = _CQ_VISION_SEGMENT_RE.sub(" ", raw)
        plain = re.sub(r"\s+", " ", plain).strip()
        if plain:
            return plain
    return _DEFAULT_VISION_PROMPT


async def fetch_image_base64(url: str) -> str | None:
    target = str(url or "").strip()
    if not target.lower().startswith(("http://", "https://")):
        return None
    try:
        timeout = httpx.Timeout(_VISION_FETCH_TIMEOUT_SEC)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(target)
        if response.status_code != 200:
            logger.warning("vision image fetch non-200 url={} status={}", target[:160], response.status_code)
            return None
        data = response.content
        if not data or len(data) > _VISION_MAX_BYTES:
            logger.warning("vision image fetch size rejected url={} bytes={}", target[:160], len(data))
            return None
        return base64.b64encode(data).decode("ascii")
    except httpx.HTTPError as exc:
        logger.warning("vision image fetch failed url={} err={}", target[:160], exc)
        return None


async def fetch_vision_images(metadata: dict[str, Any] | None) -> list[str]:
    meta = metadata if isinstance(metadata, dict) else {}
    raw_urls = meta.get("vision_image_urls")
    if not isinstance(raw_urls, list):
        return []
    images: list[str] = []
    for item in raw_urls[:_VISION_MAX_IMAGES]:
        encoded = await fetch_image_base64(str(item or ""))
        if encoded:
            images.append(encoded)
    return images


async def enrich_local_messages_for_vision(
    messages: list[dict[str, Any]],
    *,
    metadata: dict[str, Any] | None,
    user_text: str,
    provider_id: str,
) -> list[dict[str, Any]]:
    if not should_enrich_local_vision_messages(metadata, user_text=user_text, provider_id=provider_id):
        return messages
    images = await fetch_vision_images(metadata)
    if not images:
        return messages

    working = [dict(item) for item in messages]
    plain = vision_user_plain_text(metadata, user_text)
    target_idx = None
    for index in range(len(working) - 1, -1, -1):
        if str(working[index].get("role") or "").strip().lower() == "user":
            target_idx = index
            break
    payload: dict[str, Any] = {"role": "user", "content": plain, "images": images}
    if target_idx is None:
        working.append(payload)
    else:
        working[target_idx] = payload
    logger.info("vision messages enriched: images={} plain_len={}", len(images), len(plain))
    return working
