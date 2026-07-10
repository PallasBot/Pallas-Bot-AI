# 部署指南

> 4.0 演进路线与验收见 [architecture/platform-roadmap.md](architecture/platform-roadmap.md)。

## 4.0 双仓最低版本

| 组件 | 最低要求 | 校验方式 |
| --- | --- | --- |
| **Pallas-Bot-AI** | `api_version` ≥ `4.0.0` | `GET /health` → `api_version` |
| **Pallas-Bot** | `feat/4.0-persona` 含 `features/llm` 统一客户端 | 启动日志 / integration 脚本 |
| **Redis** | 可达（Celery broker + 默认 LLM session） | AI 仓 `REDIS_URL`；compose 已含 redis 服务 |
| **LLM 后端** | `local_only` 需本地 HTTP 后端；或 `remote_only` | `/health.llm.provider_mode` |

联调最小 Redis：`docker compose -f docker-compose.4.0-ci.yml up -d`

本机一键安装（依赖 + Redis + Ollama + 启停）：`./scripts/ai_bootstrap.sh`（见根目录 [README](../README.md#快速开始llm)）。

**无 GPU / 纯第三方 API**：见 **[remote-only 部署指南](deploy/remote-only.md)**（`./scripts/ai_bootstrap.sh --remote-only` 或 Docker 仅起 `redis` + `pallasbot-ai`）。

仅 LLM 的 Docker 栈：`docker compose -f docker-compose.llm.yml up -d`

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

- 容器名：`pallas-ollama`；AI 服务通过 `LLM_BACKEND_URL=http://ollama:11434` 访问
- `pallasbot-ai` 环境变量 **`LLM_AUTO_START=false`**（由 compose 管 Ollama，AI 进程不再二次拉起）
- 首次启动时 `ollama-init` 会拉取模型（默认 `qwen2.5:7b`，可通过 **`LLM_MODEL`** 覆盖）
- Bot 侧配置 **`LLM_CHAT_ENABLED=true`**（见主仓 WebUI「LLM 与 AI 服务」）

本地推理环境变量见下文 [LLM 配置参考](#llm-配置参考)。运行时说明见 [runtime.md](architecture/runtime.md)。

GPU 长跑后 Ollama 可能回退 CPU（HTTP 仍 200、推理极慢）：见 [Ollama GPU 探活](operate/ollama-gpu-watchdog.md)（`scripts/ollama_gpu_watchdog.sh`）。

## LLM 配置参考

Bot 插件 **llm_chat** / **chat** / **repeater LLM** 依赖 AI 服务统一 Chat API；与「酒后聊天」legacy RWKV 路径相互独立。

### AI 服务环境变量（`.env`）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_CHAT_ENABLED` | `true` | 是否启用 LLM Chat API（遗留 `OLLAMA_ENABLE` 仍可读） |
| `LLM_BACKEND_URL` | `http://127.0.0.1:11434` | 本地推理后端根地址（遗留 `OLLAMA_URL`） |
| `LLM_MODEL` | `qwen2.5:7b` | 默认模型名（遗留 `OLLAMA_MODEL`） |
| `LLM_AUTO_START` | `false` | **`true`** 时，启动前若连不上后端则自动 `ollama serve`（Docker 全栈请 `false`） |
| `LLM_BACKEND_BINARY` | `ollama` | 自动拉起时的可执行文件（遗留 `OLLAMA_BINARY`） |
| `LLM_AUTO_PULL` | `true` | 自动拉起成功后是否 pull 当前模型 |
| `LLM_STARTUP_TIMEOUT` | `60` | 等待后端就绪的最长秒数 |
| `LLM_MAX_HISTORIES` | `100` | 会话轮数上限 |
| `LLM_TEMPERATURE` | `0.55` | 默认温度 |
| `LLM_NUM_GPU` | `12` | 传给后端的 num_gpu |
| `LLM_REQUEST_TIMEOUT` | `90` | 单次推理 HTTP 超时 |
| `LLM_DRUNK_TEMPERATURE` | `1.0` | drunk mode 温度 |

示例见仓库根目录 [`.env.example`](../.env.example)。

**多提供方路由、请求分类器、健康检查字段**见根目录 [README.md](../README.md#provider-路由)（`providers.toml`、`LLM_CATEGORIZER_*`、`GET /health`）。

### Ollama 配置参考（遗留标题，内容已合并至上一节）

<details>
<summary>旧 OLLAMA_* 键名对照</summary>

| 旧变量 | 新变量 |
| --- | --- |
| `OLLAMA_ENABLE` | `LLM_CHAT_ENABLED` |
| `OLLAMA_URL` | `LLM_BACKEND_URL` |
| `OLLAMA_MODEL` | `LLM_MODEL` |
| `OLLAMA_AUTO_START` | `LLM_AUTO_START` |

</details>

### 热更换模型（无需重启 Celery / FastAPI）

运行时模型写入 **`logs/llm_runtime.json`**（兼容读取旧 `logs/ollama_runtime.json`），API 与 Celery worker 共享。

```bash
# 查看当前模型（canonical）
curl http://127.0.0.1:9099/api/llm/model

# 切换并拉取（推荐）
curl -X PUT http://127.0.0.1:9099/api/llm/model \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:7b","pull":true}'

# 从 .env 的 LLM_MODEL 重新加载
curl -X POST http://127.0.0.1:9099/api/llm/model/reload
```

单次对话还可在 `POST /api/llm/chat/{request_id}` 请求体传可选字段 **`model`** 临时指定。

<details>
<summary>遗留路径（deprecated，兼容期保留）</summary>

`/api/ollama/*` 与上述 `/api/llm/*` 行为相同，新集成请使用 `/api/llm/*`。

</details>

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
    uv venv --python 3.12
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

    **启用 LLM 闲聊** 时，在 AI 服务 `.env` 中至少配置：

    ```env
    LLM_CHAT_ENABLED=true
    LLM_BACKEND_URL=http://127.0.0.1:11434
    LLM_MODEL=qwen2.5:7b
    LLM_AUTO_START=true
    ```

    本地推理后端有两种提供方式（二选一）：

    **A. 由 AI 服务自动拉起（推荐）**

    - 宿主机已安装 [Ollama](https://ollama.com/)，且 `ollama` 在 `PATH` 中
    - 设置 **`LLM_AUTO_START=true`**（见上）
    - 启动 Celery / FastAPI 时会检测 `LLM_BACKEND_URL`；不可达则后台执行 `ollama serve`，并在就绪后按 **`LLM_AUTO_PULL`** 拉取 **`LLM_MODEL`**

    **B. 自行常驻 Ollama 进程**

    - 另开终端或 systemd 运行：`ollama serve`
    - AI 服务 `.env` 设 **`LLM_AUTO_START=false`**，**`LLM_BACKEND_URL`** 指向实际地址
    - 首次使用前手动拉模型：`ollama pull qwen2.5:7b`

    Bot 侧在 WebUI **通用配置 → LLM 与 AI 服务** 或 **`config/pallas.toml` 的 `[env]`** 设置 **`LLM_CHAT_ENABLED=true`**；**`AI_SERVER_HOST` / `AI_SERVER_PORT`** 指向本 AI 服务。

    环境变量明细与热更换模型 API 见 [LLM 配置参考](#llm-配置参考)。

6. 启动 Celery Worker

    ```bash
    uv run celery -A app.core.celery worker --loglevel=info
    ```

    Worker 就绪时同样会执行本地 LLM 后端可达性检查；在 **`LLM_AUTO_START=true`** 时会尝试拉起本地服务。

7. 启动 FastAPI Server

    ```bash
    uv run python -m app.run_api
    ```

    开发热重载（仅监听 API 相关目录，不扫 `app/tasks` 下 TTS/sing 大目录）：

    ```bash
    UVICORN_RELOAD=true uv run python -m app.run_api
    ```

    若仅启 Ollama 而不启 chat / sing / tts，依赖安装可省略对应 `group`；Ollama 本身走 HTTP，**不占用** RWKV / 唱歌 / TTS 的 `resource/` 模型目录。

同样地，Windows 用户请勿关闭终端，Linux 用户推荐使用 [termux](https://termux.dev/) 或 [GNU Screen](https://zhuanlan.zhihu.com/p/405968623) 来保持服务在后台运行。
