#!/bin/bash

set -e  # 出现错误立即退出
set -o pipefail  # 管道命令错误退出

# 切换到服务器目录
cd /server

# 确保日志目录存在
mkdir -p logs

echo "=== Pallas-Bot AI 启动脚本 ==="

detect_cuda_home() {
    if [ -n "${CUDA_HOME:-}" ] && [ -d "${CUDA_HOME:-}" ]; then
        return 0
    fi
    for candidate in /usr/local/cuda /usr/local/cuda-12.4 /usr/local/cuda-12; do
        if [ -d "$candidate" ]; then
            export CUDA_HOME="$candidate"
            echo "✅ CUDA_HOME=$CUDA_HOME"
            return 0
        fi
    done
}

detect_cuda_home

# 检查 GPU 可用性
echo "检查 GPU 可用性..."
if nvidia-smi > /dev/null 2>&1; then
    echo "✅ GPU 可用"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "⚠️  GPU 不可用，将使用 CPU 模式"
fi

# 检查并下载模型文件
echo "检查模型文件..."

# 老用户升级：权重已在但无 .extracted 时补标记，避免误触发全量下载
if [ -x /server/.venv/bin/python ]; then
    /server/.venv/bin/python -c "from app.media_assets import heal_extracted_markers; print(heal_extracted_markers())" \
        && echo "✅ 已按内容补齐媒体权重标记" \
        || echo "⚠️  补齐媒体权重标记失败，继续按标记文件检查"
fi

# 定义模型解压标记文件列表
MODEL_MARKERS=(
    "resource/chat/models/.extracted"
    "resource/sing/models/pallas/.extracted"
    "resource/sing/models/pretrain/.extracted"
    "resource/tts/.extracted"
)

# 检查是否需要下载
NEED_DOWNLOAD=false
for marker_file in "${MODEL_MARKERS[@]}"; do
    if [ ! -f "$marker_file" ]; then
        echo "⚠️  $(dirname "$marker_file") 模型未解压，需要下载"
        NEED_DOWNLOAD=true
    else
        echo "✅ $(dirname "$marker_file") 模型已解压，跳过下载"
    fi
done

# 只有在需要时才下载
if [ "$NEED_DOWNLOAD" = true ]; then
    echo "开始下载缺失的模型文件..."
    chmod +x /server/Docker/downloader.sh
    if /server/Docker/downloader.sh; then
        echo "✅ 模型下载完成"
    else
        echo "❌ 模型下载失败，但继续启动服务"
    fi
else
    echo "✅ 所有模型文件都已存在，跳过下载"
fi

# 解压模型文件
echo "解压模型文件..."
extract_model() {
    local zip_file="$1"
    local target_dir="$2"
    local marker_file="$3"
    
    if [ -f "$zip_file" ]; then
        echo "解压 $zip_file 到 $target_dir"
        cd "$target_dir" && unzip -o "$(basename "$zip_file")" && rm "$(basename "$zip_file")" && cd /server
        # 创建解压完成标记文件
        touch "$marker_file"
        echo "✅ $zip_file 解压完成，创建标记文件 $marker_file"
    else
        echo "⚠️  $zip_file 不存在，跳过"
    fi
}

extract_model "resource/chat/models/models.zip" "resource/chat/models" "resource/chat/models/.extracted"
extract_model "resource/sing/models/pallas/pallas.zip" "resource/sing/models/pallas" "resource/sing/models/pallas/.extracted"
extract_model "resource/sing/models/pretrain/pretrain.zip" "resource/sing/models/pretrain" "resource/sing/models/pretrain/.extracted"
extract_model "resource/tts/tts.zip" "resource/tts" "resource/tts/.extracted"

echo "✅ 模型文件处理完成"

if [ "${LLM_CHAT_ENABLED:-true}" != "false" ]; then
  echo "检查本地 LLM 后端..."
  /server/.venv/bin/python -c "from app.core.llm_backend_runtime import ensure_local_backend_ready_sync; ensure_local_backend_ready_sync()"
fi

stop_child() {
    local pid="$1"
    local name="$2"
    if kill -0 "$pid" 2>/dev/null; then
        echo "停止 $name (PID: $pid)..."
        kill -TERM "$pid" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "$pid" 2>/dev/null || return 0
            sleep 1
        done
        echo "$name 超时，强制 SIGKILL"
        kill -KILL "$pid" 2>/dev/null || true
    fi
}

