# 部署指南

文档总索引：[README.md](README.md)。快速入口见仓库根 [README.md](../README.md)。

本仓提供唱歌 / TTS 等媒体任务，以及可选遗留酒后 RWKV。普通 `@` 聊天在 Bot 内核配置 Provider，不依赖本服务。

## 双仓最低版本

| 组件 | 最低要求 | 校验方式 |
| --- | --- | --- |
| **Pallas-Bot-AI** | `api_version` ≥ `4.0.0` | `GET /health` → `api_version` |
| **Pallas-Bot** | 支持 `AI_SERVER_*` 的 V4 线 | 启动日志 / WebUI 媒体服务 |
| **Redis** | 可达（Celery broker） | AI 仓 `REDIS_URL`；compose 已含 redis |

本机一键：`./scripts/ai_bootstrap.sh`（默认装媒体栈并启动 media worker + API）。

**Windows 本机**：需 [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) 已安装且引擎在跑（bootstrap 用其拉 Redis）；也可用 WSL/本机 Redis，在 `.env` 写 `REDIS_URL`。引擎未开时日志会提示，勿依赖 WSL Containers 公测替代 Compose。

## 方式一：Docker

### 前置

- [Docker Compose](https://github.com/PallasBot/Pallas-Bot/blob/main/docs/deploy/docker.md)；Windows 用 Docker Desktop
- GPU 镜像需宿主机 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

### 快速部署

1. 复制本仓根目录 `docker-compose.yml` 到工作目录（也可整仓克隆）。
2. （可选）准备 `pallas-bot-ai/.env`（自本仓 `.env.example`）与 Bot 侧配置。
3. 启动：

```bash
docker compose up -d
```

首次可能下载镜像与模型，耗时较长。

4. 状态与日志：

```bash
docker compose ps
tail -f ./pallas-bot-ai/logs/uvicorn.log
tail -f ./pallas-bot-ai/logs/celery-media.log
```

与 Bot 全栈 compose 联用时，Bot 可将该日志目录只读挂到 `/ai-logs`，供 WebUI「AI 观测」跟读。

Bot 与本栈不同网络时：`AI_SERVER_HOST=pallasbot-ai`，本侧 `CALLBACK_HOST` 用 Bot 容器名。示例：`deploy/docker-compose.bot-join-ai.example.yml`。

## 方式二：本机手动部署

### 前置

- `uv`（推荐经 `pipx install uv`）
- Redis（例如 `docker run -d --name redis -p 6379:6379 redis`）

### 步骤

1. 依赖（媒体栈，含 torch）：

```bash
uv sync --all-groups --extra cpu   # 或 --extra gpu
git submodule update --init --recursive
```

按需收窄 group：`sing` / `tts` / `chat`（遗留 RWKV）。

2. 模型放到 `resource/` 下对应目录（`sing` / `tts` / `chat`），可从 [Hugging Face pallasbot](https://huggingface.co/pallasbot/Pallas-Bot/tree/main) 获取。

3. 配置 `.env`：至少 `CALLBACK_HOST` / `CALLBACK_PORT` 指向 Bot；建议设置 `PALLAS_AI_API_TOKEN`（与 Bot / 插件 Bearer 一致）。

4. 启动：

```bash
./scripts/ctl.sh start media
./scripts/ctl.sh start api
# 或
./scripts/ai_bootstrap.sh
```

开发热重载（不扫 workers 下大目录）：

```bash
UVICORN_RELOAD=true uv run python -m app.run_api
```

## API Bearer Token

Bot WebUI「媒体服务」里的 **Bearer Token** 须与 AI 侧 **`PALLAS_AI_API_TOKEN`** 一致。

- 非空时：`GET /api/ops/logs` 及推荐的 **`/v1/*`** 要求 `Authorization: Bearer <token>`
- 留空：不对 Bearer 校验（仅建议本机调试）

```bash
curl -H "Authorization: Bearer 你的token" "http://127.0.0.1:9099/api/ops/logs?kind=uvicorn&n=5"
curl -s http://127.0.0.1:9099/health | python3 -m json.tool
```

对外推荐 **`/v1`**；`/api` 为兼容入口。运行时边界见 [architecture/runtime.md](architecture/runtime.md)。
