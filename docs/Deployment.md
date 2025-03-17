# 部署指南

## 方式一（推荐）：使用 Docker 部署

## 方式二：手动部署

### 前置条件

对于手动部署，首先需要在本地安装并配置好 Redis, 以及 Python 3.9.x 环境。

### 步骤

1. 安装 uv

    ```bash
    # 如果没有安装 pipx，首先安装 pipx
    python -m pip install --user pipx
    python -m pipx ensurepath
    # 安装 uv
    pipx install uv
    ```

2. 配置虚拟环境并安装依赖

    ```bash
    uv venv --python 3.9
    uv lock
    # 使用 CPU 推理
    uv sync --all-groups --extra cpu
    # 使用 GPU 推理
    uv sync --all-groups --extra gpu
    ```

    如果只需要启用部分功能，可仅安装对应依赖：

    ```bash
    uv sync --group sing --extra cpu
    ```

    依赖 `group` 对应的功能如下：

    - `dev`: 开发环境
    - `lint`: 代码检查
    - `chat`: 聊天
    - `sing`: 唱歌
    - `tts`: 语音合成

3. 配置环境变量

    请结合注释，根据实际情况修改 `.env` 文件中的配置。

4. 启动 Celery Worker

    ```bash
    celery -A app.core.celery worker --loglevel=info
    ```

5. 启动 FastAPI Server

    ```bash
    uvicorn app.main:app --reload --port 8000
    ```
