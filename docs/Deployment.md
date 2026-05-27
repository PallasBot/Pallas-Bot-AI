# 部署指南

## 方式一：使用 Docker 部署

本项目的 `docker-compose.yml` 提供了全栈服务一键部署。

### 前置条件

- **Docker 和 Docker Compose**
  
  请确保已[安装 Docker 和 Docker Compose](https://github.com/PallasBot/Pallas-Bot/blob/main/docs/DockerDeployment.md#%E5%AE%89%E8%A3%85-docker-%E4%B8%8E-docker-compose)。

- **NVIDIA Docker 支持（GPU 版本）**
  
  请确保已在宿主机上[安装 container toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)（Windows 用户请使用 WSL2 环境安装 `container toolkit`）。

### 快速部署

1. **复制 `docker-compose.yml` 文件**

   无需克隆本项目，只需将本项目根目录下的 `docker-compose.yml` 文件复制到你的工作目录。

2. （可选）**配置环境变量**

   在当前工作目录下创建 `pallas-bot-ai` 目录并将项目根目录下的 `.env` 文件复制到其中。
   同样地，在当前工作目录下创建 `pallas-bot` 目录，复制一份 `Pallas-Bot` 项目的 `.env` 文件到其中。
   根据你的需要修改两份文件中的配置。

3. **一键启动！**

   ```bash
   docker compose up -d
   ```

   注意，首次启动时会自动下载 Docker 镜像、模型文件和语音文件，可能需要一些时间（15-20分钟）。

4. **查看服务状态**

   ```bash
   docker compose ps
   docker compose logs -f
   ```

   首次启动时，可以通过 `docker compose logs -f pallasbot-ai` 查看 AI 服务端的日志，确认当前下载进度。

### 服务管理

- **停止服务**: `docker compose down`
- **拉取最新镜像**: `docker compose pull`
- **重启服务**: `docker compose restart`
- **查看日志**: `docker compose logs -f [service_name]`
- **进入容器**: `docker compose exec [service_name] bash`

### Ollama（Docker）

全栈 `docker-compose.yml` 已包含 **Ollama** 容器，与 `pallasbot-ai` 同网段启动：

- 容器名：`pallas-ollama`；AI 服务通过 `OLLAMA_URL=http://ollama:11434` 访问
- `pallasbot-ai` 环境变量 **`OLLAMA_AUTO_START=false`**（由 compose 管 Ollama，AI 进程不再二次拉起）
- 首次启动时 `ollama-init` 会拉取模型（默认 `qwen2.5:7b`，可通过 **`OLLAMA_MODEL`** 覆盖）
- Bot 侧在 WebUI **插件 → ollama** 或 **`config/pallas.toml` 的 `[env]`** 设置 **`OLLAMA_ENABLE=true`** 后启用

Ollama 环境变量、热更换模型等共用说明见下文 [Ollama 配置参考](#ollama-配置参考)。

## Ollama 配置参考

Bot 插件 **牛牛聊天**（`ollama`）依赖 AI 服务的 Ollama HTTP 接口；与「酒后聊天」（RWKV）相互独立。

### AI 服务环境变量（`.env`）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `OLLAMA_ENABLE` | `true` | 是否注册 Ollama 相关 API |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama 根地址（Docker 全栈填 `http://ollama:11434`） |
| `OLLAMA_MODEL` | `qwen2.5:7b` | 默认模型名；亦可通过运行时 API 覆盖 |
| `OLLAMA_AUTO_START` | `false` | **`true`** 时，FastAPI / Celery 启动前若连不上 `OLLAMA_URL` 则自动 `ollama serve`（**手动部署推荐**；Docker 全栈请保持 `false`） |
| `OLLAMA_BINARY` | `ollama` | 自动拉起时使用的可执行文件 |
| `OLLAMA_AUTO_PULL` | `true` | 自动拉起成功后是否 `pull` 当前模型 |
| `OLLAMA_STARTUP_TIMEOUT` | `60` | 等待 Ollama 就绪的最长秒数 |

### 热更换模型（无需重启 Celery / FastAPI）

运行时模型写入 **`logs/ollama_runtime.json`**，API 与 Celery worker 共享。

```bash
# 查看当前模型
curl http://127.0.0.1:9099/api/ollama/model

# 切换并拉取（推荐）
curl -X PUT http://127.0.0.1:9099/api/ollama/model \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:7b","pull":true}'

# 从 .env 的 OLLAMA_MODEL 重新加载
curl -X POST http://127.0.0.1:9099/api/ollama/model/reload
```

单次对话还可在 `POST /api/ollama/chat/{request_id}` 请求体传可选字段 **`model`** 临时指定。

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

当然其他方式部署 Redis 也是可以的。

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

    从 [huggingface](https://huggingface.co/pallasbot/Pallas-Bot/tree/main) 为你启用的 AI 功能下载模型，解压并放到 `resource` 的对应目录下。
    目录结构如下：

    ```
    resource
    ├─chat
    │  └─models
    ├─sing
    │  └─models
    │     ├─pallas
    │     └─pretrain
    │         ├─contentvec
    │         ├─nsf_hifigan
    │         ├─pc_nsf_hifigan_44.1k_hop512_128bin_2025.02
    │         └─rmvpe
    └─tts
        ├─configs
        ├─G2PWModel
        ├─ja_userdic
        ├─pallas
        ├─pretrained_models
        │  ├─chinese-hubert-base
        │  ├─chinese-roberta-wwm-ext-large
        │  ├─fast_langdetect
        │  └─gsv-v4-pretrained
        └─ref_audio
    ```

5. 配置环境变量

    请结合注释，根据实际情况修改 `.env` 文件中的配置。保持注释即使用默认值。

    **启用牛牛聊天（Ollama）** 时，在 AI 服务 `.env` 中至少配置：

    ```env
    OLLAMA_ENABLE=true
    OLLAMA_URL=http://127.0.0.1:11434
    OLLAMA_MODEL=qwen2.5:7b
    OLLAMA_AUTO_START=true
    ```

    Ollama 有两种提供方式（二选一）：

    **A. 由 AI 服务自动拉起（推荐）**

    - 宿主机已安装 [Ollama](https://ollama.com/)，且 `ollama` 在 `PATH` 中
    - 设置 **`OLLAMA_AUTO_START=true`**（见上）
    - 启动 Celery / FastAPI 时会检测 `OLLAMA_URL`；不可达则后台执行 `ollama serve`，并在就绪后按 **`OLLAMA_AUTO_PULL`** 拉取 **`OLLAMA_MODEL`**

    **B. 自行常驻 Ollama 进程**

    - 另开终端或 systemd 运行：`ollama serve`
    - AI 服务 `.env` 设 **`OLLAMA_AUTO_START=false`**，**`OLLAMA_URL`** 指向实际地址
    - 首次使用前手动拉模型：`ollama pull qwen2.5:7b`

    Bot 侧在 WebUI **插件 → ollama** 或 **`config/pallas.toml` 的 `[env]`** 设置 **`OLLAMA_ENABLE=true`**；**`AI_SERVER_HOST` / `AI_SERVER_PORT`** 指向本 AI 服务（可与 sing/chat 共用，通常已在 WebUI 配置）。

    环境变量明细与热更换模型 API 见 [Ollama 配置参考](#ollama-配置参考)。

6. 启动 Celery Worker

    ```bash
    uv run celery -A app.core.celery worker --loglevel=info
    ```

    Worker 就绪时同样会执行 Ollama 可达性检查；在 **`OLLAMA_AUTO_START=true`** 时会尝试拉起本地服务。

7. 启动 FastAPI Server

    ```bash
    uv run uvicorn app.main:app --reload --port 9099
    ```

    若仅启 Ollama 而不启 chat / sing / tts，依赖安装可省略对应 `group`；Ollama 本身走 HTTP，**不占用** RWKV / 唱歌 / TTS 的 `resource/` 模型目录。

同样地，Windows 用户请勿关闭终端，Linux 用户推荐使用 [termux](https://termux.dev/) 或 [GNU Screen](https://zhuanlan.zhihu.com/p/405968623) 来保持服务在后台运行。
