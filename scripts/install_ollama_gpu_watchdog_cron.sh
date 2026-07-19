#!/usr/bin/env bash
# 将 Ollama GPU watchdog 安装为 /etc/cron.d/pallas-ollama-gpu
#
# 用法:
#   sudo ./scripts/install_ollama_gpu_watchdog_cron.sh
#   sudo OLLAMA_CONTAINER=ollama ./scripts/install_ollama_gpu_watchdog_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="/etc/cron.d/pallas-ollama-gpu"
SOURCE="$ROOT/deploy/ollama-gpu-watchdog.cron.example"
CONTAINER="${OLLAMA_CONTAINER:-ollama}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请使用 root 运行: sudo $0" >&2
  exit 1
fi

if [[ ! -f "$SOURCE" ]]; then
  echo "缺少 $SOURCE" >&2
  exit 1
fi

chmod +x "$ROOT/scripts/ollama_gpu_watchdog.sh"

sed \
  -e "s|/path/to/Pallas-Bot-AI|$ROOT|g" \
  -e "s|^OLLAMA_CONTAINER=ollama$|OLLAMA_CONTAINER=${CONTAINER}|" \
  -e "s|OLLAMA_CONTAINER=ollama /|OLLAMA_CONTAINER=${CONTAINER} /|" \
  "$SOURCE" >"$TARGET"
chmod 644 "$TARGET"

echo "已写入 $TARGET"
echo "日志: /var/log/ollama-gpu-watchdog.log"
echo "手动探活: OLLAMA_CONTAINER=${CONTAINER} $ROOT/scripts/ollama_gpu_watchdog.sh"
