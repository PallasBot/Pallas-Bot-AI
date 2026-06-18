#!/usr/bin/env bash
# Celery worker 启停：避免前台 Ctrl+C 卡在 warm shutdown 等 Ollama 长任务。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PID_FILE="${CELERY_PID_FILE:-$ROOT/logs/celery.pid}"
LOG_FILE="${CELERY_LOG_FILE:-$ROOT/logs/celery.log}"
WAIT_SEC="${CELERY_STOP_WAIT_SEC:-20}"

read_pids() {
  if [[ -f "$PID_FILE" ]]; then
    tr ' ' '\n' <"$PID_FILE" | rg -v '^\s*$' || true
  fi
  pgrep -f "celery -A app.core.celery worker" 2>/dev/null || true
}

is_running() {
  local p
  while read -r p; do
    [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null && return 0
  done < <(read_pids | sort -u)
  return 1
}

start_worker() {
  mkdir -p "$(dirname "$LOG_FILE")"
  if is_running; then
    echo "celery worker 已在运行"
    read_pids | sort -u
    return 0
  fi
  echo "启动 celery worker → $LOG_FILE"
  nohup uv run --no-sync celery -A app.core.celery worker --loglevel=warning >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 3
  if is_running; then
    echo "celery worker 已启动"
    read_pids | sort -u
  else
    echo "celery worker 启动失败，见 $LOG_FILE"
    return 1
  fi
}

stop_worker() {
  local pids=()
  while read -r p; do
    [[ -n "$p" ]] && pids+=("$p")
  done < <(read_pids | sort -u)

  if [[ ${#pids[@]} -eq 0 ]]; then
    echo "celery worker 未在运行"
    rm -f "$PID_FILE"
    return 0
  fi

  echo "停止 celery worker (SIGTERM → 等待 ${WAIT_SEC}s → SIGKILL)..."
  kill -TERM "${pids[@]}" 2>/dev/null || true

  local i
  for ((i = 0; i < WAIT_SEC; i++)); do
    if ! is_running; then
      echo "celery worker 已退出"
      rm -f "$PID_FILE"
      return 0
    fi
    sleep 1
  done

  echo "超时，强制 SIGKILL"
  kill -KILL "${pids[@]}" 2>/dev/null || true
  sleep 1
  rm -f "$PID_FILE"
  echo "celery worker 已强杀"
}

status_worker() {
  if is_running; then
    echo "celery worker 运行中:"
    read_pids | sort -u
  else
    echo "celery worker 未运行"
  fi
}

case "${1:-}" in
  start) start_worker ;;
  stop) stop_worker ;;
  restart) stop_worker; start_worker ;;
  status) status_worker ;;
  *)
    echo "用法: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
