from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.media_models import (
    get_tts_defaults,
    list_sing_speakers,
    list_tts_voices,
    load_media_models,
    order_backends_by_preference,
    resolve_sing_speaker,
    resolve_tts_request,
    set_sing_defaults,
    set_tts_defaults,
)


def test_resolve_sing_speaker_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    (tmp_path / "data").mkdir()
    assert resolve_sing_speaker("", root=tmp_path) == "pallas"
    assert resolve_sing_speaker("custom", root=tmp_path) == "custom"


def test_set_sing_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    speaker_dir = tmp_path / "resource/sing/models/foo"
    speaker_dir.mkdir(parents=True)
    (speaker_dir / "foo.pt").write_bytes(b"x")
    monkeypatch.setattr("app.media_models.settings.svc_models_root", "resource/sing/models")
    result = set_sing_defaults(default_speaker="foo", root=tmp_path)
    assert result["default_speaker"] == "foo"
    assert load_media_models(tmp_path)["sing"]["default_speaker"] == "foo"


def test_preferred_backend_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    (tmp_path / "data").mkdir()
    a = SimpleNamespace(name="ddsp_6.3")
    b = SimpleNamespace(name="sovits_4.1")
    ordered = order_backends_by_preference([a, b], "sovits_4.1")
    assert [x.name for x in ordered] == ["sovits_4.1", "ddsp_6.3"]
    set_sing_defaults(preferred_backend="", root=tmp_path)
    assert not load_media_models(tmp_path)["sing"]["preferred_backend"]


def test_list_tts_voices_and_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    ref = tmp_path / "resource/tts/ref_audio"
    ref.mkdir(parents=True)
    sample = ref / "demo.wav"
    sample.write_bytes(b"RIFF")
    voices = list_tts_voices(tmp_path)
    assert any(v["path"].endswith("demo.wav") for v in voices["voices"])
    set_tts_defaults(ref_audio_path="resource/tts/ref_audio/demo.wav", prompt_text="hi", root=tmp_path)
    defaults = get_tts_defaults(tmp_path)
    assert defaults["ref_audio_path"].endswith("demo.wav")
    assert defaults["prompt_text"] == "hi"
    req = resolve_tts_request(text="你好", root=tmp_path)
    assert "demo.wav" in req["ref_audio_path"]
    assert req["prompt_text"] == "hi"


def test_list_sing_speakers_skips_pretrain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    monkeypatch.setattr("app.media_models.settings.svc_models_root", "resource/sing/models")
    (tmp_path / "resource/sing/models/pallas").mkdir(parents=True)
    (tmp_path / "resource/sing/models/pallas/a.pt").write_bytes(b"x")
    (tmp_path / "resource/sing/models/pretrain").mkdir(parents=True)
    rows = list_sing_speakers(tmp_path)
    ids = {s["id"] for s in rows["speakers"]}
    assert "pallas" in ids
    assert "pretrain" not in ids


def test_api_media_models_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resource/sing/models/pallas").mkdir(parents=True)
    (tmp_path / "resource/sing/models/pallas/a.pt").write_bytes(b"x")
    (tmp_path / "resource/tts/ref_audio").mkdir(parents=True)
    (tmp_path / "resource/tts/ref_audio/a.wav").write_bytes(b"x")
    (tmp_path / "data").mkdir()
    client = TestClient(create_app(enabled_endpoints={"media_models"}))
    speakers = client.get("/api/media/models/sing/speakers")
    assert speakers.status_code == 200
    assert "speakers" in speakers.json()
    put = client.put("/api/media/models/sing/defaults", json={"default_speaker": "pallas"})
    assert put.status_code == 200
    backends = client.get("/api/media/models/sing/backends")
    assert backends.status_code == 200
    assert "backends" in backends.json()
    voices = client.get("/api/media/models/tts/voices")
    assert voices.status_code == 200
    assert "voices" in voices.json()
