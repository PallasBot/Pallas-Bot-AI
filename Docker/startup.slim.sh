#!/bin/bash
# LLM-only 启动：不下载媒体模型、不启 media worker。
set -e
set -o pipefail

cd /server
mkdir -p logs

echo "=== Pallas-Bot AI (slim / LLM-only) ==="

if [ "${LLM_AUTO_START:-false}" = "true" ] || [ "${LLM_AUTO_START:-0}" = "1" ]; then
  echo "预热本地 LLM backend…"
  /server/.venv/bin/python -c "from app.core.llm_backend_runtime import ensure_local_backend_ready_sync; ensure_local_backend_ready_sync()" || true
fi

stop_child() {
    local pid="$1"
    local name="$2"
    if [ -n "$pid" ] && [ "$pid" != "0" ] && kill -0 "$pid" 2>/dev/null; then
        echo "停止 $name (PID: $pid)..."
        kill -TERM "$pid" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "$pid" 2>/dev/null || return 0
            sleep 1
        done
        kill -KILL "$pid" 2>/dev/null || true
    fi
}

shutdown_all() {
    echo "正在关闭服务..."
    stop_child "${UVICORN_PID:-0}" "FastAPI"
    stop_child "${CELERY_PID:-0}" "Celery Worker"
}

trap 'shutdown_all; exit 0' SIGTERM SIGINT

echo "启动 Celery Worker (default 队列: LLM)..."
CELERY_TASK_PACKAGES="${AI_DEFAULT_WORKER_PACKAGES:-llm}" \
    /server/.venv/bin/python -m celery -A app.core.celery worker \
    --loglevel=warning -Q default -n default@%h >> logs/celery.log 2>&1 &
CELERY_PID=$!

sleep 5
if kill -0 "$CELERY_PID" 2>/dev/null; then
    echo "✅ Celery Worker (default) 启动成功 (PID: $CELERY_PID)"
else
    echo "❌ Celery Worker (default) 启动失败"
    exit 1
fi

echo "跳过 media worker（slim 镜像）"

echo "启动 FastAPI 服务器..."
/server/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9099 --log-level warning >> logs/uvicorn.log 2>&1 &
UVICORN_PID=$!

sleep 3
if kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "✅ FastAPI 启动成功 (PID: $UVICORN_PID)"
else
    echo "❌ FastAPI 启动失败"
    stop_child "$CELERY_PID" "Celery Worker"
    exit 1
fi

echo "=== 服务已启动（模型请在 WebUI 接入页拉取/切换）==="
echo "API: http://0.0.0.0:9099"

while true; do
    if ! kill -0 "$CELERY_PID" 2>/dev/null; then
        echo "❌ Celery Worker 已退出"
        stop_child "$UVICORN_PID" "FastAPI"
        wait "$CELERY_PID"
        exit 1
    fi
    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
        echo "❌ FastAPI 已退出"
        stop_child "$CELERY_PID" "Celery Worker"
        wait "$UVICORN_PID"
        exit 1
    fi
    sleep 2
done
