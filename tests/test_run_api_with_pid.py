from __future__ import annotations

import os
from pathlib import Path

from app import run_api_with_pid


def test_run_api_with_pid_writes_native_pid(tmp_path, monkeypatch) -> None:
    pidfile = tmp_path / "api.pid"
    called: dict[str, object] = {}

    def fake_run_module(mod: str, *, run_name: str) -> None:
        called["mod"] = mod
        called["run_name"] = run_name
        assert pidfile.read_text(encoding="utf-8").strip() == str(os.getpid())

    monkeypatch.setattr(run_api_with_pid.runpy, "run_module", fake_run_module)
    run_api_with_pid.main([str(pidfile)])
    assert called == {"mod": "app.run_api", "run_name": "__main__"}
    assert Path(pidfile).read_text(encoding="utf-8").strip() == str(os.getpid())
