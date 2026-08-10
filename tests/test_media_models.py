from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.http.factory import create_app
from app.media import models as media_models
from app.media.models import (
    get_sing_defaults,
    get_tts_defaults,
    get_tts_translator,
    list_sing_speakers,
    list_tts_voices,
    load_media_models,
    order_backends_by_preference,
    resolve_sing_speaker,
    resolve_tts_request,
    resolve_tts_translator_config,
    save_media_models,
    set_sing_defaults,
    set_tts_defaults,
    set_tts_translator,
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
    monkeypatch.setattr("app.media.models.settings.svc_models_root", "resource/sing/models")
    result = set_sing_defaults(default_speaker="foo", root=tmp_path)
    assert result["default_speaker"] == "foo"
    assert load_media_models(tmp_path)["sing"]["default_speaker"] == "foo"


def test_save_media_models_replaces_complete_temp_file_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    replacements: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def capture_replace(source: Path, destination: Path) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(media_models.os, "replace", capture_replace)
    save_media_models({"sing": {"song_cache_days": 90, "song_cache_size": 12}}, root=tmp_path)

    target = tmp_path / "data/media_models.json"
    assert replacements == [(replacements[0][0], target)]
    assert replacements[0][0].parent == target.parent
    assert replacements[0][0] != target
    assert not replacements[0][0].exists()
    assert load_media_models(tmp_path)["sing"]["song_cache_days"] == 90


def test_sing_cache_defaults_follow_settings_and_disk_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr("app.media.models.settings.song_cache_days", 45)
    monkeypatch.setattr("app.media.models.settings.song_cache_size", 250)

    defaults = get_sing_defaults(tmp_path)
    assert defaults["song_cache_days"] == 45
    assert defaults["song_cache_size"] == 250
    assert list_sing_speakers(tmp_path)["song_cache_days"] == 45

    set_sing_defaults(song_cache_days=90, song_cache_size=12, root=tmp_path)
    monkeypatch.setattr("app.media.models.settings.song_cache_days", 60)
    saved = get_sing_defaults(tmp_path)
    assert saved["song_cache_days"] == 90
    assert saved["song_cache_size"] == 12
    assert load_media_models(tmp_path)["sing"]["song_cache_days"] == 90

    set_sing_defaults(preferred_backend="", root=tmp_path)
    assert get_sing_defaults(tmp_path)["song_cache_days"] == 90
    assert get_sing_defaults(tmp_path)["song_cache_size"] == 12


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("song_cache_days", 0),
        ("song_cache_days", 3651),
        ("song_cache_size", -1),
        ("song_cache_size", 10001),
        ("song_cache_days", True),
    ],
)
def test_set_sing_cache_rejects_invalid_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    (tmp_path / "data").mkdir()
    with pytest.raises(ValueError, match="song_cache"):
        set_sing_defaults(root=tmp_path, **{field: value})


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
    monkeypatch.setattr("app.media.models.settings.svc_models_root", "resource/sing/models")
    (tmp_path / "resource/sing/models/pallas").mkdir(parents=True)
    (tmp_path / "resource/sing/models/pallas/a.pt").write_bytes(b"x")
    (tmp_path / "resource/sing/models/pretrain").mkdir(parents=True)
    rows = list_sing_speakers(tmp_path)
    ids = {s["id"] for s in rows["speakers"]}
    assert "pallas" in ids
    assert "pretrain" not in ids


def test_tts_translator_disk_overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr("app.media.models.settings.translator_enable", True)
    monkeypatch.setattr("app.media.models.settings.default_translator", "baidu")
    monkeypatch.setattr("app.media.models.settings.baidu_app_id", "env-id")
    monkeypatch.setattr("app.media.models.settings.baidu_secret_key", "env-secret")

    public = get_tts_translator(tmp_path)
    assert public["source"] == "env"
    assert public["enable"] is True
    assert public["baidu_app_id"] == "env-id"
    assert public["baidu_secret_configured"] is True
    assert "baidu_secret_key" not in public

    saved = set_tts_translator(
        enable=False,
        provider="youdao",
        youdao_app_key="yd-key",
        youdao_app_secret="yd-secret",
        root=tmp_path,
    )
    assert saved["source"] == "disk"
    assert saved["enable"] is False
    assert saved["provider"] == "youdao"
    assert saved["youdao_secret_configured"] is True

    # 空 secret / **** 不覆盖
    set_tts_translator(youdao_app_secret="", root=tmp_path)
    set_tts_translator(youdao_app_secret="****", root=tmp_path)
    cfg = resolve_tts_translator_config(tmp_path)
    assert cfg["youdao_app_secret"] == "yd-secret"
    assert cfg["enable"] is False

    # 保存音色默认不丢翻译
    ref = tmp_path / "resource/tts/ref_audio"
    ref.mkdir(parents=True)
    (ref / "demo.wav").write_bytes(b"RIFF")
    set_tts_defaults(ref_audio_path="resource/tts/ref_audio/demo.wav", root=tmp_path)
    assert load_media_models(tmp_path)["translator"]["provider"] == "youdao"


def test_api_tts_translator_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    client = TestClient(create_app(enabled_endpoints={"media_models"}))
    got = client.get("/api/media/models/tts/translator")
    assert got.status_code == 200
    body = got.json()
    assert "enable" in body
    assert "baidu_secret_configured" in body
    put = client.put(
        "/api/media/models/tts/translator",
        json={"enable": True, "provider": "baidu", "baidu_app_id": "x", "baidu_secret_key": "y"},
    )
    assert put.status_code == 200
    assert put.json()["enable"] is True
    assert put.json()["baidu_secret_configured"] is True


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
    put = client.put(
        "/api/media/models/sing/defaults",
        json={"default_speaker": "pallas", "song_cache_days": 3650, "song_cache_size": 0},
    )
    assert put.status_code == 200
    assert put.json()["song_cache_days"] == 3650
    assert put.json()["song_cache_size"] == 0
    assert client.get("/api/media/models/sing/defaults").json()["song_cache_size"] == 0
    assert client.put("/api/media/models/sing/defaults", json={"song_cache_days": 0}).status_code == 422
    assert client.put("/api/media/models/sing/defaults", json={"song_cache_size": 10001}).status_code == 422
    for field, value in (("song_cache_days", True), ("song_cache_days", "30"), ("song_cache_size", 1.0)):
        assert client.put("/api/media/models/sing/defaults", json={field: value}).status_code == 422
    backends = client.get("/api/media/models/sing/backends")
    assert backends.status_code == 200
    assert "backends" in backends.json()
    voices = client.get("/api/media/models/tts/voices")
    assert voices.status_code == 200
    assert "voices" in voices.json()
