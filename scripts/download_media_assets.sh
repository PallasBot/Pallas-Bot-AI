#!/usr/bin/env bash
# 源码/可写目录下拉取并解压 chat/sing/tts 默认权重（与 Docker/startup 对齐）。
set -euo pipefail

ROOT="${PALLAS_AI_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

mkdir -p \
  resource/chat/models \
  resource/sing/models/pallas \
  resource/sing/models/pretrain \
  resource/tts

if [[ -x "$ROOT/Docker/downloader.sh" ]] || [[ -f "$ROOT/Docker/downloader.sh" ]]; then
  if command -v aria2c >/dev/null 2>&1; then
    echo "using Docker/downloader.sh (aria2c)"
    # downloader 假设 cwd=/server；用相对路径时先 cd ROOT
    bash "$ROOT/Docker/downloader.sh" || {
      # downloader 内写死 /server；失败则走 python 回退
      echo "aria2 downloader failed or paths mismatch; falling back to python"
      uv run python -c "from app.media_assets import download_and_extract_missing; download_and_extract_missing()"
      exit 0
    }
  else
    echo "aria2c not found; using python downloader"
    uv run python -c "from app.media_assets import download_and_extract_missing; download_and_extract_missing()"
  fi
else
  uv run python -c "from app.media_assets import download_and_extract_missing; download_and_extract_missing()"
fi

extract_one() {
  local zip_file="$1"
  local target_dir="$2"
  local marker="$3"
  if [[ -f "$marker" ]]; then
    echo "skip extract: $marker exists"
    return 0
  fi
  if [[ ! -f "$zip_file" ]]; then
    echo "missing zip: $zip_file"
    return 1
  fi
  echo "extract $zip_file -> $target_dir"
  (cd "$target_dir" && unzip -o "$(basename "$zip_file")" && rm -f "$(basename "$zip_file")")
  touch "$marker"
}

# python 路径已含解压；若仅 aria2 下好 zip 则在此解压
extract_one "resource/chat/models/models.zip" "resource/chat/models" "resource/chat/models/.extracted" || true
extract_one "resource/sing/models/pallas/pallas.zip" "resource/sing/models/pallas" "resource/sing/models/pallas/.extracted" || true
extract_one "resource/sing/models/pretrain/pretrain.zip" "resource/sing/models/pretrain" "resource/sing/models/pretrain/.extracted" || true
extract_one "resource/tts/tts.zip" "resource/tts" "resource/tts/.extracted" || true

echo "media assets download finished"
