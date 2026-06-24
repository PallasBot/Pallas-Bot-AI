from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.llm_backend_runtime import get_llm_model, local_backend_chat_url
from app.core.logger import logger
from app.schemas.persona_affect import (
    AffectRefineRequest,
    AffectRefineResponse,
    AffectTriggerSuggestion,
)

_DELTA_CLAMP = 0.5
_CONFIDENCE_CLAMP = 1.0
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


class AffectRefineBackendSlots:
    slots: asyncio.Semaphore | None = None

    @classmethod
    def get(cls) -> asyncio.Semaphore:
        if cls.slots is None:
            limit = max(1, int(settings.persona_affect_refine_max_concurrent))
            cls.slots = asyncio.Semaphore(limit)
        return cls.slots


def clamp_delta(value: float) -> float:
    return max(-_DELTA_CLAMP, min(_DELTA_CLAMP, float(value)))


def clamp_confidence(value: float) -> float:
    return max(0.0, min(_CONFIDENCE_CLAMP, float(value)))


def sanitize_message_samples(samples: list[str], *, limit: int = 12, max_len: int = 120) -> list[str]:
    out: list[str] = []
    for raw in samples[:limit]:
        text = str(raw or "").strip().replace("\n", " ")
        if not text:
            continue
        if len(text) > max_len:
            text = text[: max_len - 1] + "…"
        out.append(text)
    return out


def build_affect_refine_user_prompt(request: AffectRefineRequest) -> str:
    derived = request.profile.derived
    raw = request.profile.raw
    tone = raw.affect_tone if raw is not None else None
    hints = [str(item).strip() for item in request.hints if str(item).strip()]
    samples = sanitize_message_samples(
        request.message_samples,
        limit=settings.persona_affect_refine_max_samples,
    )

    lines = [
        "请根据群聊统计与样本，在已有 warmth/assertiveness 基线之上给出小幅情感偏移。",
        "只输出 JSON 对象，字段：warmth_delta, assertiveness_delta, confidence, summary, triggers。",
        "triggers 可为空数组；|delta| 通常不超过 0.15。",
        "",
        f"group_id={request.group_id}",
    ]
    if derived is not None:
        lines.append(
            "derived: "
            f"warmth_bias={derived.warmth_bias}, assertiveness_bias={derived.assertiveness_bias}, "
            f"length_pref={derived.length_pref}, chaos_bias={derived.chaos_bias}"
        )
    if raw is not None:
        lines.append(f"raw: repeat_chain_rate={raw.repeat_chain_rate}, local_answer_ratio={raw.local_answer_ratio}")
    if tone is not None:
        lines.append(
            "affect_tone: "
            f"civility={tone.civility_score}, harsh_ratio={tone.harsh_msg_ratio}, "
            f"polite_ratio={tone.polite_msg_ratio}, punct={tone.punct_aggression_avg}"
        )
    if hints:
        lines.append("hints: " + "；".join(hints[:8]))
    if samples:
        lines.append("message_samples:")
        lines.extend(f"- {item}" for item in samples)
    return "\n".join(lines)


def parse_affect_refine_json(text: str) -> dict[str, Any]:
    body = str(text or "").strip()
    if not body:
        raise ValueError("empty model output")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(body)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


def normalize_affect_refine_payload(data: dict[str, Any]) -> AffectRefineResponse:
    triggers: list[AffectTriggerSuggestion] = []
    raw_triggers = data.get("triggers")
    if isinstance(raw_triggers, list):
        for item in raw_triggers[:8]:
            if not isinstance(item, dict):
                continue
            phrase = str(item.get("phrase") or "").strip()
            if not phrase:
                continue
            triggers.append(
                AffectTriggerSuggestion(
                    phrase=phrase[:64],
                    warmth_delta=clamp_delta(float(item.get("warmth_delta") or 0.0)),
                    assertiveness_delta=clamp_delta(float(item.get("assertiveness_delta") or 0.0)),
                    ttl_hours=int(item.get("ttl_hours") or 168),
                )
            )

    summary = str(data.get("summary") or "").strip()
    if len(summary) > 256:
        summary = summary[:255] + "…"

    return AffectRefineResponse(
        warmth_delta=clamp_delta(float(data.get("warmth_delta") or 0.0)),
        assertiveness_delta=clamp_delta(float(data.get("assertiveness_delta") or 0.0)),
        confidence=clamp_confidence(float(data.get("confidence") or 0.0)),
        summary=summary,
        triggers=triggers,
    )


def heuristic_affect_refine(request: AffectRefineRequest) -> AffectRefineResponse:
    """本地后端不可用时的保守回退：仅依据 civility 给极小 delta。"""
    tone = request.profile.raw.affect_tone if request.profile.raw is not None else None
    civility = float(tone.civility_score if tone is not None else 0.0)
    warmth_delta = clamp_delta(civility * 0.05)
    assertiveness_delta = clamp_delta(-civility * 0.04)
    if abs(warmth_delta) < 0.01 and abs(assertiveness_delta) < 0.01:
        return AffectRefineResponse(confidence=0.0, summary="样本信号不足，未调整")
    return AffectRefineResponse(
        warmth_delta=warmth_delta,
        assertiveness_delta=assertiveness_delta,
        confidence=0.35,
        summary="启发式回退：依据 civility 微调",
    )


async def call_local_backend_json(system_prompt: str, user_prompt: str) -> str:
    model = (settings.persona_affect_refine_model or "").strip() or get_llm_model()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": settings.persona_affect_refine_temperature},
    }
    timeout = httpx.Timeout(settings.persona_affect_refine_timeout_sec)
    async with AffectRefineBackendSlots.get(), httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(local_backend_chat_url(), json=payload)
        response.raise_for_status()
        body = response.json()
    message = body.get("message") if isinstance(body, dict) else None
    if isinstance(message, dict):
        content = str(message.get("content") or "").strip()
        if content:
            return content
    raise ValueError("local backend response missing message content")


async def refine_group_affect(request: AffectRefineRequest) -> AffectRefineResponse:
    if not settings.persona_affect_refine_enabled:
        raise RuntimeError("persona affect refine disabled")

    system_prompt = (
        "你是群聊语气分析助手。根据统计与脱敏样本，输出 JSON："
        '{"warmth_delta": number, "assertiveness_delta": number, '
        '"confidence": number, "summary": string, "triggers": []}。'
        "不要输出 markdown 或解释文字。"
    )
    user_prompt = build_affect_refine_user_prompt(request)

    if not settings.llm_chat_enabled:
        logger.warning("persona affect refine: llm backend disabled, using heuristic fallback")
        return heuristic_affect_refine(request)

    try:
        raw_text = await call_local_backend_json(system_prompt, user_prompt)
        payload = parse_affect_refine_json(raw_text)
        result = normalize_affect_refine_payload(payload)
        if result.confidence < settings.persona_affect_refine_min_confidence:
            logger.info(
                "persona affect refine low confidence={} group={}",
                result.confidence,
                request.group_id,
            )
        return result
    except Exception as exc:
        detail = str(exc).strip() or "(no message)"
        logger.warning(
            "persona affect refine failed group={}: {} {}",
            request.group_id,
            type(exc).__name__,
            detail,
        )
        return heuristic_affect_refine(request)
