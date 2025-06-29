FROM nvidia/cuda:12.4-devel-ubuntu22.04

# 设置构建参数
ARG BUILDKIT_INLINE_CACHE=1
ARG CUDA_VERSION=12.4

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0
ENV PIP_NO_CACHE_DIR=1
ENV UV_CACHE_DIR=/tmp/uv-cache

# 设置标签
LABEL org.opencontainers.image.title="Pallas-Bot AI"
LABEL org.opencontainers.image.description="AI-powered bot with chat, singing, and TTS capabilities"
LABEL org.opencontainers.image.vendor="Pallas-Bot"
LABEL org.opencontainers.image.version="latest"
LABEL org.opencontainers.image.cuda.version="${CUDA_VERSION}"

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    git \
    wget \
    curl \
    aria2 \
    unzip \
    ffmpeg \
    build-essential \
    pkg-config \
    libsndfile1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建软链接
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# 安装 uv
RUN pip3 install --no-cache-dir uv

# 设置工作目录
WORKDIR /server

# 复制依赖文件（利用 Docker 层缓存）
COPY pyproject.toml uv.lock ./

# 创建虚拟环境并安装 Python 依赖 (GPU 版本，包含所有功能)
RUN uv venv --python 3.10 && \
    uv sync --all-groups --extra gpu && \
    rm -rf /tmp/uv-cache

# 复制应用代码
COPY app/ ./app/
COPY Docker/ ./Docker/

# 复制配置文件
COPY .env* ./

# 创建必要的目录
RUN mkdir -p logs resource/chat/models resource/sing/models resource/tts

# 处理 git 子模块（如果存在）
COPY .git* ./
RUN if [ -f .gitmodules ]; then \
        git init && \
        git config --global --add safe.directory /server && \
        git submodule update --init --recursive || true; \
    fi

# 设置启动脚本权限
RUN chmod +x /server/Docker/startup.sh /server/Docker/downloader.sh

# 创建非 root 用户（安全最佳实践）
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /server

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:9099/health || exit 1

# 暴露端口
EXPOSE 9099

# 切换到非 root 用户
USER appuser

# 启动命令
CMD ["/server/Docker/startup.sh"]
