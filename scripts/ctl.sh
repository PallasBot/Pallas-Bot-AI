#!/usr/bin/env bash
# Pallas-Bot AI 统一启停脚本。
# 管理三类服务：
#   llm   —— Celery worker，吃 default 队列（LLM 推理）
#   media —— Celery worker，吃 media 队列（唱歌 / TTS / 旧版 chat）
#   api   —— FastAPI (uvicorn)
#
# 用法:
#   ./scripts/ctl.sh <command> [target]
#   command: start | stop | restart | status | purge-stale | restart-clean
#   target : llm | media | api | all（缺省 all）
#
# 例:
#   ./scripts/ctl.sh restart media     # 只重启 media，不动正在跑的 LLM
#   ./scripts/ctl.sh stop llm
#   ./scripts/ctl.sh start             # 启动全部
#
# 僵尸进程根治：Celery 以 --pidfile 写**自身真实 PID**（不再记 uv run 包装层 PID），
# stop 时按真实 PID + 进程组精确清理，避免卡死 worker 被 SIGKILL 后遗留孤儿。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG_DIR="${PALLAS_LOG_DIR:-$ROOT/logs}"
WAIT_SEC="${PALLAS_STOP_WAIT_SEC:-20}"
REDIS_URL_OVERRIDE="${PALLAS_REDIS_URL:-${REDIS_URL:-}}"

mkdir -p "$LOG_DIR"

# ── 服务定义 ───────────────────────────────────────────────────────────
# 每个服务: 类型(celery|api) | 队列(celery) | 任务包(celery) | pidfile | logfile
svc_kind()    { case "$1" in llm|media) echo celery ;; api) echo api ;; esac; }
svc_queue()   { case "$1" in llm) echo default ;; media) echo media ;; *) echo "" ;; esac; }
svc_packages(){ case "$1" in llm) echo llm ;; media) echo "sing,tts,chat" ;; *) echo "" ;; esac; }
svc_pidfile() { echo "$LOG_DIR/$1.pid"; }
svc_logfile() {
  case "$1" in
    llm)   echo "$LOG_DIR/celery.log" ;;
    media) echo "$LOG_DIR/celery-media.log" ;;
    api)   echo "$LOG_DIR/uvicorn.log" ;;
  esac
}

ALL_SERVICES=(llm media api)

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

is_running() {
  local pid
  pid="$(read_pid "$(svc_pidfile "$1")")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

# ── 启动 ───────────────────────────────────────────────────────────────
start_one() {
  local svc="$1"
  local pidfile logfile
  pidfile="$(svc_pidfile "$svc")"
  logfile="$(svc_logfile "$svc")"

  if is_running "$svc"; then
    echo "[$svc] 已在运行 (PID $(read_pid "$pidfile"))"
    return 0
  fi
  # 清理过期 pidfile
  rm -f "$pidfile"

  detect_cuda_home

  if [[ "$(svc_kind "$svc")" == "celery" ]]; then
    local queue packages
    queue="$(svc_queue "$svc")"
    packages="$(svc_packages "$svc")"
    echo "[$svc] 启动 celery worker queue=$queue → $logfile"
    # setsid 让每个服务独立进程组：stop 补杀进程组时不会误伤其它 worker。
    # --pidfile 让 celery 写自身真实 PID；-n 给唯一节点名，避免多 worker 冲突。
    CELERY_TASK_PACKAGES="$packages" setsid nohup uv run --no-sync celery -A app.core.celery worker \
      --loglevel=warning -Q "$queue" -n "${svc}@%h" --pidfile="$pidfile" \
      >>"$logfile" 2>&1 &
  else
    echo "[$svc] 启动 API → $logfile"
    setsid nohup uv run --no-sync python -m app.run_api >>"$logfile" 2>&1 &
    echo $! >"$pidfile"
  fi

  # celery 自己写 pidfile 需要一点时间；轮询等待。
  local i
  for ((i = 0; i < 10; i++)); do
    sleep 1
    if is_running "$svc"; then
      echo "[$svc] 已启动 (PID $(read_pid "$pidfile"))"
      return 0
    fi
  done
  echo "[$svc] 启动失败，见 $logfile"
  return 1
}

# ── 停止 ───────────────────────────────────────────────────────────────
stop_one() {
  local svc="$1"
  local pidfile pid
  pidfile="$(svc_pidfile "$svc")"
  pid="$(read_pid "$pidfile")"

  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    echo "[$svc] 未在运行"
    rm -f "$pidfile"
    return 0
  fi

  echo "[$svc] 停止 (PID $pid; SIGTERM → 等 ${WAIT_SEC}s → SIGKILL)..."
  kill -TERM "$pid" 2>/dev/null || true

  local i
  for ((i = 0; i < WAIT_SEC; i++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "[$svc] 已退出"
      rm -f "$pidfile"
      return 0
    fi
    sleep 1
  done

  echo "[$svc] 超时，SIGKILL"
  kill -KILL "$pid" 2>/dev/null || true
  # 补杀进程组，清掉 celery 卡死任务可能遗留的子进程/孤儿。
  local pgid
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
  if [[ -n "$pgid" ]]; then
    kill -KILL -- "-$pgid" 2>/dev/null || true
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

# ── purge-stale（仅影响 celery broker，api 跳过）─────────────────────────
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
  echo "清理 Celery 遗留任务（保留 llm:session:*） url=$redis_url"
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

# ── 目标解析 ───────────────────────────────────────────────────────────
resolve_targets() {
  local target="${1:-all}"
  case "$target" in
    all|"") printf '%s\n' "${ALL_SERVICES[@]}" ;;
    llm|media|api) printf '%s\n' "$target" ;;
    *)
      echo "未知目标: $target（可选 llm|media|api|all）" >&2
      return 1
      ;;
  esac
}

# 启动顺序 llm→media→api；停止逆序，避免 API 先收任务无人处理。
main() {
  local cmd="${1:-}"
  local target="${2:-all}"
  local targets
  mapfile -t targets < <(resolve_targets "$target")

  case "$cmd" in
    start)
      for s in "${targets[@]}"; do start_one "$s"; done
      ;;
    stop)
      # 逆序停
      for ((i = ${#targets[@]} - 1; i >= 0; i--)); do stop_one "${targets[$i]}"; done
      ;;
    restart)
      for ((i = ${#targets[@]} - 1; i >= 0; i--)); do stop_one "${targets[$i]}"; done
      for s in "${targets[@]}"; do start_one "$s"; done
      ;;
    restart-clean)
      for ((i = ${#targets[@]} - 1; i >= 0; i--)); do stop_one "${targets[$i]}"; done
      # 只要目标里含 celery 服务才清 broker
      for s in "${targets[@]}"; do [[ "$(svc_kind "$s")" == "celery" ]] && { purge_stale; break; }; done
      for s in "${targets[@]}"; do start_one "$s"; done
      ;;
    purge-stale)
      purge_stale
      ;;
    status)
      for s in "${targets[@]}"; do status_one "$s"; done
      ;;
    *)
      echo "用法: $0 {start|stop|restart|restart-clean|purge-stale|status} [llm|media|api|all]"
      exit 1
      ;;
  esac
}

main "$@"
