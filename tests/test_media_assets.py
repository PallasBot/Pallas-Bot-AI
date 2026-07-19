from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routers import LLM_CORE_ENDPOINTS, resolve_enabled_endpoints
from app.app_factory import create_app
from app.media_assets import (
    collect_asset_status,
    download_and_extract_missing,
    parse_models_txt,
    start_download_job,
)


def test_parse_models_txt(tmp_path: Path) -> None:
    p = tmp_path / "models.txt"
    p.write_text(
        "https://example.com/a.zip\n  out=resource/chat/models/models.zip\n",
        encoding="utf-8",
    )
    mapping = parse_models_txt(p)
    assert mapping["resource/chat/models/models.zip"] == "https://example.com/a.zip"


def test_collect_asset_status_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    monkeypatch.setattr(
        "app.media_assets.celery_task_package_enabled",
        lambda alias: alias == "llm",
    )
    (tmp_path / "resource").mkdir()
    st = collect_asset_status(tmp_path)
    assert st.deploy_mode == "source"
    assert st.download_allowed is True
    assert st.all_media_assets_ready is False
    assert "missing_chat" in st.hints
    assert st.media_packages_enabled["sing"] is False


def test_collect_asset_status_ready_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    monkeypatch.setattr("app.media_assets.celery_task_package_enabled", lambda alias: True)
    for _aid, marker, _zip in (
        ("chat", "resource/chat/models/.extracted", ""),
        ("sing_pallas", "resource/sing/models/pallas/.extracted", ""),
        ("sing_pretrain", "resource/sing/models/pretrain/.extracted", ""),
        ("tts", "resource/tts/.extracted", ""),
    ):
        path = tmp_path / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    st = collect_asset_status(tmp_path)
    assert st.all_media_assets_ready is True


def test_download_and_extract_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")

    def fake_retrieve(url: str, filename: str | Path) -> tuple[str, None]:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("dummy.txt", "ok")
        return str(path), None

    monkeypatch.setattr("app.media_assets.urlretrieve", fake_retrieve)
    progress: list[str] = []
    download_and_extract_missing(root=tmp_path, progress=progress)
    assert (tmp_path / "resource/chat/models/.extracted").is_file()
    assert (tmp_path / "resource/tts/.extracted").is_file()
    assert any("download chat" in line for line in progress)


def test_start_download_job_docker_forbidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "docker")
    (tmp_path / "resource").mkdir()
    with pytest.raises(PermissionError):
        start_download_job(root=tmp_path)


def test_api_media_assets_status() -> None:
    client = TestClient(create_app(enabled_endpoints={"media_assets"}))
    resp = client.get("/api/media/assets/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "deploy_mode" in body
    assert "assets" in body
    assert "chat" in body["assets"]


def test_api_media_assets_download_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "docker")
    client = TestClient(create_app(enabled_endpoints={"media_assets"}))
    resp = client.post("/api/media/assets/download")
    assert resp.status_code == 409


def test_media_assets_in_llm_core() -> None:
    assert "media_assets" in LLM_CORE_ENDPOINTS
    assert "media_assets" in resolve_enabled_endpoints({"media_assets", "llm_chat"})
