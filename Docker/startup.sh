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

# 下载模型文件
echo "开始下载模型文件..."
chmod +x /server/Docker/downloader.sh
if /server/Docker/downloader.sh; then
    echo "✅ 模型下载完成"
else
    echo "❌ 模型下载失败，但继续启动服务"
fi

# 解压模型文件
echo "解压模型文件..."
extract_model() {
    local zip_file="$1"
    local target_dir="$2"
    
    if [ -f "$zip_file" ]; then
        echo "解压 $zip_file 到 $target_dir"
        cd "$target_dir" && unzip -o "$(basename "$zip_file")" && rm "$(basename "$zip_file")" && cd /server
        echo "✅ $zip_file 解压完成"
    else
        echo "⚠️  $zip_file 不存在，跳过"
    fi
}

extract_model "resource/chat/models/models.zip" "resource/chat/models"
extract_model "resource/sing/models/pallas/pallas.zip" "resource/sing/models/pallas"
extract_model "resource/sing/models/pretrain/pretrain.zip" "resource/sing/models/pretrain"
extract_model "resource/tts/tts.zip" "resource/tts"

echo "✅ 模型文件处理完成"

# 启动 Celery Worker (后台运行)
echo "启动 Celery Worker..."
nohup uv run celery -A app.core.celery worker --loglevel=info --concurrency=1 > logs/celery.log 2>&1 &
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

uv run uvicorn app.main:app --host 0.0.0.0 --port 9099 --log-level info