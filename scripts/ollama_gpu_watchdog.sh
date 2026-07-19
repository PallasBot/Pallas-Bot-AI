#!/usr/bin/env bash
# Ollama GPU 探活：检测容器内 NVML/CUDA 是否失效，可选自动 restart。
#
# 背景：Ollama 容器长跑后，宿主机驱动/NVIDIA 栈变化可能导致容器内 NVML 断联，
# Ollama 仍在线但推理回退 CPU（日志含 no CUDA-capable device / CPU KV buffer）。
# 重启容器通常即可恢复 GPU 挂载。
#
# 用法:
#   ./scripts/ollama_gpu_watchdog.sh              # 仅检查，异常 exit 1
#   ./scripts/ollama_gpu_watchdog.sh --fix        # 异常时 restart 容器后再验
#   ./scripts/ollama_gpu_watchdog.sh --quiet      # 仅输出错误/修复动作
#
# cron 示例（每 10 分钟，异常则重启）:
#   */10 * * * * /path/to/Pallas-Bot-AI/scripts/ollama_gpu_watchdog.sh --fix --quiet >>/var/log/ollama-gpu-watchdog.log 2>&1
#
# 环境变量:
#   OLLAMA_CONTAINER       — 容器名（默认自动探测）
#   OLLAMA_COMPOSE_DIR     — 若设置，--fix 时用 docker compose restart（而非 docker restart）
#   OLLAMA_COMPOSE_FILES   — compose 文件列表，空格分隔（相对 OLLAMA_COMPOSE_DIR）
#   OLLAMA_SKIP_GPU=1      — 跳过 GPU 检查（remote_only / 纯 CPU 部署）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

FIX=0
QUIET=0

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix) FIX=1 ;;
    --quiet) QUIET=1 ;;
    -h|--help) usage 0 ;;
    *) echo "未知参数: $1" >&2; usage 1 ;;
  esac
  shift
done

log() {
  [[ "$QUIET" == "1" ]] && return 0
  printf '[ollama-gpu] %s\n' "$*"
}

warn() { printf '[ollama-gpu] 警告: %s\n' "$*" >&2; }
fail_msg() { printf '[ollama-gpu] 错误: %s\n' "$*" >&2; }

read_env_key() {
  local key="$1" default="${2:-}"
  if [[ -f "$ROOT/.env" ]]; then
    local raw
    raw="$(grep -E "^${key}=" "$ROOT/.env" | tail -n 1 || true)"
    if [[ -n "$raw" ]]; then
      raw="${raw#${key}=}"
      raw="${raw#\"}"; raw="${raw%\"}"
      raw="${raw#\'}"; raw="${raw%\'}"
      printf '%s' "$raw"
      return 0
    fi
  fi
  printf '%s' "$default"
}

container_gpu_reserved() {
  local name="$1"
  local reqs
  reqs="$(docker inspect "$name" --format '{{json .HostConfig.DeviceRequests}}' 2>/dev/null || echo 'null')"
  [[ "$reqs" != "null" && "$reqs" != "[]" && "$reqs" == *gpu* ]]
}

resolve_container() {
  if [[ -n "${OLLAMA_CONTAINER:-}" ]]; then
    printf '%s' "$OLLAMA_CONTAINER"
    return 0
  fi
  local candidates=(
    pallas-ai-ollama
    pallas-full-ollama
    ollama
  )
  local name
  for name in "${candidates[@]}"; do
    if docker inspect "$name" >/dev/null 2>&1; then
      printf '%s' "$name"
      return 0
    fi
  done
  local found
  found="$(docker ps --filter 'ancestor=ollama/ollama' --format '{{.Names}}' | head -n 1 || true)"
  if [[ -n "$found" ]]; then
    printf '%s' "$found"
    return 0
  fi
  found="$(docker ps --format '{{.Names}}' | grep -E '(^|[-_])ollama($|[-_])' | head -n 1 || true)"
  if [[ -n "$found" ]]; then
    printf '%s' "$found"
    return 0
  fi
  return 1
}

