#!/usr/bin/env bash
# Pallas-Bot AI 统一启停脚本。
# 管理两类服务：
#   media —— Celery worker，吃 media 队列（唱歌 / TTS / 遗留 chat）
#   api   —— FastAPI (uvicorn)

# 用法:
#   ./scripts/ctl.sh <command> [target]
#   command: start | stop | restart | status | purge-stale | restart-clean
#   target : media | api | all（缺省 all）

# 例:
#   ./scripts/ctl.sh start media
#   ./scripts/ctl.sh start api
#   ./scripts/ctl.sh restart media
#   ./scripts/ctl.sh start
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Bot 进程可能带着 VIRTUAL_ENV=…/Pallas-Bot/.venv；本仓应使用自己的 .venv
unset VIRTUAL_ENV VIRTUAL_ENV_PROMPT UV_PROJECT UV_PROJECT_ENVIRONMENT PYTHONHOME || true

LOG_DIR="${PALLAS_LOG_DIR:-$ROOT/logs}"
WAIT_SEC="${PALLAS_STOP_WAIT_SEC:-20}"
# media worker 冷启动（导入 TTS/唱歌）在 Windows 上常需数十秒；过短会误报「启动失败」
START_WAIT_SEC="${PALLAS_START_WAIT_SEC:-90}"
START_WAIT_API_SEC="${PALLAS_START_WAIT_API_SEC:-20}"
REDIS_URL_OVERRIDE="${PALLAS_REDIS_URL:-${REDIS_URL:-}}"

mkdir -p "$LOG_DIR"

svc_kind()    { case "$1" in media) echo celery ;; api) echo api ;; esac; }
svc_queue()   { case "$1" in media) echo media ;; *) echo "" ;; esac; }
svc_packages(){ case "$1" in media) echo "sing,tts,chat" ;; *) echo "" ;; esac; }
svc_pidfile() { echo "$LOG_DIR/$1.pid"; }
svc_logfile() {
  case "$1" in
    media) echo "$LOG_DIR/celery-media.log" ;;
    api)   echo "$LOG_DIR/uvicorn.log" ;;
  esac
}

ALL_SERVICES=(api media)

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

read_pid() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] && tr -d '[:space:]' <"$pidfile" || true
}

is_windows_host() {
  case "$(uname -s 2>/dev/null || true)" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
  esac
  [[ -n "${WINDIR:-}" || -n "${SystemRoot:-}" ]]
}

