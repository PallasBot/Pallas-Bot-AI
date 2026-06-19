#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WORKER_SCRIPT="${AI_SERVICE_WORKER_SCRIPT:-$ROOT/scripts/celery_worker.sh}"
RUN_API_CMD="${AI_SERVICE_RUN_API_CMD:-$ROOT/scripts/run_api.sh}"
API_PID_FILE="${AI_SERVICE_API_PID_FILE:-$ROOT/logs/api.pid}"
API_LOG_FILE="${AI_SERVICE_API_LOG_FILE:-$ROOT/logs/api.log}"
API_STOP_WAIT_SEC="${AI_SERVICE_API_STOP_WAIT_SEC:-20}"
DEFAULT_WORKER_PID_FILE="${AI_SERVICE_DEFAULT_WORKER_PID_FILE:-$ROOT/logs/celery.pid}"
DEFAULT_WORKER_LOG_FILE="${AI_SERVICE_DEFAULT_WORKER_LOG_FILE:-$ROOT/logs/celery.log}"

run_worker() {
  local action="$1"
  local queue="$2"
  local pid_file="$3"
  local log_file="$4"
  env \
    CELERY_PID_FILE="$pid_file" \
    CELERY_LOG_FILE="$log_file" \
    CELERY_WORKER_QUEUE="$queue" \
    "$WORKER_SCRIPT" "$action"
}

read_api_pids() {
  if [[ -f "$API_PID_FILE" ]]; then
    tr ' ' '\n' <"$API_PID_FILE" | rg -v '^\s*$' || true
  fi
}

api_is_running() {
  local pid
  while read -r pid; do
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && return 0
  done < <(read_api_pids | sort -u)
  return 1
}

start_api() {
  mkdir -p "$(dirname "$API_LOG_FILE")"
  if api_is_running; then
    echo "API 已在运行"
    read_api_pids | sort -u
    return 0
  fi

  echo "启动 API → $API_LOG_FILE"
  nohup "$RUN_API_CMD" >>"$API_LOG_FILE" 2>&1 &
  echo $! >"$API_PID_FILE"
  sleep 3

  if api_is_running; then
    echo "API 已启动"
    read_api_pids | sort -u
  else
    echo "API 启动失败，见 $API_LOG_FILE"
    rm -f "$API_PID_FILE"
    return 1
  fi
}

stop_api() {
  local pids=()
  local pid
  while read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(read_api_pids | sort -u)

  if [[ ${#pids[@]} -eq 0 ]]; then
    echo "API 未运行"
    rm -f "$API_PID_FILE"
    return 0
  fi

  echo "停止 API (SIGTERM → 等待 ${API_STOP_WAIT_SEC}s → SIGKILL)..."
  kill -TERM "${pids[@]}" 2>/dev/null || true

  local i
  for ((i = 0; i < API_STOP_WAIT_SEC; i++)); do
    if ! api_is_running; then
      echo "API 已退出"
      rm -f "$API_PID_FILE"
      return 0
    fi
    sleep 1
  done

  echo "API 停止超时，强制 SIGKILL"
  kill -KILL "${pids[@]}" 2>/dev/null || true
  sleep 1
  rm -f "$API_PID_FILE"
  echo "API 已强杀"
}

start_service() {
  run_worker start "" "$DEFAULT_WORKER_PID_FILE" "$DEFAULT_WORKER_LOG_FILE"
  start_api
  echo "AI service 已启动"
}

stop_service() {
  stop_api
  run_worker stop "" "$DEFAULT_WORKER_PID_FILE" "$DEFAULT_WORKER_LOG_FILE"
  echo "AI service 已停止"
}

status_service() {
  if api_is_running; then
    echo "API 运行中:"
    read_api_pids | sort -u
  else
    echo "API 未运行"
  fi
  run_worker status "" "$DEFAULT_WORKER_PID_FILE" "$DEFAULT_WORKER_LOG_FILE"
}

purge_stale_service() {
  run_worker purge-stale "" "$DEFAULT_WORKER_PID_FILE" "$DEFAULT_WORKER_LOG_FILE"
}

restart_clean_service() {
  stop_api
  run_worker restart-clean "" "$DEFAULT_WORKER_PID_FILE" "$DEFAULT_WORKER_LOG_FILE"
  start_api
  echo "AI service 已启动"
}

case "${1:-}" in
  start) start_service ;;
  stop) stop_service ;;
  restart) stop_service; start_service ;;
  purge-stale) purge_stale_service ;;
  restart-clean) restart_clean_service ;;
  status) status_service ;;
  *)
    echo "用法: $0 {start|stop|restart|restart-clean|purge-stale|status}"
    exit 1
    ;;
esac
