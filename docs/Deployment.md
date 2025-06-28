# 部署指南

## 方式一（推荐）：使用 Docker 部署

## 方式二：手动部署

### 前置条件

- Python 环境

    本项目使用 `uv` 管理虚拟环境，对于本地已有的 Python 版本没有要求，`uv` 会自动配置适合本项目的 Python 版本。

    不推荐使用 `conda` 套 `uv`，可能会导致意料之外的问题，直接使用系统 Python 环境安装 `pipx` 和 `uv` 即可。

- Redis

    在这里 Redis 仅作为中间件，没有持久化需求，推荐直接使用 Docker 一行命令部署：

```bash
docker run -d --name redis -p 6379:6379 redis
```

### 步骤

1. 安装 uv

    ```bash
    # 如果没有安装 pipx，首先安装 pipx
    python -m pip install --user pipx
    python -m pipx ensurepath
    # 重新打开终端
    # 安装 uv
    pipx install uv
    ```

2. 配置虚拟环境并安装依赖

    ```bash
    uv venv --python 3.10
    uv lock
    # 使用 CPU 推理
    uv sync --all-groups --extra cpu
    # 使用 GPU 推理
    uv sync --all-groups --extra gpu
    ```

    如果只需要启用部分功能，可仅安装对应依赖：

    ```bash
    uv sync --group sing --extra gpu
    ```

    依赖 `group` 对应的功能如下：

    - `dev`: 开发环境
    - `chat`: 聊天
    - `sing`: 唱歌
    - `tts`: 语音合成

3. （如果启用了唱歌或 TTS 功能）更新 git 子模块

    ```bash
    git submodule update --init --recursive
    ```

4. 下载模型

    从 [huggingface](https://huggingface.co/pallasbot/Pallas-Bot/tree/main) 为你启用的 AI 功能下载模型，放到 `resource` 的对应目录下。

5. 配置环境变量

    请结合注释，根据实际情况修改 `.env` 文件中的配置。保持注释即使用默认值。

6. 启动 Celery Worker

    ```bash
    uv run celery -A app.core.celery worker --loglevel=info
    ```

7. 启动 FastAPI Server

    ```bash
    uv run uvicorn app.main:app --reload --port 9099
    ```
