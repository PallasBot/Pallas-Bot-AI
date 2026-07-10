#!/usr/bin/env bash
# Pallas-Bot-AI 本地/半自动安装：依赖、.env、Redis、Ollama 模型、启停与健康检查。
#
# 用法:
#   ./scripts/ai_bootstrap.sh                 # LLM 栈：uv sync + Redis + Ollama + 启动 llm/api
#   ./scripts/ai_bootstrap.sh --check-only    # 仅体检，不改环境
#   ./scripts/ai_bootstrap.sh --no-start      # 装依赖与配置，不启动服务
#   ./scripts/ai_bootstrap.sh --with-media    # 额外安装 sing/tts/chat 并启动 media worker
#   ./scripts/ai_bootstrap.sh --remote-only   # 跳过 Ollama，适合 LLM_PROVIDER_MODE=remote_only
#   ./scripts/ai_bootstrap.sh --bot-host HOST --bot-port PORT
#
# 环境变量（非交互）:
#   PALLAS_BOT_HOST / PALLAS_BOT_PORT — callback 目标（默认 localhost:8088）
#   PALLAS_SKIP_REDIS=1               — 不尝试拉起 Redis 容器
#   PALLAS_GPU=1                      — uv sync 使用 --extra gpu
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CHECK_ONLY=0
NO_START=0
WITH_MEDIA=0
REMOTE_ONLY=0
BOT_HOST="${PALLAS_BOT_HOST:-localhost}"
BOT_PORT="${PALLAS_BOT_PORT:-8088}"
USE_GPU="${PALLAS_GPU:-0}"

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY=1 ;;
    --no-start) NO_START=1 ;;
    --with-media) WITH_MEDIA=1 ;;
    --remote-only) REMOTE_ONLY=1 ;;
    --bot-host) BOT_HOST="${2:?}"; shift ;;
    --bot-port) BOT_PORT="${2:?}"; shift ;;
    -h|--help) usage 0 ;;
    *) echo "未知参数: $1" >&2; usage 1 ;;
  esac
  shift
done

log() { printf '[bootstrap] %s\n' "$*"; }
warn() { printf '[bootstrap] 警告: %s\n' "$*" >&2; }
fail() { printf '[bootstrap] 错误: %s\n' "$*" >&2; exit 1; }

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

set_env_key() {
  local key="$1" value="$2"
  if [[ ! -f "$ROOT/.env" ]]; then
    printf '%s=%s\n' "$key" "$value" >>"$ROOT/.env"
    return 0
  fi
  if grep -qE "^${key}=" "$ROOT/.env"; then
    local tmp
    tmp="$(mktemp)"
    awk -v k="$key" -v v="$value" '
      $0 ~ "^" k "=" { print k "=" v; next }
      { print }
    ' "$ROOT/.env" >"$tmp"
    mv "$tmp" "$ROOT/.env"
  else
    printf '%s=%s\n' "$key" "$value" >>"$ROOT/.env"
  fi
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    log "uv: $(uv --version)"
    return 0
  fi
  fail "未找到 uv。请先安装: https://docs.astral.sh/uv/getting-started/installation/"
}

ensure_env_file() {
  if [[ -f "$ROOT/.env" ]]; then
    log ".env 已存在"
    return 0
  fi
  if [[ ! -f "$ROOT/.env.example" ]]; then
    fail "缺少 .env.example"
  fi
  cp "$ROOT/.env.example" "$ROOT/.env"
  log "已从 .env.example 复制 .env"
}

configure_callback() {
  local cur_host cur_port
  cur_host="$(read_env_key CALLBACK_HOST "")"
  cur_port="$(read_env_key CALLBACK_PORT "")"
  if [[ -z "$cur_host" || "$cur_host" == "localhost" ]]; then
    set_env_key CALLBACK_HOST "$BOT_HOST"
    log "CALLBACK_HOST=$BOT_HOST"
  else
    log "保留 CALLBACK_HOST=$cur_host"
  fi
  if [[ -z "$cur_port" ]]; then
    set_env_key CALLBACK_PORT "$BOT_PORT"
    log "CALLBACK_PORT=$BOT_PORT"
  else
    log "保留 CALLBACK_PORT=$cur_port"
  fi
  set_env_key LLM_CHAT_ENABLED "true"
}

