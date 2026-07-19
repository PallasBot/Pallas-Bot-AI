from __future__ import annotations

from app.run_api import parse_reload_dirs


def test_parse_reload_dirs_splits_comma_list() -> None:
    assert parse_reload_dirs("app/api,app/core") == ["app/api", "app/core"]
    assert parse_reload_dirs(" app/api , ") == ["app/api"]
    assert parse_reload_dirs("") == []