gpu_check_needed() {
  if [[ "${OLLAMA_SKIP_GPU:-}" == "1" ]]; then
    return 1
  fi
  local mode
  mode="$(read_env_key LLM_PROVIDER_MODE "local_only")"
  if [[ "$mode" == "remote_only" ]]; then
    return 1
  fi
  return 0
}

nvml_ok_in_container() {
  local name="$1"
  docker exec "$name" nvidia-smi >/dev/null 2>&1
}

ollama_logs_suggest_cpu_fallback() {
  local name="$1"
  docker logs "$name" --tail 200 2>&1 | grep -Eq \
    'no CUDA-capable device is detected|Failed to initialize NVML|failure during GPU discovery'
}

ollama_http_ok() {
  local base="${1:-http://127.0.0.1:11434}"
  curl -fsS --max-time 3 "${base%/}/api/tags" >/dev/null 2>&1
}

restart_container() {
  local name="$1"
  if [[ -n "${OLLAMA_COMPOSE_DIR:-}" ]]; then
    local -a compose_args=(-C "$OLLAMA_COMPOSE_DIR")
    if [[ -n "${OLLAMA_COMPOSE_FILES:-}" ]]; then
      local f
      for f in $OLLAMA_COMPOSE_FILES; do
        compose_args+=(-f "$f")
      done
    fi
    log "docker compose ${compose_args[*]} restart ollama"
    docker compose "${compose_args[@]}" restart ollama
    return 0
  fi
  log "docker restart $name"
  docker restart "$name"
}

diagnose() {
  local name="$1"
  local issues=()

  if ! docker inspect "$name" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
    issues+=("容器未运行")
    printf '%s\n' "${issues[@]}"
    return 1
  fi

  if container_gpu_reserved "$name"; then
    if ! nvml_ok_in_container "$name"; then
      issues+=("容器内 nvidia-smi / NVML 不可用")
    elif ollama_logs_suggest_cpu_fallback "$name"; then
      issues+=("Ollama 日志显示 CUDA 初始化失败或 GPU discovery 超时")
    fi
  else
    log "容器 $name 未声明 GPU 设备，跳过 NVML 检查"
  fi

  if ((${#issues[@]} > 0)); then
    printf '%s\n' "${issues[@]}"
    return 1
  fi
  return 0
}

main() {
  if ! command -v docker >/dev/null 2>&1; then
    fail_msg "未找到 docker"
    exit 2
  fi

  if ! gpu_check_needed; then
    log "LLM_PROVIDER_MODE=remote_only 或 OLLAMA_SKIP_GPU=1，跳过"
    exit 0
  fi

  local name
  if ! name="$(resolve_container)"; then
    local backend
    backend="$(read_env_key LLM_BACKEND_URL "http://127.0.0.1:11434")"
    if ollama_http_ok "$backend"; then
      log "未找到 Ollama 容器，但 $backend 可达（可能是宿主机 ollama serve），跳过容器 GPU 检查"
      exit 0
    fi
    fail_msg "未找到运行中的 Ollama 容器，且 $backend 不可达"
    exit 2
  fi

  log "检查容器: $name"

  local issues
  if issues="$(diagnose "$name")"; then
    log "GPU 探活通过"
    exit 0
  fi

  while IFS= read -r line; do
    [[ -n "$line" ]] && warn "$line"
  done <<<"$issues"

  if [[ "$FIX" != "1" ]]; then
    fail_msg "GPU 探活失败；可执行: $0 --fix"
    exit 1
  fi

  restart_container "$name"
  sleep 5

  if diagnose "$name" >/dev/null; then
    log "重启后 GPU 探活通过"
    exit 0
  fi

  fail_msg "重启后仍失败；请检查宿主机 nvidia-smi、nvidia-container-toolkit 与驱动"
  exit 1
}

main "$@"
