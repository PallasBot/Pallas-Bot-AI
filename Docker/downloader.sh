#!/bin/bash

echo "Downloading models..."

# 确保目录存在
mkdir -p /server/resource/chat/models
mkdir -p /server/resource/sing/models/pallas
mkdir -p /server/resource/sing/models/pretrain
mkdir -p /server/resource/tts

# 使用 aria2c 下载模型文件，支持断点续传和多线程下载
aria2c \
    --disable-ipv6 \
    --input-file /server/Docker/models.txt \
    --dir /server \
    --continue \
    --max-connection-per-server=4 \
    --split=4 \
    --max-tries=3 \
    --retry-wait=3

echo "Model download completed."