#!/usr/bin/env bash
# Pallas-Bot-AI 本地/半自动安装：媒体依赖、.env、Redis、启停与健康检查。

# 聊天 / 画画默认由 Bot 内核或插件直连，本仓 bootstrap 面向唱歌 / TTS 等媒体服务。

# 用法:
#   ./scripts/ai_bootstrap.sh                 # 装媒体依赖 + Redis + 启动 media/api
#   ./scripts/ai_bootstrap.sh --check-only    # 仅体检，不改环境
#   ./scripts/ai_bootstrap.sh --no-start      # 装依赖与配置，不启动服务
#   ./scripts/ai_bootstrap.sh --bot-host HOST --bot-port PORT
#   PALLAS_GPU=1 ./scripts/ai_bootstrap.sh    # uv sync 使用 --extra gpu

# 兼容（已忽略，可去掉）:
#   --with-media   历史 LLM-only 时代的媒体开关；现默认即媒体栈
#   --remote-only  历史跳过 Ollama；聊天已不经本仓

# 环境变量（非交互）:
#   PALLAS_BOT_HOST / PALLAS_BOT_PORT — callback 目标（默认 localhost:8088）
#   PALLAS_SKIP_REDIS=1               — 不尝试拉起 Redis 容器
#   PALLAS_GPU=1                      — uv sync 使用 --extra gpu（否则 --extra cpu）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# 从 Bot 控制台拉起时可能继承 Bot 的 VIRTUAL_ENV，导致 uv 警告
unset VIRTUAL_ENV VIRTUAL_ENV_PROMPT UV_PROJECT UV_PROJECT_ENVIRONMENT PYTHONHOME || true

CHECK_ONLY=0
NO_START=0
BOT_HOST="${PALLAS_BOT_HOST:-localhost}"
BOT_PORT="${PALLAS_BOT_PORT:-8088}"
USE_GPU="${PALLAS_GPU:-0}"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY=1 ;;
    --no-start) NO_START=1 ;;
    --with-media)
      # 兼容旧调用：默认已是媒体栈
      ;;
    --remote-only)
      printf '[bootstrap] 警告: --remote-only 已忽略（聊天/画画不经本仓 Ollama）\n' >&2
      ;;
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

is_windows_host() {
  case "$(uname -s 2>/dev/null || true)" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
  esac
  [[ -n "${WINDIR:-}" || -n "${SystemRoot:-}" ]]
}

docker_engine_error_looks_desktop() {
  local err="${1:-}"
  printf '%s' "$err" | grep -qiE \
    'dockerDesktopLinuxEngine|npipe:|Is the docker daemon running|failed to connect to the docker API|cannot find the file specified|The system cannot find the file specified'
}

warn_redis_manual_fallback() {
  local url="${1:-redis://127.0.0.1:6379/0}"
  warn "也可不用 Docker：本机或 WSL 自备 Redis，在 .env 设置 REDIS_URL=${url}"
}

warn_docker_desktop_hint() {
  warn "Windows：请安装并启动 Docker Desktop，托盘图标就绪后再重试"
  warn "安装说明: https://docs.docker.com/desktop/setup/install/windows-install/"
}

ensure_redis() {
  local url compose_out compose_rc info_err info_rc i
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
    warn "Redis 不可达且未找到 docker"
    if is_windows_host; then
      warn_docker_desktop_hint
    else
      warn "请安装 Docker，或手动启动 Redis"
    fi
    warn_redis_manual_fallback "$url"
    return 1
  fi

  set +e
  info_err="$(docker info 2>&1)"
  info_rc=$?
  set -e
  if [[ "$info_rc" -ne 0 ]]; then
    warn "检测到 Docker CLI，但引擎未运行（docker info 失败）"
    if is_windows_host || docker_engine_error_looks_desktop "$info_err"; then
      warn_docker_desktop_hint
    else
      warn "请启动 Docker 守护进程后再重试"
    fi
    warn_redis_manual_fallback "$url"
    return 1
  fi

  log "尝试用 docker compose 拉起 Redis（docker-compose.4.0-ci.yml）..."
  set +e
  compose_out="$(docker compose -f "$ROOT/docker-compose.4.0-ci.yml" up -d 2>&1)"
  compose_rc=$?
  set -e
  if [[ "$compose_rc" -ne 0 ]]; then
    warn "docker compose 拉起 Redis 失败（exit ${compose_rc}）"
    if [[ -n "$compose_out" ]]; then
      printf '%s\n' "$compose_out" | tail -n 12 | while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -n "$line" ]] && warn "  $line"
      done
    fi
    if is_windows_host || docker_engine_error_looks_desktop "$compose_out"; then
      warn_docker_desktop_hint
    fi
    warn_redis_manual_fallback "$url"
    return 1
  fi

  for ((i = 0; i < 30; i++)); do
    if redis_ping "$url"; then
      log "Redis 已就绪"
      return 0
    fi
    sleep 1
  done
  warn "Redis 容器已拉起但暂不可达，请检查 REDIS_URL=${url}"
  warn "可执行: docker compose -f docker-compose.4.0-ci.yml ps"
  warn_redis_manual_fallback "$url"
  return 1
}

