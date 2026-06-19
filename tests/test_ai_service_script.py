from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_service.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_script(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    api_cmd = tmp_path / "api_stub.sh"
    worker_cmd = tmp_path / "worker_stub.sh"
    api_pid = tmp_path / "api.pid"
    api_log = tmp_path / "api.log"
    worker_pid = tmp_path / "worker.pid"
    worker_log = tmp_path / "worker.log"
    media_worker_pid = tmp_path / "worker-media.pid"
    media_worker_log = tmp_path / "worker-media.log"

    _write_executable(
        api_cmd,
        """#!/usr/bin/env bash
set -euo pipefail
echo "api started" >> "${AI_SERVICE_TEST_API_LOG}"
trap 'exit 0' TERM INT
while true; do
  sleep 1
done
""",
    )
    _write_executable(
        worker_cmd,
        """#!/usr/bin/env bash
set -euo pipefail
PID_FILE="${CELERY_PID_FILE:?}"
LOG_FILE="${CELERY_LOG_FILE:?}"
QUEUE="${CELERY_WORKER_QUEUE:-default}"
case "${1:-}" in
  start)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "worker already running"
      exit 0
    fi
    (
      trap 'exit 0' TERM INT
      while true; do
        sleep 1
      done
    ) >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    echo "worker started queue=${QUEUE}"
    ;;
  stop)
    if [[ -f "$PID_FILE" ]]; then
      pid="$(cat "$PID_FILE")"
      kill -TERM "$pid" 2>/dev/null || true
      rm -f "$PID_FILE"
    fi
    echo "worker stopped"
    ;;
  status)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "celery worker 运行中: queue=${QUEUE}"
      cat "$PID_FILE"
    else
      echo "celery worker 未运行: queue=${QUEUE}"
    fi
    ;;
  purge-stale)
    echo "worker purged queue=${QUEUE}"
    ;;
  restart-clean)
    echo "worker restart-clean queue=${QUEUE}"
    ;;
  *)
    echo "bad action" >&2
    exit 1
    ;;
esac
""",
    )

    env = os.environ.copy()
    env.update(
        {
            "AI_SERVICE_RUN_API_CMD": str(api_cmd),
            "AI_SERVICE_WORKER_SCRIPT": str(worker_cmd),
            "AI_SERVICE_API_PID_FILE": str(api_pid),
            "AI_SERVICE_API_LOG_FILE": str(api_log),
            "AI_SERVICE_DEFAULT_WORKER_PID_FILE": str(worker_pid),
            "AI_SERVICE_DEFAULT_WORKER_LOG_FILE": str(worker_log),
            "AI_SERVICE_MEDIA_WORKER_PID_FILE": str(media_worker_pid),
            "AI_SERVICE_MEDIA_WORKER_LOG_FILE": str(media_worker_log),
            "AI_SERVICE_TEST_API_LOG": str(api_log),
        }
    )
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_ai_service_script_start_status_stop(tmp_path: Path) -> None:
    start = _run_script(tmp_path, "start")
    assert start.returncode == 0
    assert "AI service 已启动" in start.stdout

    status = _run_script(tmp_path, "status")
    assert status.returncode == 0
    assert "API 运行中" in status.stdout
    assert "celery worker 运行中: queue=default" in status.stdout
    assert "queue=media" not in status.stdout

    stop = _run_script(tmp_path, "stop")
    assert stop.returncode == 0
    assert "AI service 已停止" in stop.stdout

    status_after = _run_script(tmp_path, "status")
    assert status_after.returncode == 0
    assert "API 未运行" in status_after.stdout
    assert "celery worker 未运行: queue=default" in status_after.stdout


def test_ai_service_script_reuses_existing_processes(tmp_path: Path) -> None:
    first = _run_script(tmp_path, "start")
    assert first.returncode == 0

    second = _run_script(tmp_path, "start")
    assert second.returncode == 0
    assert "API 已在运行" in second.stdout

    stop = _run_script(tmp_path, "stop")
    assert stop.returncode == 0


def test_ai_service_status_only_reports_single_worker(tmp_path: Path) -> None:
    _run_script(tmp_path, "start")

    status = _run_script(tmp_path, "status")
    assert status.returncode == 0
    assert "celery worker 运行中: queue=default" in status.stdout
    assert "queue=media" not in status.stdout


def test_ai_service_forwards_worker_actions(tmp_path: Path) -> None:
    purge = _run_script(tmp_path, "purge-stale")
    assert purge.returncode == 0
    assert "worker purged queue=default" in purge.stdout

    restart_clean = _run_script(tmp_path, "restart-clean")
    assert restart_clean.returncode == 0
    assert "worker restart-clean queue=default" in restart_clean.stdout