shutdown_all() {
    echo "正在关闭服务..."
    stop_child "${UVICORN_PID:-0}" "FastAPI"
    stop_child "${CELERY_MEDIA_PID:-0}" "Celery Media Worker"
    stop_child "${CELERY_PID:-0}" "Celery Worker"
}

trap 'shutdown_all; exit 0' SIGTERM SIGINT

# 启动 Celery Worker —— 拆成两个进程，按队列隔离：
#   default 队列：LLM 推理任务（包 llm）
#   media   队列：唱歌 / TTS / 旧版 chat 等 GPU 媒体任务（包 sing,tts,chat）
# 否则单进程单线程池会让媒体任务卡死时连带 LLM 一起哑掉（见昨晚 7h 卡死）。
echo "启动 Celery Worker (default 队列: LLM)..."
CELERY_TASK_PACKAGES="${AI_DEFAULT_WORKER_PACKAGES:-llm}" \
    /server/.venv/bin/python -m celery -A app.core.celery worker \
    --loglevel=warning -Q default -n default@%h >> logs/celery.log 2>&1 &
CELERY_PID=$!

# 等待 Celery 启动并检查状态
sleep 5
if kill -0 "$CELERY_PID" 2>/dev/null; then
    echo "✅ Celery Worker (default) 启动成功 (PID: $CELERY_PID)"
else
    echo "❌ Celery Worker (default) 启动失败"
    exit 1
fi

# 默认启 media（全功能镜像）。纯 LLM / remote-only 可设 AI_ENABLE_MEDIA_WORKER=0 省资源。
CELERY_MEDIA_PID=0
if [ "${AI_ENABLE_MEDIA_WORKER:-1}" != "0" ]; then
    echo "启动 Celery Worker (media 队列: 唱歌/TTS/chat)..."
    CELERY_TASK_PACKAGES="${AI_MEDIA_WORKER_PACKAGES:-sing,tts,chat}" \
        /server/.venv/bin/python -m celery -A app.core.celery worker \
        --loglevel=warning -Q media -n media@%h >> logs/celery-media.log 2>&1 &
    CELERY_MEDIA_PID=$!

    sleep 5
    if kill -0 "$CELERY_MEDIA_PID" 2>/dev/null; then
        echo "✅ Celery Worker (media) 启动成功 (PID: $CELERY_MEDIA_PID)"
    else
        echo "❌ Celery Worker (media) 启动失败"
        stop_child "$CELERY_PID" "Celery Worker"
        exit 1
    fi
else
    echo "跳过 media worker（AI_ENABLE_MEDIA_WORKER=0）"
fi

# 启动 FastAPI 服务器 (后台运行，由当前脚本统一托管两个子进程)
echo "启动 FastAPI 服务器..."
/server/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9099 --log-level warning >> logs/uvicorn.log 2>&1 &
UVICORN_PID=$!

sleep 3
if kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "✅ FastAPI 启动成功 (PID: $UVICORN_PID)"
else
    echo "❌ FastAPI 启动失败"
    stop_child "$CELERY_MEDIA_PID" "Celery Media Worker"
    stop_child "$CELERY_PID" "Celery Worker"
    exit 1
fi

echo "=== 服务已启动 ==="
echo "API 地址: http://0.0.0.0:9099"
echo "Celery (default) PID: $CELERY_PID"
echo "Celery (media)   PID: $CELERY_MEDIA_PID"
echo "Uvicorn PID: $UVICORN_PID"
echo "================="

# 任何一个子进程退出，都结束其它进程并让容器退出，避免只剩半边服务。
while true; do
    if ! kill -0 "$CELERY_PID" 2>/dev/null; then
        echo "❌ Celery Worker (default) 已退出"
        stop_child "$UVICORN_PID" "FastAPI"
        stop_child "$CELERY_MEDIA_PID" "Celery Media Worker"
        wait "$CELERY_PID"
        exit 1
    fi
    if ! kill -0 "$CELERY_MEDIA_PID" 2>/dev/null; then
        echo "❌ Celery Worker (media) 已退出"
        stop_child "$UVICORN_PID" "FastAPI"
        stop_child "$CELERY_PID" "Celery Worker"
        wait "$CELERY_MEDIA_PID"
        exit 1
    fi
    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
        echo "❌ FastAPI 已退出"
        stop_child "$CELERY_PID" "Celery Worker"
        stop_child "$CELERY_MEDIA_PID" "Celery Media Worker"
        wait "$UVICORN_PID"
        exit 1
    fi
    sleep 2
done
