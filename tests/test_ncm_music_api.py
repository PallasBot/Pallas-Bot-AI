import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.media.services import ncm_loader


@asynccontextmanager
async def _session():
    yield object()


def test_get_song_id_keeps_first_result_for_logged_in_session(monkeypatch: pytest.MonkeyPatch) -> None:
    search = AsyncMock(return_value={"result": {"songCount": 1, "songs": [{"id": 123}]}})
    monkeypatch.setattr(ncm_loader, "ncm_request_session", _session)
    monkeypatch.setattr(ncm_loader.ncm.cloudsearch, "GetSearchResult", search)

    assert asyncio.run(ncm_loader.get_song_id("song", exclude_vip=False)) == 123
    search.assert_awaited_once_with("song", 1, 10)


def test_get_song_id_filters_unavailable_and_vip_results(monkeypatch: pytest.MonkeyPatch) -> None:
    search = AsyncMock(
        return_value={
            "result": {
                "songCount": 4,
                "songs": [
                    {"id": 1},
                    {"id": 2, "privilege": {"chargeInfoList": []}},
                    {"id": 3, "privilege": {"chargeInfoList": [{"chargeType": 1}]}},
                    {"id": 4, "privilege": {"chargeInfoList": [{"chargeType": 0}]}},
                ],
            }
        }
    )
    monkeypatch.setattr(ncm_loader, "ncm_request_session", _session)
    monkeypatch.setattr(ncm_loader.ncm.cloudsearch, "GetSearchResult", search)

    assert asyncio.run(ncm_loader.get_song_id("song", exclude_vip=True)) == 4


def test_get_song_detail_returns_only_title_and_artist_names(monkeypatch: pytest.MonkeyPatch) -> None:
    detail = AsyncMock(
        return_value={
            "songs": [
                {
                    "id": 123,
                    "name": "Song",
                    "ar": [{"id": 9, "name": "Artist"}, {"id": 10, "name": ""}],
                }
            ],
            "privileges": [{"token": "must not escape"}],
        }
    )
    monkeypatch.setattr(ncm_loader, "ncm_request_session", _session)
    monkeypatch.setattr(ncm_loader.ncm.track, "GetTrackDetail", detail)

    assert asyncio.run(ncm_loader.get_song_detail(123)) == {"name": "Song", "artists": ["Artist"]}
    detail.assert_awaited_once_with(123)