sync_deps() {
  # 媒体栈：sing/tts 等需要 torch（cpu|gpu）。聊天 / 画画不依赖本仓 LLM worker。
  if [[ "$USE_GPU" == "1" ]]; then
    log "安装媒体任务依赖（sing/tts + torch GPU）..."
    uv sync --all-groups --extra gpu
  else
    log "安装媒体任务依赖（sing/tts + torch CPU）..."
    uv sync --all-groups --extra cpu
  fi
  set_env_key CELERY_TASK_PACKAGES "all"
  if [[ -d "$ROOT/.git" ]]; then
    log "更新 git 子模块（媒体模型路径）..."
    git submodule update --init --recursive || warn "子模块更新失败，媒体功能可能不可用"
  fi
}

check_ffmpeg() {
  if command -v ffmpeg >/dev/null 2>&1; then
    log "已检测到 ffmpeg: $(command -v ffmpeg)"
    return 0
  fi
  warn "未在 PATH 中找到 ffmpeg。唱歌 / TTS 音频处理可能失败（pydub 会告警 Couldn't find ffmpeg）。"
  if [[ "${OS:-}" == "Windows_NT" ]] || uname -s 2>/dev/null | grep -qiE 'mingw|msys|cygwin'; then
    warn "Windows：请安装 ffmpeg 并加入 PATH，或把 ffmpeg.exe / ffprobe.exe 放到本仓可用路径后重开终端。"
    warn "可用 winget：winget install --id Gyan.FFmpeg -e  （装完新开终端再启动媒体服务）"
  else
    warn "Linux：sudo apt install ffmpeg ；macOS：brew install ffmpeg"
  fi
  return 1
}

start_services() {
  if [[ "$NO_START" == "1" ]]; then
    log "--no-start：跳过启停"
    return 0
  fi
  mkdir -p "$ROOT/logs"
  local url
  url="$(read_env_key REDIS_URL "redis://127.0.0.1:6379/0")"
  if ! redis_ping "$url"; then
    warn "Redis 仍不可达（${url}）；media worker 依赖 Redis，启动可能失败"
  fi
  log "启动媒体服务（先 API，再 media worker）..."
  # 分开启：media 失败时也不要挡住 API（Bot 连 9099 需要 API）
  local start_rc=0
  if ! "$ROOT/scripts/ctl.sh" start api; then
    warn "API 启动失败，见 logs/uvicorn.log"
    start_rc=1
  fi
  if ! "$ROOT/scripts/ctl.sh" start media; then
    warn "media worker 启动失败，见 logs/celery-media.log（唱歌/TTS 会不可用；API 仍可单独排查）"
    start_rc=1
  fi
  return "$start_rc"
}

health_check() {
  local port api_base
  port="$(read_env_key UVICORN_PORT "9099")"
  api_base="http://127.0.0.1:${port}"
  log "健康检查 $api_base/health ..."
  if ! command -v curl >/dev/null 2>&1; then
    warn "未找到 curl，跳过健康检查"
    return 1
  fi
  # Windows 常只有 python，没有 python3
  if ! curl -fsS --max-time 10 "${api_base}/health" | json_pretty; then
    warn "健康检查失败；查看 logs/uvicorn.log 与 logs/celery-media.log"
    return 1
  fi
  return 0
}

json_pretty() {
  if command -v python >/dev/null 2>&1; then
    python -m json.tool
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m json.tool
  elif command -v uv >/dev/null 2>&1; then
    uv run --no-sync python -m json.tool
  else
    cat
  fi
}

print_next_steps() {
  local ai_port
  ai_port="$(read_env_key UVICORN_PORT "9099")"
  cat <<EOF

── 下一步（Bot 侧）──
1. 聊天 / 画画：Bot「接入」Provider 与画画插件直连，不必经本仓
2. 媒体（唱歌 / TTS）：WebUI「媒体 → 媒体服务」保存基址并测通
   AI_SERVER_HOST=127.0.0.1
   AI_SERVER_PORT=${ai_port}
3. 确认回调：CALLBACK_HOST=$(read_env_key CALLBACK_HOST "$BOT_HOST") CALLBACK_PORT=$(read_env_key CALLBACK_PORT "$BOT_PORT")
4. GPU torch：PALLAS_GPU=1 ./scripts/ai_bootstrap.sh

常用命令:
  ./scripts/ctl.sh status
  ./scripts/ctl.sh restart media
  curl -s http://127.0.0.1:${ai_port}/health | python -m json.tool

EOF
}

main() {
  ensure_uv
  ensure_env_file
  configure_callback

  if [[ "$CHECK_ONLY" == "1" ]]; then
    ensure_redis || true
    check_ffmpeg || true
    health_check || true
    exit 0
  fi

  sync_deps
  check_ffmpeg || true
  ensure_redis || true
  start_services || warn "部分服务启动失败；继续健康检查与后续提示"
  sleep 3
  health_check || true
  print_next_steps
}

main "$@"
