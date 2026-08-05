from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.cli import main


def test_cli_forwards_lifecycle_command_to_ctl(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_run(command: list[str], *, check: bool) -> SimpleNamespace:
        captured.append(command)
        assert check is False
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.cli.subprocess.run", fake_run)

    assert main(["restart", "media"]) == 0
    assert captured == [["bash", str(Path(__file__).parent.parent / "scripts/ctl.sh"), "restart", "media"]]


def test_cli_uses_all_services_by_default(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_run(command: list[str], *, check: bool) -> SimpleNamespace:
        captured.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.cli.subprocess.run", fake_run)

    assert main(["status"]) == 0
    assert captured == [["bash", str(Path(__file__).parent.parent / "scripts/ctl.sh"), "status", "all"]]


def test_cli_purges_stale_tasks_without_service_target(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_run(command: list[str], *, check: bool) -> SimpleNamespace:
        captured.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.cli.subprocess.run", fake_run)

    assert main(["purge-stale"]) == 0
    assert captured == [["bash", str(Path(__file__).parent.parent / "scripts/ctl.sh"), "purge-stale"]]
