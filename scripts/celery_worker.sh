#!/usr/bin/env bash
# Celery worker 启停：避免前台 Ctrl+C 卡在 warm shutdown 等 Ollama 长任务。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PID_FILE="${CELERY_PID_FILE:-$ROOT/logs/celery.pid}"
LOG_FILE="${CELERY_LOG_FILE:-$ROOT/logs/celery.log}"
WAIT_SEC="${CELERY_STOP_WAIT_SEC:-20}"
WORKER_QUEUE="${CELERY_WORKER_QUEUE:-}"
REDIS_URL_OVERRIDE="${CELERY_REDIS_URL:-${REDIS_URL:-}}"

detect_cuda_home() {
  if [[ -n "${CUDA_HOME:-}" && -d "${CUDA_HOME:-}" ]]; then
    return 0
  fi
  local candidate=""
  for candidate in /usr/local/cuda /usr/local/cuda-12.4 /usr/local/cuda-12; do
    if [[ -d "$candidate" ]]; then
      export CUDA_HOME="$candidate"
      return 0
    fi
  done
}

read_pids() {
  if [[ -f "$PID_FILE" ]]; then
    tr ' ' '\n' <"$PID_FILE" | grep -v '^\s*$' || true
  fi
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
  detect_cuda_home
  if is_running; then
    echo "celery worker 已在运行"
    read_pids | sort -u
    return 0
  fi
  local queue_args=()
  if [[ -n "$WORKER_QUEUE" ]]; then
    queue_args=( -Q "$WORKER_QUEUE" )
  fi
  echo "启动 celery worker${WORKER_QUEUE:+ queue=$WORKER_QUEUE} → $LOG_FILE"
  nohup uv run --no-sync celery -A app.core.celery worker --loglevel=warning "${queue_args[@]}" >>"$LOG_FILE" 2>&1 &
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

resolve_redis_url() {
  if [[ -n "$REDIS_URL_OVERRIDE" ]]; then
    printf '%s\n' "$REDIS_URL_OVERRIDE"
    return 0
  fi
  if [[ -f "$ROOT/.env" ]]; then
    local raw
    raw="$(grep -E '^REDIS_URL=' "$ROOT/.env" | tail -n 1 || true)"
    raw="${raw#REDIS_URL=}"
    raw="${raw#\"}"
    raw="${raw%\"}"
    if [[ -n "$raw" ]]; then
      printf '%s\n' "$raw"
      return 0
    fi
  fi
  printf '%s\n' "redis://localhost:6379/0"
}

purge_stale() {
  local redis_url
  redis_url="$(resolve_redis_url)"
  echo "清理 Celery 遗留任务（保留 llm:session:*） url=$redis_url"
  local summary
  summary="$(REDIS_URL="$redis_url" uv run --no-sync python - <<'PY'
import json
import os

import redis

url = os.environ["REDIS_URL"]
client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1.0, socket_timeout=2.0)
patterns = ("celery-task-meta-*", "unacked", "unacked_index")
deleted = {}
for pattern in patterns:
    keys = [pattern] if "*" not in pattern else sorted(client.keys(pattern))
    existing = [key for key in keys if client.exists(key)]
    deleted[pattern] = len(existing)
    if existing:
        client.delete(*existing)
print(json.dumps({"redis_url": url, "deleted": deleted}, ensure_ascii=False))
PY
)"
  echo "$summary"
}

case "${1:-}" in
  start) start_worker ;;
  stop) stop_worker ;;
  restart) stop_worker; start_worker ;;
  purge-stale) purge_stale ;;
  restart-clean) stop_worker; purge_stale; start_worker ;;
  status) status_worker ;;
  *)
    echo "用法: $0 {start|stop|restart|restart-clean|purge-stale|status}"
    exit 1
    ;;
esac
