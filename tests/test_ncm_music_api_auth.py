from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.http.endpoints import ncm_music
from app.http.factory import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(enabled_endpoints={"ncm_music"}))


def test_ncm_endpoints_fail_closed_without_configured_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "")

    assert client.get("/v1/ncm/search", params={"q": "song"}).status_code == 503
    assert client.get("/api/ncm/search", params={"q": "song"}).status_code == 503


def test_ncm_endpoints_require_valid_bearer(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")

    assert client.get("/v1/ncm/search", params={"q": "song"}).status_code == 401
    assert (
        client.get(
            "/v1/ncm/search",
            params={"q": "song"},
            headers={"Authorization": "Bearer wrong-token"},
        ).status_code
        == 401
    )


def test_ncm_endpoints_return_only_song_metadata(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")
    monkeypatch.setattr(ncm_music.ncm_login_manager, "session", object())
    search_song = AsyncMock(return_value=123)
    get_song_detail = AsyncMock(return_value={"name": "Song", "artists": ["Artist"]})
    monkeypatch.setattr(ncm_music, "get_song_id", search_song)
    monkeypatch.setattr(
        ncm_music,
        "get_song_detail",
        get_song_detail,
    )
    headers = {"Authorization": "Bearer secret-token"}

    search = client.get("/v1/ncm/search", params={"q": "Song"}, headers=headers)
    detail = client.get("/v1/ncm/songs/123", headers=headers)

    assert search.status_code == 200
    assert search.json() == {"song_id": 123}
    search_song.assert_awaited_once_with("Song", exclude_vip=False)
    assert detail.status_code == 200
    assert detail.json() == {"name": "Song", "artists": ["Artist"]}
    get_song_detail.assert_awaited_once_with(123)
