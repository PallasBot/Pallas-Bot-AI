# 多阶段构建 - 构建阶段
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

ARG CUDA_VERSION=12.4

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1
ENV UV_CACHE_DIR=/tmp/uv-cache

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3-pip \
    build-essential \
    pkg-config \
    git \
    && ln -s /usr/bin/python3.10 /usr/bin/python \
    && pip3 install --no-cache-dir uv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/* \
    && rm -rf /root/.cache

WORKDIR /build

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 创建虚拟环境并安装依赖
RUN uv venv --python 3.10 \
    && uv sync --all-groups --extra gpu \
    && find /build/.venv -name "*.pyc" -delete \
    && find /build/.venv -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /tmp/uv-cache \
    && rm -rf /root/.cache

# 运行时阶段
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS runtime

ARG BUILDKIT_INLINE_CACHE=1
ARG CUDA_VERSION=12.4

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0
ENV PATH="/server/.venv/bin:$PATH"

LABEL org.opencontainers.image.title="Pallas-Bot AI"
LABEL org.opencontainers.image.description="AI-powered bot with chat, singing, and TTS capabilities"
LABEL org.opencontainers.image.vendor="Pallas-Bot"
LABEL org.opencontainers.image.version="latest"
LABEL org.opencontainers.image.cuda.version="${CUDA_VERSION}"

# 只安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    wget \
    curl \
    aria2 \
    unzip \
    ffmpeg \
    libsndfile1 \
    git \
    && ln -s /usr/bin/python3.10 /usr/bin/python \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

WORKDIR /server

# 从构建阶段复制虚拟环境
COPY --from=builder /build/.venv /server/.venv

# 创建必要的目录
RUN mkdir -p logs resource/chat/models resource/sing/models resource/tts

# 复制应用代码
COPY app/ ./app/
COPY Docker/ ./Docker/
COPY .env* ./

# Git相关操作
COPY .git* ./
RUN if [ -f .gitmodules ]; then \
        git init \
        && git config --global --add safe.directory /server \
        && git submodule update --init --recursive || true; \
    fi \
    && chmod +x /server/Docker/startup.sh /server/Docker/downloader.sh

CMD ["/server/Docker/startup.sh"]
