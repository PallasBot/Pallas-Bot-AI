<div align="center">

<img alt="LOGO" src="https://github.com/user-attachments/assets/fe654813-bf37-4e5f-9c7d-98d867016618" width=427 height=276/>

# Pallas-Bot-AI

<br>

Pallas-Bot 的可选媒体后端（与本体解耦）：唱歌、TTS 等。聊天由 Bot 内核直连 Provider。

</div>

## 简介

使用 FastAPI + Celery(Redis) 为 [Pallas-Bot](https://github.com/PallasBot/Pallas-Bot) 提供**媒体**能力（唱歌 / TTS 等）。任务异步执行，完成后通过 `/callback` 回推 Bot。

Bot 侧请安装官方扩展 [`pallas-plugin-ai-media`](https://github.com/PallasBot/Plugin-Ai-Media)（`牛牛唱歌` / `牛牛说`），并配置 `AI_SERVER_HOST` / `AI_SERVER_PORT`（或控制台媒体服务地址）。

默认启动 **media worker + API**（`./scripts/ctl.sh start` 或 `./scripts/ai_bootstrap.sh`）。

- 文档索引：[docs/README.md](./docs/README.md)
- 部署细节：[docs/Deployment.md](./docs/Deployment.md)
- V4 平台路线：[docs/architecture/platform-roadmap.md](./docs/architecture/platform-roadmap.md)

## 快速开始（媒体服务）

### 方式 A：一键脚本（推荐，本机开发）

```bash
cp .env.example .env
# 编辑 CALLBACK_HOST / CALLBACK_PORT 指向已运行的 Bot（默认 localhost:8088）
# 建议设置 PALLAS_AI_API_TOKEN，与 Bot / 插件 Bearer 一致
./scripts/ai_bootstrap.sh
```

默认安装 **媒体栈**（`uv sync --all-groups --extra cpu`，含 torch），并启动 media worker + API。

| 场景 | 命令 |
| --- | --- |
| 仅体检 | `./scripts/ai_bootstrap.sh --check-only` |
| 只装不启动 | `./scripts/ai_bootstrap.sh --no-start` |
| 媒体 + NVIDIA GPU torch | `PALLAS_GPU=1 ./scripts/ai_bootstrap.sh` |

### 方式 B：Docker

```bash
docker compose up -d redis
# 或完整栈见 docker-compose.yml
curl -s http://127.0.0.1:9099/health | python3 -m json.tool
```

全功能 GPU 镜像：`docker build -t pallasbot/pallas-bot-ai:latest .`

Bot 也在 Docker、且与本栈**不同网络**时：让 Bot 挂入固定网络，`AI_SERVER_HOST=pallasbot-ai`，本侧 `CALLBACK_HOST` 用 Bot 容器名。示例：[deploy/docker-compose.bot-join-ai.example.yml](deploy/docker-compose.bot-join-ai.example.yml)。

### 手动启动

```bash
cp .env.example .env
uv sync --all-groups --extra cpu   # 或 --extra gpu
./scripts/ctl.sh start media
./scripts/ctl.sh start api
```

```bash
./scripts/ctl.sh status
./scripts/ctl.sh stop all
```

### 自检与 API

```bash
curl -s http://127.0.0.1:9099/health | python3 -m json.tool
```

关注 `media_tasks`、`tts` 等字段（按已启用端点返回）。`health` 中会提示推荐前缀 `/v1`。

对外推荐 **`/v1`**（配置了 `PALLAS_AI_API_TOKEN` 时须带 Bearer）；`/api` 为兼容入口（deprecated）。

```bash
# 示例：提交 TTS（request_id 由调用方生成，完成后走 Bot /callback）
curl -s -X POST "http://127.0.0.1:9099/v1/tts/${REQUEST_ID}" \
  -H "Authorization: Bearer ${PALLAS_AI_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"text":"你好"}'
```

---

## 项目结构

- `app/http` — FastAPI 路由（`/api` 兼容、`/v1` 推荐）
- `app/media` — 媒体门面、运行时、SVC 注册表与本地服务
- `app/workers` — Celery 媒体任务（`sing` / `tts` / 遗留酒后 `chat` RWKV）
- `docs` — 部署与架构文档
- `tests` — 单测

## 相关仓库

| 仓库 | 说明 |
| --- | --- |
| [Pallas-Bot](https://github.com/PallasBot/Pallas-Bot) | Bot 本体（通过 `AI_SERVER_*` 连接本服务） |
| [Plugin-Ai-Media](https://github.com/PallasBot/Plugin-Ai-Media) | 官方扩展：牛牛唱歌 / 牛牛说 |
| [Pallas-Bot-WebUI](https://github.com/PallasBot/Pallas-Bot-WebUI) | 控制台前端 |
| [Pallas-Bot-Docs](https://github.com/PallasBot/Pallas-Bot-Docs) | 文档站 |
| [Pallas-Bot-Community-Stats](https://github.com/PallasBot/Pallas-Bot-Community-Stats) | 社区统计与语料中心 |

## 开发

```bash
uv run pytest
uv run ruff check app/ tests/
```

完整环境见 [docs/Deployment.md](./docs/Deployment.md)。
