FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

ARG BUILDKIT_INLINE_CACHE=1
ARG CUDA_VERSION=12.4

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0
ENV PIP_NO_CACHE_DIR=1
ENV UV_CACHE_DIR=/tmp/uv-cache

LABEL org.opencontainers.image.title="Pallas-Bot AI"
LABEL org.opencontainers.image.description="AI-powered bot with chat, singing, and TTS capabilities"
LABEL org.opencontainers.image.vendor="Pallas-Bot"
LABEL org.opencontainers.image.version="latest"
LABEL org.opencontainers.image.cuda.version="${CUDA_VERSION}"

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

RUN ln -s /usr/bin/python3.10 /usr/bin/python

RUN pip3 install --no-cache-dir uv

WORKDIR /server

COPY pyproject.toml uv.lock ./

RUN uv venv --python 3.10 && \
    uv sync --all-groups --extra gpu && \
    rm -rf /tmp/uv-cache

COPY app/ ./app/
COPY Docker/ ./Docker/

COPY .env* ./

RUN mkdir -p logs resource/chat/models resource/sing/models resource/tts

COPY .git* ./
RUN if [ -f .gitmodules ]; then \
        git init && \
        git config --global --add safe.directory /server && \
        git submodule update --init --recursive || true; \
    fi

RUN chmod +x /server/Docker/startup.sh /server/Docker/downloader.sh

CMD ["/server/Docker/startup.sh"]