redis_ping() {
  local url="${1:-redis://127.0.0.1:6379/0}"
  if command -v redis-cli >/dev/null 2>&1; then
    redis-cli -u "$url" ping 2>/dev/null | grep -q PONG && return 0
  fi
  if command -v uv >/dev/null 2>&1 && [[ -d "$ROOT/.venv" ]]; then
    REDIS_URL="$url" uv run --no-sync python - <<'PY' 2>/dev/null
import os, sys
import redis
url = os.environ["REDIS_URL"]
client = redis.Redis.from_url(url, socket_connect_timeout=1.0, socket_timeout=1.0)
client.ping()
PY
    return $?
  fi
  return 1
}

ensure_redis() {
  local url
  url="$(read_env_key REDIS_URL "redis://127.0.0.1:6379/0")"
  if redis_ping "$url"; then
    log "Redis 可达: $url"
    return 0
  fi
  if [[ "${PALLAS_SKIP_REDIS:-}" == "1" ]]; then
    warn "Redis 不可达且 PALLAS_SKIP_REDIS=1，跳过自动拉起"
    return 1
  fi
  if ! command -v docker >/dev/null 2>&1; then
    warn "Redis 不可达且无 docker，请手动启动 Redis 并设置 REDIS_URL"
    return 1
  fi
  log "尝试用 docker compose 拉起 Redis（docker-compose.4.0-ci.yml）..."
  docker compose -f "$ROOT/docker-compose.4.0-ci.yml" up -d
  local i
  for ((i = 0; i < 30; i++)); do
    if redis_ping "$url"; then
      log "Redis 已就绪"
      return 0
    fi
    sleep 1
  done
  warn "Redis 容器已启动但 ping 仍失败，请检查 REDIS_URL=$url"
  return 1
}

sync_deps() {
  log "安装 Python 依赖（uv sync --group dev）..."
  if [[ "$USE_GPU" == "1" ]]; then
    uv sync --group dev --extra gpu
  else
    uv sync --group dev --extra cpu
  fi
  if [[ "$WITH_MEDIA" == "1" ]]; then
    log "安装媒体任务依赖（sing/tts/chat）..."
    if [[ "$USE_GPU" == "1" ]]; then
      uv sync --all-groups --extra gpu
    else
      uv sync --all-groups --extra cpu
    fi
    if [[ -d "$ROOT/.git" ]]; then
      log "更新 git 子模块（媒体模型路径）..."
      git submodule update --init --recursive || warn "子模块更新失败，媒体功能可能不可用"
    fi
  fi
}

ollama_http_ok() {
  local base="${1:-http://127.0.0.1:11434}"
  curl -fsS --max-time 3 "${base%/}/api/tags" >/dev/null 2>&1
}

