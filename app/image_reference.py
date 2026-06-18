from __future__ import annotations

import asyncio
import base64

import httpx

from app.core.logger import logger
from app.schemas.image_api import ImageArtifact

DEFAULT_REF_USER_AGENT = "curl/8.5.0"

PLATFORM_REFERENCE_HOST_TOKENS = (
    "qpic.cn",
    "qlogo.cn",
    "qq.com",
    "multimedia.nt.qq.com.cn",
)


def is_platform_reference_url(url: str) -> bool:
    lower = (url or "").lower()
    return any(token in lower for token in PLATFORM_REFERENCE_HOST_TOKENS)


def reference_request_headers(url: str) -> dict[str, str]:
    headers: dict[str, str] = {"User-Agent": DEFAULT_REF_USER_AGENT}
    lower = (url or "").lower()
    if any(token in lower for token in PLATFORM_REFERENCE_HOST_TOKENS):
        headers.setdefault("Referer", "https://qun.qq.com/")
    return headers


def decode_inline_image_reference(value: str) -> bytes | None:
    t = (value or "").strip()
    if not t:
        return None
    if t.startswith("data:") and ";base64," in t:
        try:
            raw = t.split(";base64,", 1)[1]
            return base64.b64decode(raw, validate=True)
        except (ValueError, TypeError):
            return None
    return None


async def download_reference_blob(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout_sec: float,
) -> bytes | None:
    u = (url or "").strip()
    if not u:
        return None
    inline = decode_inline_image_reference(u)
    if inline is not None:
        return inline
    if u.startswith("base64://"):
        try:
            return base64.b64decode(u[9:], validate=True)
        except (ValueError, TypeError):
            return None
    if not u.startswith(("http://", "https://")):
        return None
    if is_platform_reference_url(u):
        logger.warning(
            "image ref rejects platform url (expect bot inline): url={}",
            u[:160],
        )
        return None
    try:
        response = await client.get(
            u,
            headers=reference_request_headers(u),
            timeout=httpx.Timeout(timeout_sec, connect=min(15.0, timeout_sec)),
        )
        if response.status_code == 200 and response.content:
            return response.content
        logger.warning(
            "image ref download non-200 url={} status={}",
            u[:160],
            response.status_code,
        )
    except httpx.HTTPError as exc:
        logger.warning("image ref download failed url={} err={}", u[:160], exc)
    return None


async def download_reference_blobs(
    client: httpx.AsyncClient,
    ref_urls: list[str],
    *,
    timeout_sec: float,
) -> list[bytes]:
    if not ref_urls:
        return []

    async def one(url: str) -> bytes | None:
        return await download_reference_blob(client, url, timeout_sec=timeout_sec)

    results = await asyncio.gather(*(one(u) for u in ref_urls))
    return [blob for blob in results if blob]


def extract_image_fields(data: object) -> tuple[str | None, str | None]:
    if not isinstance(data, dict):
        return None, None
    items = data.get("data")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            url = first.get("url")
            b64 = first.get("b64_json")
            return (
                str(url).strip() if isinstance(url, str) and url.strip() else None,
                str(b64).strip() if isinstance(b64, str) and b64.strip() else None,
            )
    inner = data.get("data")
    if isinstance(inner, dict):
        url = inner.get("url")
        b64 = inner.get("b64_json")
        return (
            str(url).strip() if isinstance(url, str) and url.strip() else None,
            str(b64).strip() if isinstance(b64, str) and b64.strip() else None,
        )
    url = data.get("url")
    b64 = data.get("b64_json")
    return (
        str(url).strip() if isinstance(url, str) and url.strip() else None,
        str(b64).strip() if isinstance(b64, str) and b64.strip() else None,
    )


async def artifact_from_upstream_json(
    client: httpx.AsyncClient,
    data: object,
    *,
    timeout_sec: float,
) -> ImageArtifact:
    remote_url, raw_b64 = extract_image_fields(data)
    if raw_b64:
        base64.b64decode(raw_b64, validate=True)
        return ImageArtifact(mime_type="image/png", b64_data=raw_b64)
    if remote_url:
        inline = decode_inline_image_reference(remote_url)
        if inline is not None:
            encoded = base64.b64encode(inline).decode("ascii")
            return ImageArtifact(mime_type="image/png", b64_data=encoded)
        blob = await download_reference_blob(client, remote_url, timeout_sec=timeout_sec)
        if blob:
            encoded = base64.b64encode(blob).decode("ascii")
            return ImageArtifact(mime_type="image/png", b64_data=encoded)
    raise ValueError("missing image data in upstream response")
