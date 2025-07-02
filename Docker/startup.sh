#!/bin/bash

set -e  # 出现错误立即退出
set -o pipefail  # 管道命令错误退出

# 切换到服务器目录
cd /server

# 确保日志目录存在
mkdir -p logs

echo "=== Pallas-Bot AI 启动脚本 ==="

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

# 启动 Celery Worker (后台运行)
echo "启动 Celery Worker..."
nohup /server/.venv/bin/python -m celery -A app.core.celery worker --loglevel=info --concurrency=1 > logs/celery.log 2>&1 &
CELERY_PID=$!

# 等待 Celery 启动并检查状态
sleep 5
if kill -0 $CELERY_PID 2>/dev/null; then
    echo "✅ Celery Worker 启动成功 (PID: $CELERY_PID)"
else
    echo "❌ Celery Worker 启动失败"
    exit 1
fi

# 启动 FastAPI 服务器
echo "启动 FastAPI 服务器..."
echo "=== 服务已启动 ==="
echo "API 地址: http://0.0.0.0:9099"
echo "================="

# 捕获信号以优雅关闭
trap 'echo "正在关闭服务..."; kill $CELERY_PID 2>/dev/null || true; exit 0' SIGTERM SIGINT

/server/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9099 --log-level info