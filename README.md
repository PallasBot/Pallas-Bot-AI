<div align="center">

<img alt="LOGO" src="https://github.com/user-attachments/assets/fe654813-bf37-4e5f-9c7d-98d867016618" width=427 height=276/>

# Pallas-Bot-AI

<br>

Pallas-Bot AI Backend，与 Pallas-Bot 本体解耦的 AI 功能服务端。

</div>

## 简介

使用 FastAPI + Celery(Redis) 提供 Pallas-Bot 所需的 AI 接口：LLM 闲聊、接话、唱歌、绘图等。LLM 任务异步执行，完成后通过 `/callback` 回推 Bot。

- 部署细节：[docs/Deployment.md](./docs/Deployment.md)
- 4.0 平台路线：[docs/architecture/platform-roadmap.md](./docs/architecture/platform-roadmap.md)

## 快速开始（LLM）

### 方式 A：一键脚本（推荐，本机开发）

```bash
cp .env.example .env
# 编辑 CALLBACK_HOST / CALLBACK_PORT 指向已运行的 Bot（默认 localhost:8088）
./scripts/ai_bootstrap.sh
```

仅体检：`./scripts/ai_bootstrap.sh --check-only`  
远端 API、不用 Ollama：`./scripts/ai_bootstrap.sh --remote-only`（完整步骤见 **[docs/deploy/remote-only.md](docs/deploy/remote-only.md)**）  
含唱歌/TTS：`./scripts/ai_bootstrap.sh --with-media`

### 方式 B：Docker（仅 AI + Redis + Ollama）

```bash
docker compose -f docker-compose.llm.yml up -d
curl -s http://127.0.0.1:9099/health | python3 -m json.tool
```

有 NVIDIA GPU：`docker compose -f docker-compose.llm.yml -f docker-compose.llm.gpu.yml up -d`

Ollama 长跑后 GPU 失效（推理变慢）：内置 guard（`LLM_OLLAMA_GPU_GUARD` + `OLLAMA_CONTAINER`）或 [`docs/operate/ollama-gpu-watchdog.md`](docs/operate/ollama-gpu-watchdog.md)

同机 Bot 未进 compose 时，默认 `CALLBACK_HOST=host.docker.internal`。

### 1. 复制配置（手动步骤）

```bash
cp .env.example .env
# 编辑 .env：Redis、CALLBACK_*、远端 API（若用 chain/remote）
```

### 2. 拉取 Ollama 模型

主对话模型与分类用小模型需分别拉取（宿主机已运行 `ollama serve` 时）：

```bash
ollama pull qwen2.5:7b      # 主对话（与 LLM_MODEL 一致）
ollama pull qwen2.5:0.5b    # 请求分类器（与 LLM_CATEGORIZER_MODEL 一致）
```

无 `ollama` 命令行时可用 HTTP：

```bash
curl -X POST http://127.0.0.1:11434/api/pull -d '{"name":"qwen2.5:7b"}'
curl -X POST http://127.0.0.1:11434/api/pull -d '{"name":"qwen2.5:0.5b"}'
```

### 3. 启动服务

```bash
uv sync --group dev
./scripts/ai_service.sh start
```

查看状态 / 停止服务：

```bash
./scripts/ai_service.sh status
./scripts/ai_service.sh stop
```

默认仅注册 **LLM** 任务（`CELERY_TASK_PACKAGES=llm`）。若需酒后 RWKV、唱歌、TTS，在 `.env` 设 `CELERY_TASK_PACKAGES=all` 并安装对应依赖：`uv sync --all-groups --extra gpu`。

Bot 侧须开启 `LLM_CHAT_ENABLED=true`，并配置 `AI_SERVER_HOST` / `AI_SERVER_PORT` 指向本服务。

### 4. 自检

```bash
curl -s http://127.0.0.1:9099/health | python3 -m json.tool
```

关注 `llm.provider_status`（各提供方可达性）、`llm.categorizer_model`、`llm.configuration_ok`。

WebUI **通用配置 → 智能对话与 AI 服务 → 模型与推理** 可查看提供方状态表（只读）。

---

## Provider 路由

支持 **本地 Ollama**、**远端 OpenAI 兼容 API**，以及按 task 分流。

### 仅用 `.env`（单本地 + 单远端）

