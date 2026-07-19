from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.endpoints import persona_affect as persona_affect_endpoint
from app.core.config import settings
from app.main import app
from app.schemas.persona_affect import AffectRefineProfile, AffectRefineProfileDerived, AffectRefineRequest
from app.services.persona_affect import (
    build_affect_refine_user_prompt,
    heuristic_affect_refine,
    normalize_affect_refine_payload,
    parse_affect_refine_json,
    sanitize_message_samples,
)


def test_sanitize_message_samples_truncates() -> None:
    samples = sanitize_message_samples(["  hello  ", "x" * 200], max_len=10)
    assert samples[0] == "hello"
    assert samples[1].endswith("…")


def test_parse_affect_refine_json_from_markdown_block() -> None:
    payload = parse_affect_refine_json(
        '说明\n```json\n{"warmth_delta": 0.1, "assertiveness_delta": -0.05, "confidence": 0.7, "summary": "ok"}\n```'
    )
    assert payload["warmth_delta"] == 0.1


def test_normalize_affect_refine_payload_clamps() -> None:
    result = normalize_affect_refine_payload({
        "warmth_delta": 9,
        "assertiveness_delta": -9,
        "confidence": 2,
        "summary": "x" * 300,
        "triggers": [{"phrase": "？？？", "warmth_delta": 0.02, "assertiveness_delta": 0.03}],
    })
    assert result.warmth_delta == 0.5
    assert result.assertiveness_delta == -0.5
    assert result.confidence == 1.0
    assert len(result.summary) <= 256
    assert result.triggers[0].phrase == "？？？"


def test_heuristic_affect_refine_uses_civility() -> None:
    request = AffectRefineRequest(
        group_id=1,
        profile=AffectRefineProfile(
            raw={
                "affect_tone": {
                    "civility_score": 0.5,
                    "harsh_msg_ratio": 0.0,
                    "polite_msg_ratio": 0.2,
                    "punct_aggression_avg": 0.0,
                }
            },
            derived=AffectRefineProfileDerived(warmth_bias=0.1, assertiveness_bias=0.0),
        ),
    )
    result = heuristic_affect_refine(request)
    assert result.warmth_delta > 0
    assert result.assertiveness_delta <= 0


def test_build_affect_refine_user_prompt_includes_hints() -> None:
    prompt = build_affect_refine_user_prompt(
        AffectRefineRequest(
            group_id=42,
            profile=AffectRefineProfile(derived=AffectRefineProfileDerived()),
            hints=["群消息偏短"],
            message_samples=["谢谢"],
        )
    )
    assert "group_id=42" in prompt
    assert "群消息偏短" in prompt
    assert "谢谢" in prompt


def test_persona_affect_refine_endpoint_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "persona_affect_refine_enabled", False)
    client = TestClient(app)
    response = client.post(
        "/api/persona/affect-refine",
        json={
            "group_id": 1,
            "profile": {"derived": {"warmth_bias": 0.0, "assertiveness_bias": 0.0}},
            "hints": [],
            "message_samples": [],
        },
    )
    assert response.status_code == 503


def test_persona_affect_refine_endpoint_enabled(monkeypatch) -> None:
    async def fake_refine(request: AffectRefineRequest):
        return normalize_affect_refine_payload({
            "warmth_delta": 0.05,
            "assertiveness_delta": 0.02,
            "confidence": 0.8,
            "summary": "test",
        })

    monkeypatch.setattr(settings, "persona_affect_refine_enabled", True)
    monkeypatch.setattr(persona_affect_endpoint, "refine_group_affect", fake_refine)

    client = TestClient(app)
    response = client.post(
        "/api/persona/affect-refine",
        json={
            "group_id": 1,
            "profile": {"derived": {"warmth_bias": 0.0, "assertiveness_bias": 0.0}},
            "hints": ["聊天较活跃"],
            "message_samples": ["草"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["warmth_delta"] == 0.05
    assert body["confidence"] == 0.8
