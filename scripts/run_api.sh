#!/usr/bin/env bash
# 启动 FastAPI；默认不热重载。开发：UVICORN_RELOAD=true ./scripts/run_api.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec uv run python -m app.run_api "$@"
