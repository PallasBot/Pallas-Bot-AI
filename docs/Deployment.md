# 部署指南

## 方式一（推荐）：使用 Docker 部署

本项目的 `docker-compose.yml` 提供了全栈服务一键部署。

### 前置条件

- **Docker 和 Docker Compose**
  
  请确保已[安装 Docker 和 Docker Compose](https://github.com/PallasBot/Pallas-Bot/blob/master/docs/DockerDeployment.md#%E5%AE%89%E8%A3%85-docker-%E4%B8%8E-docker-compose)。

- **NVIDIA Docker 支持（GPU 版本）**
  
  请确保已在宿主机上 [安装 CUDA 12.4](https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/index.html) ，[安装 container toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)（Windows 用户请使用 WSL2 环境安装 `container toolkit`）。

  可以使用 `nvidia-smi` 命令检查 GPU 是否可用、CUDA 是否已安装：

  ```bash
   nvidia-smi
   ```

### 快速部署

1. **复制 `docker-compose.yml` 文件**

   无需克隆本项目，只需将本项目根目录下的 `docker-compose.yml` 文件复制到你的工作目录。

2. **配置环境变量**

   在当前工作目录下创建 `pallas-bot-ai` 目录并将项目根目录下的 `.env` 文件复制到其中。
   同样地，在当前工作目录下创建 `pallas-bot` 目录，复制一份 `Pallas-Bot` 项目的 `.env.prod` 文件到其中。
   根据你的需要修改两份文件中的配置。

3. **一键启动！**

   ```bash
   docker compose up -d
   ```

   注意，首次启动时会自动下载 Docker 镜像、模型文件和语音文件，可能需要一些时间。

4. **查看服务状态**

   ```bash
   docker compose ps
   docker compose logs -f
   ```

### 服务管理

- **停止服务**: `docker compose down`
- **拉取最新镜像**: `docker compose pull`
- **重启服务**: `docker compose restart`
- **查看日志**: `docker compose logs -f [service_name]`
- **进入容器**: `docker compose exec [service_name] bash`

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
