from __future__ import annotations

import asyncio

import pytest

from app.services.vision_messages import (
    enrich_local_messages_for_vision,
    vision_user_plain_text,
)


def test_vision_user_plain_text_prefers_metadata() -> None:
    meta = {"vision_plain_text": "看看这个"}
    assert vision_user_plain_text(meta, "[CQ:image,url=https://x]") == "看看这个"


def test_enrich_local_messages_for_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(metadata):
        return ["ZmFrZQ=="]

    monkeypatch.setattr("app.services.vision_messages.fetch_vision_images", fake_fetch)
    monkeypatch.setattr("app.services.vision_messages.vision_model_for_provider", lambda _pid: "llava:7b")

    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "old"}]
    meta = {
        "has_image": True,
        "vision_image_urls": ["https://example.com/a.png"],
        "vision_plain_text": "这是什么",
    }

    async def run():
        return await enrich_local_messages_for_vision(
            messages,
            metadata=meta,
            user_text="[CQ:image,url=https://example.com/a.png] 这是什么",
            provider_id="local",
        )

    enriched = asyncio.run(run())
    assert enriched[-1]["content"] == "这是什么"
    assert enriched[-1]["images"] == ["ZmFrZQ=="]


def test_enrich_skips_without_vision_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.vision_messages.vision_model_for_provider", lambda _pid: "")
    messages = [{"role": "user", "content": "x"}]
    meta = {"has_image": True, "vision_image_urls": ["https://example.com/a.png"]}

    async def run():
        return await enrich_local_messages_for_vision(
            messages,
            metadata=meta,
            user_text="[CQ:image,url=https://example.com/a.png]",
            provider_id="local",
        )

    enriched = asyncio.run(run())
    assert enriched == messages