# Celery 写入的是原生 Windows PID；Git Bash 的 kill -0 偶发认不出，再退到 tasklist。
pid_alive() {
  local pid="$1"
  [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  if is_windows_host && command -v tasklist >/dev/null 2>&1; then
    tasklist //FI "PID eq ${pid}" 2>/dev/null | grep -qE "[^0-9]${pid}[^0-9]|^${pid}[^0-9]"
    return $?
  fi
  return 1
}

is_running() {
  local pid
  pid="$(read_pid "$(svc_pidfile "$1")")"
  pid_alive "$pid"
}

# Linux 有 setsid；Git Bash / 部分环境没有。有则用，否则回退 nohup / 纯后台。
background_cmd() {
  local logfile="$1"
  shift
  if command -v setsid >/dev/null 2>&1; then
    if command -v nohup >/dev/null 2>&1; then
      setsid nohup "$@" >>"$logfile" 2>&1 &
    else
      setsid "$@" >>"$logfile" 2>&1 &
    fi
  elif command -v nohup >/dev/null 2>&1; then
    nohup "$@" >>"$logfile" 2>&1 &
  else
    "$@" >>"$logfile" 2>&1 &
  fi
}

start_one() {
  local svc="$1"
  local pidfile logfile
  pidfile="$(svc_pidfile "$svc")"
  logfile="$(svc_logfile "$svc")"

  if is_running "$svc"; then
    echo "[$svc] 已在运行 (PID $(read_pid "$pidfile"))"
    return 0
  fi
  rm -f "$pidfile"

  detect_cuda_home

  local wait_sec="$START_WAIT_API_SEC"
  if [[ "$(svc_kind "$svc")" == "celery" ]]; then
    local queue packages
    queue="$(svc_queue "$svc")"
    packages="$(svc_packages "$svc")"
    wait_sec="$START_WAIT_SEC"
    echo "[$svc] 启动 celery worker queue=$queue → $logfile（最多等 ${wait_sec}s）"
    CELERY_TASK_PACKAGES="$packages" background_cmd "$logfile" \
      uv run --no-sync celery -A app.core.celery worker \
      --loglevel=warning -Q "$queue" -n "${svc}@%h" --pidfile="$pidfile"
  else
    echo "[$svc] 启动 API → $logfile（最多等 ${wait_sec}s）"
    # 由 Python 写原生 PID；勿用 echo $!（Git Bash / MSYS 伪 PID，Bot 侧 OpenProcess 认不出）
    background_cmd "$logfile" uv run --no-sync python -m app.run_api_with_pid "$pidfile"
  fi

  local i
  for ((i = 0; i < wait_sec; i++)); do
    sleep 1
    if is_running "$svc"; then
      echo "[$svc] 已启动 (PID $(read_pid "$pidfile"))"
      return 0
    fi
    # 冷启动慢 / Git Bash PID 认不出：日志已出现启动摘要且 pidfile 已写出 → 视为成功
    if [[ -f "$pidfile" && -f "$logfile" ]]; then
      if tail -n 80 "$logfile" 2>/dev/null | grep -q '启动摘要'; then
        echo "[$svc] 已启动 (PID $(read_pid "$pidfile"); 日志已确认)"
        return 0
      fi
    fi
  done
  echo "[$svc] 启动失败，见 $logfile"
  if [[ "$(svc_kind "$svc")" == "celery" ]]; then
    local redis_url
    redis_url="$(resolve_redis_url)"
    if ! REDIS_URL="$redis_url" uv run --no-sync python - <<'PY' 2>/dev/null
import os
import redis
url = os.environ["REDIS_URL"]
redis.Redis.from_url(url, socket_connect_timeout=1.0, socket_timeout=1.0).ping()
PY
    then
      echo "[$svc] 提示: media worker 依赖 Redis（当前不可达: ${redis_url}）"
      echo "[$svc] Windows 请先打开 Docker Desktop 再跑 bootstrap，或本机/WSL 自备 Redis 并设置 REDIS_URL"
    else
      echo "[$svc] 提示: Redis 可达，但 ${wait_sec}s 内未检测到进程；可看日志末尾，或加大 PALLAS_START_WAIT_SEC"
    fi
  elif [[ "$(svc_kind "$svc")" == "api" ]]; then
    echo "[$svc] 提示: 查看 logs/uvicorn.log；Bot 连 9099 失败多半是 API 未起来"
  fi
  return 1
}

stop_one() {
  local svc="$1"
  local pidfile pid
  pidfile="$(svc_pidfile "$svc")"
  pid="$(read_pid "$pidfile")"

  if [[ -z "$pid" ]] || ! pid_alive "$pid"; then
    echo "[$svc] 未在运行"
    rm -f "$pidfile"
    return 0
  fi

  echo "[$svc] 停止 (PID $pid; SIGTERM → 等 ${WAIT_SEC}s → SIGKILL)..."
  kill -TERM "$pid" 2>/dev/null || true
  if is_windows_host && command -v taskkill >/dev/null 2>&1; then
    taskkill //PID "$pid" //T 2>/dev/null || true
  fi

  local i
  for ((i = 0; i < WAIT_SEC; i++)); do
    if ! pid_alive "$pid"; then
      echo "[$svc] 已退出"
      rm -f "$pidfile"
      return 0
    fi
    sleep 1
  done

  echo "[$svc] 超时，SIGKILL"
  kill -KILL "$pid" 2>/dev/null || true
  if is_windows_host && command -v taskkill >/dev/null 2>&1; then
    taskkill //F //PID "$pid" //T 2>/dev/null || true
  fi
  # 进程组强杀依赖 Linux ps/pgid；Git Bash / Windows 跳过
  if ! is_windows_host; then
    local pgid
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
    if [[ -n "$pgid" && "$pgid" =~ ^[0-9]+$ ]]; then
      kill -KILL -- "-$pgid" 2>/dev/null || true
    fi
  fi
  sleep 1
  rm -f "$pidfile"
  echo "[$svc] 已强杀"
}

status_one() {
  local svc="$1"
  if is_running "$svc"; then
    echo "[$svc] 运行中 (PID $(read_pid "$(svc_pidfile "$svc")"))"
  else
    echo "[$svc] 未运行"
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
    raw="${raw#REDIS_URL=}"; raw="${raw#\"}"; raw="${raw%\"}"
    [[ -n "$raw" ]] && { printf '%s\n' "$raw"; return 0; }
  fi
  printf '%s\n' "redis://localhost:6379/0"
}

purge_stale() {
  local redis_url
  redis_url="$(resolve_redis_url)"
  echo "清理 Celery 遗留任务 url=$redis_url"
  REDIS_URL="$redis_url" uv run --no-sync python - <<'PY'
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
}

resolve_targets() {
  local target="${1:-all}"
  case "$target" in
    all|"") printf '%s\n' "${ALL_SERVICES[@]}" ;;
    media|api) printf '%s\n' "$target" ;;
    *)
      echo "未知目标: $target（可选 media|api|all）" >&2
      return 1
      ;;
  esac
}

main() {
  local cmd="${1:-}"
  local target="${2:-all}"
  local targets=()
  local line
  local rc=0
  # 不用 mapfile：部分精简 bash / 旧 Git Bash 更稳妥
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -n "$line" ]] && targets+=("$line")
  done < <(resolve_targets "$target")

  case "$cmd" in
    start)
      # 单个失败不中断：否则 media 误报会导致 api 根本不启动
      for s in "${targets[@]}"; do start_one "$s" || rc=1; done
      ;;
    stop)
      for ((i = ${#targets[@]} - 1; i >= 0; i--)); do stop_one "${targets[$i]}" || true; done
      ;;
    restart)
      for ((i = ${#targets[@]} - 1; i >= 0; i--)); do stop_one "${targets[$i]}" || true; done
      for s in "${targets[@]}"; do start_one "$s" || rc=1; done
      ;;
    restart-clean)
      for ((i = ${#targets[@]} - 1; i >= 0; i--)); do stop_one "${targets[$i]}" || true; done
      for s in "${targets[@]}"; do [[ "$(svc_kind "$s")" == "celery" ]] && { purge_stale || rc=1; break; }; done
      for s in "${targets[@]}"; do start_one "$s" || rc=1; done
      ;;
    purge-stale)
      purge_stale
      ;;
    status)
      for s in "${targets[@]}"; do status_one "$s"; done
      ;;
    *)
      echo "用法: $0 {start|stop|restart|restart-clean|purge-stale|status} [media|api|all]"
      exit 1
      ;;
  esac
  return "$rc"
}

main "$@"
exit $?