ensure_ollama_models() {
  if [[ "$REMOTE_ONLY" == "1" ]]; then
    set_env_key LLM_PROVIDER_MODE "remote_only"
    set_env_key LLM_AUTO_START "false"
    log "remote_only：跳过 Ollama 检测"
    return 0
  fi

  local backend model categorizer auto_start
  backend="$(read_env_key LLM_BACKEND_URL "http://127.0.0.1:11434")"
  model="$(read_env_key LLM_MODEL "qwen2.5:7b")"
  categorizer="$(read_env_key LLM_CATEGORIZER_MODEL "qwen2.5:0.5b")"
  auto_start="$(read_env_key LLM_AUTO_START "true")"

  if ollama_http_ok "$backend"; then
    log "Ollama 已可达: $backend"
  elif [[ "$auto_start" == "true" ]] && command -v ollama >/dev/null 2>&1; then
    log "后台拉起 ollama serve..."
    nohup ollama serve >>"$ROOT/logs/ollama-bootstrap.log" 2>&1 &
    local i
    for ((i = 0; i < 60; i++)); do
      if ollama_http_ok "$backend"; then
        log "Ollama 已就绪"
        break
      fi
      sleep 1
    done
  else
    warn "Ollama 不可达 ($backend)。可设 LLM_AUTO_START=true 并安装 ollama，或用 --remote-only / Docker: docker compose -f docker-compose.llm.yml up -d"
    return 1
  fi

  if command -v ollama >/dev/null 2>&1; then
    log "拉取主模型 $model ..."
    ollama pull "$model" || warn "拉取 $model 失败"
    if [[ -n "$categorizer" && "$categorizer" != "$model" ]]; then
      log "拉取分类模型 $categorizer ..."
      ollama pull "$categorizer" || warn "拉取 $categorizer 失败"
    fi
  else
    local host="${backend#*://}"
    host="${host%%/*}"
    log "通过 HTTP 拉取模型（无 ollama CLI）..."
    curl -fsS -X POST "${backend%/}/api/pull" -d "{\"name\":\"${model}\"}" >/dev/null || warn "HTTP pull $model 失败"
    if [[ -n "$categorizer" && "$categorizer" != "$model" ]]; then
      curl -fsS -X POST "${backend%/}/api/pull" -d "{\"name\":\"${categorizer}\"}" >/dev/null || warn "HTTP pull $categorizer 失败"
    fi
  fi
}

start_services() {
  if [[ "$NO_START" == "1" ]]; then
    log "--no-start：跳过启停"
    return 0
  fi
  mkdir -p "$ROOT/logs"
  log "启动 AI 服务（ctl.sh）..."
  if [[ "$WITH_MEDIA" == "1" ]]; then
    "$ROOT/scripts/ctl.sh" start all
  else
    "$ROOT/scripts/ctl.sh" start llm
    "$ROOT/scripts/ctl.sh" start api
  fi
}

health_check() {
  local port api_base
  port="$(read_env_key UVICORN_PORT "9099")"
  api_base="http://127.0.0.1:${port}"
  log "健康检查 $api_base/health ..."
  if ! curl -fsS --max-time 10 "${api_base}/health" | python3 -m json.tool; then
    warn "健康检查失败；查看 logs/uvicorn.log 与 logs/celery.log"
    return 1
  fi
  return 0
}

print_next_steps() {
  cat <<EOF

── 下一步（Bot 侧）──
1. 在 Bot 的 config/pallas.toml 的 [env] 或 WebUI「智能对话与 AI 服务」配置：
   LLM_CHAT_ENABLED=true
   AI_SERVER_HOST=127.0.0.1
   AI_SERVER_PORT=9099
2. 确认 AI 能回调 Bot：CALLBACK_HOST=$(read_env_key CALLBACK_HOST "$BOT_HOST") CALLBACK_PORT=$(read_env_key CALLBACK_PORT "$BOT_PORT")
3. Docker 同网部署时 CALLBACK_HOST 填 Bot 服务名（如 pallasbot），见 docker-compose.full.yml

常用命令:
  ./scripts/ctl.sh status
  ./scripts/ctl.sh restart llm
  curl -s http://127.0.0.1:9099/health | python3 -m json.tool

EOF
}

main() {
  ensure_uv
  ensure_env_file
  configure_callback

  if [[ "$CHECK_ONLY" == "1" ]]; then
    ensure_redis || true
    if [[ "$REMOTE_ONLY" != "1" ]]; then
      ollama_http_ok "$(read_env_key LLM_BACKEND_URL "http://127.0.0.1:11434")" && log "Ollama OK" || warn "Ollama 不可达"
      if [[ "${OLLAMA_SKIP_GPU:-}" != "1" ]] && [[ "$REMOTE_ONLY" != "1" ]]; then
        "$ROOT/scripts/ollama_gpu_watchdog.sh" --quiet || warn "Ollama GPU 探活失败，可执行: ./scripts/ollama_gpu_watchdog.sh --fix"
      fi
    fi
    health_check || true
    exit 0
  fi

  sync_deps
  ensure_redis || true
  ensure_ollama_models || true
  start_services
  sleep 3
  health_check || true
  print_next_steps
}

main "$@"