| 变量 | 说明 |
| --- | --- |
| `LLM_PROVIDER_MODE` | `local_only` / `remote_only` / `chain` |
| `LLM_CHAIN_LOCAL_TASKS` | 走本地的 task，如 `llm_chat,drunk` |
| `LLM_CHAIN_REMOTE_TASKS` | 走远端的 task，如 `repeater_fallback,repeater_polish` |
| `LLM_REMOTE_*` | 远端 base_url、api_key、model |

**预设 A（常见）**：@ / 醉聊走本地，接话走远端。

```env
LLM_PROVIDER_MODE=chain
LLM_CHAIN_LOCAL_TASKS=llm_chat,drunk
LLM_CHAIN_REMOTE_TASKS=repeater_fallback,repeater_polish
```

### 多用 `providers.toml`（推荐：多远端 / 多本地）

```bash
cp config/providers.example.toml config/providers.toml
```

示例：第二个 Ollama 实例专门跑带 tools 的 @ 对话：

```toml
[[providers]]
id = "local"
kind = "local"
default_model = "qwen2.5:7b"

[[providers]]
id = "ollama-tools"
kind = "local"
base_url = "http://127.0.0.1:11435"
default_model = "qwen2.5:7b"

[routing.tasks]
llm_chat = "ollama-tools"
repeater_fallback = "local"
```

`.env` 指定文件路径（可选，默认 `config/providers.toml`）：

```env
LLM_PROVIDERS_FILE=config/providers.toml
```

`id = "local"` 且未写 `base_url` 时，回退 `LLM_BACKEND_URL`；其他本地 id **必须**写 `base_url`。

---

## 请求分类器（按需 tools）

开启后，每次 LLM 推理前用小模型判断是否需要 tool schema、难度档位（供 MoE 使用）。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_CATEGORIZER_ENABLED` | `true` | 总开关 |
| `LLM_CATEGORIZER_PROVIDER` | `local` | 注册表中的本地 provider id |
| `LLM_CATEGORIZER_MODEL` | — | 分类模型；未设时回退 `LLM_MOE_MODEL_SIMPLE` |
| `LLM_TOOLS_SELECTIVE` | `true` | 闲聊不带工具词时不注入 schema |

推荐配置：

```env
LLM_CATEGORIZER_MODEL=qwen2.5:0.5b
LLM_MOE_MODEL_SIMPLE=qwen2.5:0.5b
LLM_TOOLS_SELECTIVE=true
```

日志示例：`请求分类：tools=True tier=medium source=model`。小模型失败时自动回退关键词启发式。

Bot 可在 metadata 传 `tools_required: true/false` 强制覆盖。

**Bot 侧预筛**：主仓 `LLM_TOOLS_SELECTIVE=true` 时，仅在与方舟/命令相关的 domain 才附带 schema，减小 payload。

---

## 按难度选模型（MoE + categorizer）

配置 ≥2 档 `LLM_MOE_MODEL_*` 后，自动按 categorizer 的 `tier` 选模型（无需 `LLM_MOE_ENABLED=true`）：

```env
LLM_MOE_MODEL_SIMPLE=qwen2.5:0.5b
LLM_MOE_MODEL_MEDIUM=qwen2.5:7b
LLM_MOE_MODEL_COMPLEX=qwen3.5:9b
```

---

## WebUI 编辑提供方

控制台 **模型与推理** 面板可编辑 task 路由并保存到 `config/providers.toml`。

API：`GET/PUT /api/llm/providers`（Bot 代理：`/common-config/llm/providers`）。

---

## 健康检查

`GET /health` 返回 `llm` 字段，包含：

- `provider_mode` / `active_providers` / `task_routing`
- `provider_status[]`：每个提供方的 `id`、`kind`、`reachable`、`default_model`
- `categorizer_enabled` / `categorizer_model`
- `local_reachable` / `remote_reachable`（汇总）

---

## 项目结构

- `app/api` — HTTP 路由
- `app/providers` — LLM 路由、分类器、tool 循环
- `app/tasks` — Celery 任务
- `config/providers.example.toml` — 多提供方配置模板
- `docs` — 部署与架构文档
- `tests` — 单测

## 开发

```bash
uv run pytest
uv run ruff check app/
```

完整环境见 [docs/Deployment.md](./docs/Deployment.md)。
