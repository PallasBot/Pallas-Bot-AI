# 纯远端 API 部署（remote-only）

> 适用场景：服务器**没有 GPU / 跑不动 Ollama**，但仍想用 @ 闲聊、接话 LLM 等智能对话能力。  
> 对应需求：[Pallas-Bot #220](https://github.com/PallasBot/Pallas-Bot/issues/220)。

## 结论先说

| 项目 | 说明 |
| --- | --- |
| **需要** | 轻量 **Pallas-Bot-AI**（Redis + FastAPI + Celery），**不需要** Ollama / GPU / 本地模型 / **torch** |
| **需要** | 第三方 **OpenAI 兼容 API**（DeepSeek、OpenAI、硅基流动等）及 API Key |
| **不需要** | Bot 直连第三方；API Key 只配置在 **AI 仓** `.env` 或 `providers.toml` |
| **不在 scope** | 唱歌、醉聊 RWKV、本地 TTS（需 `--with-media` + 本地模型与媒体 worker） |

架构边界见 [Pallas AI 终态架构](https://github.com/PallasBot/Pallas-Bot/blob/dev/docs/architecture/internal/pallas-final-ai-shape.md)：Bot 负责触发与 callback，AI 仓负责 provider 路由、队列与异步回推。

---

## 前置条件

1. **Pallas-Bot** 已能正常收发消息（记下 Bot HTTP 端口，默认 `8088`）。
2. **Redis** 可达（Celery broker + LLM 会话存储）。
3. 已申请 **OpenAI 兼容 API** 的 `base_url`、API Key、模型名。
4. 机器资源：纯 LLM 网关通常 **1～2 GB 内存** 即可；无 GPU 要求。

---

## 方式 A：一键脚本（本机，推荐）

在 **Pallas-Bot-AI** 仓库：

```bash
cp .env.example .env
# 编辑 .env：填入 LLM_REMOTE_*（见下文「最小 .env」）
./scripts/ai_bootstrap.sh --remote-only --bot-host 127.0.0.1 --bot-port 8088
```

或在 **Pallas-Bot** 仓库（同级已克隆 AI 仓时）：

```bash
uv run pallas ai setup --remote-only --bot-port 8088
```

脚本会：

- 设置 `LLM_PROVIDER_MODE=remote_only`、`LLM_AUTO_START=false`
- **跳过** Ollama 检测与模型拉取
- 安装 **LLM-only** 依赖（`uv sync --group dev`，不装 torch）、尝试拉起 Redis、启动 LLM worker 与 API
- 唱歌/TTS 仍需另行 `--with-media`（与 remote-only 可叠加：`./scripts/ai_bootstrap.sh --remote-only --with-media`）

仅体检、不启动：`./scripts/ai_bootstrap.sh --remote-only --check-only`

---

## 方式 B：Docker（仅 Redis + AI，无 Ollama 容器）

```bash
cp .env.example .env
# 编辑 .env 填入远端 API（见下节）
docker compose -f docker-compose.llm.yml up -d redis pallasbot-ai
```

`docker-compose.llm.yml` 默认 `AI_ENABLE_MEDIA_WORKER=0`（不启唱歌/TTS worker）。需要媒体时设 `AI_ENABLE_MEDIA_WORKER=1`。

**不要**启动 `ollama` / `ollama-init` 服务。`docker-compose.llm.yml` 已支持 `pallasbot-ai` 在无 Ollama 时单独运行（`depends_on.ollama.required: false`）。

同机 Bot 未进 compose 时，默认 `CALLBACK_HOST=host.docker.internal`；Bot 在其它机器上时改为 Bot 可达 IP。

启动后在 `.env` 或 compose 环境变量中至少设置：

```env
LLM_PROVIDER_MODE=remote_only
LLM_REMOTE_BASE_URL=https://api.deepseek.com
LLM_REMOTE_API_KEY=sk-...
LLM_REMOTE_MODEL=deepseek-chat
LLM_CATEGORIZER_ENABLED=false
GPU_LOCK_LLM_ENABLED=false
CELERY_TASK_PACKAGES=llm
```

---

## 方式 C：手动步骤

### 1. Redis

```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### 2. 依赖（无需 gpu extra）

```bash
uv venv --python 3.12
uv sync --group dev
```

### 3. 最小 `.env`

```env
REDIS_URL=redis://127.0.0.1:6379/0
LLM_SESSION_BACKEND=redis
CELERY_TASK_PACKAGES=llm

CALLBACK_HOST=127.0.0.1
CALLBACK_PORT=8088

LLM_CHAT_ENABLED=true
LLM_PROVIDER_MODE=remote_only
LLM_AUTO_START=false

LLM_REMOTE_BASE_URL=https://api.deepseek.com
LLM_REMOTE_API_KEY=sk-xxxxxxxx
LLM_REMOTE_MODEL=deepseek-chat

# remote_only 下无本地 categorizer 模型，建议关闭或改 remote
LLM_CATEGORIZER_ENABLED=false
GPU_LOCK_LLM_ENABLED=false
```

### 4. 启动

```bash
./scripts/ai_service.sh start
# 或
./scripts/ctl.sh start llm
```

---

## 多 Provider 与按 task 路由（可选）

复制 [`config/providers.example.toml`](../../config/providers.example.toml) 为 `config/providers.toml`，在 `.env` 设：

```env
LLM_PROVIDERS_FILE=config/providers.toml
```

示例：主对话走 DeepSeek，接话走同一远端模型：

```toml
[[providers]]
id = "deepseek"
kind = "remote"
base_url = "https://api.deepseek.com"
api_key_env = "LLM_REMOTE_API_KEY"
default_model = "deepseek-chat"
enabled = true

[routing.tasks]
llm_chat = "deepseek"
repeater_fallback = "deepseek"
repeater_select = "deepseek"
repeater_polish = "deepseek"
```

API Key 仍通过环境变量注入（`api_key_env`），**不要**把密钥写进 toml 入库。

WebUI **通用配置 → 模型与 Provider** 可编辑上述配置（Bot 代理 AI 仓 API）。

---

## Bot 侧配置

`config/pallas.toml` 的 `[env]` 或 WebUI **智能对话与 AI 服务**：

| 键 | 说明 |
| --- | --- |
| `LLM_CHAT_ENABLED` | `true` |
| `AI_SERVER_HOST` | AI 服务地址（本机 `127.0.0.1`） |
| `AI_SERVER_PORT` | 默认 `9099` |

Bot **不**配置 `LLM_REMOTE_*` / `OPENAI_API_KEY`；密钥仅落在 AI 仓。

---

## 画图（可选）

若还需文生图且不想跑本地模型：

**经 AI 仓**（draw 默认 `ai_service_runtime`）：

```env
IMAGE_ENABLED=true
IMAGE_BASE_URL=https://api.openai.com
IMAGE_API_KEY=sk-...
IMAGE_MODEL=gpt-image-1
```

**Draw 插件直连**（不经 AI 仓）：WebUI **外部服务地址与连通检测** → 画画 → `plugin_runtime` + `pallas_image_base_url` / `pallas_image_api_key`。

---

## 验收

### 1. AI 健康检查

```bash
curl -s http://127.0.0.1:9099/health | python3 -m json.tool
```

期望：

- `llm.provider_mode` 为 `remote_only`
- `llm.configured` 为 `true`
- 远端 provider 探测 `reachable: true`（若配置了 probe）

### 2. Provider 连通（可选）

```bash
curl -s -X POST http://127.0.0.1:9099/api/llm/providers/deepseek/test
```

（provider id 与 `providers.toml` 一致）

### 3. Bot / WebUI

- `/pallas/api/common-config/llm/wizard/status` → AI 服务就绪
- `/pallas/api/common-config/llm/runtime-overview` → provider 为 remote
- 群内 **@ 牛** 发一句闲聊，应异步收到回复

### 4. 一键体检

```bash
./scripts/ai_bootstrap.sh --remote-only --check-only
```

---

## 能力范围

| 能力 | remote-only |
| --- | --- |
| @ 闲聊 / 私聊 LLM | ✅ |
| 接话（repeater LLM） | ✅ |
| 方舟 tools | ✅（依赖远端模型支持 function calling） |
| 文生图（第三方图像 API） | ✅（需额外配置 `IMAGE_*` 或 draw 直连） |
| 唱歌 / TTS | ❌ 需 `--with-media` + 本地模型 |
| 醉聊 RWKV（ai-media） | ❌ 需本地 ChatRWKV |
| Embedding / 向量 RAG | ⚠️ AI 仓为 stub，质量有限 |

---

## 常见问题

### `provider_mode` 仍是 `local_only`

确认 `.env` 中 `LLM_PROVIDER_MODE=remote_only` 且已重启 Celery / API。`ai_bootstrap.sh --remote-only` 会自动写入。

### `LLM_REMOTE_*` 未配置 / health 报 configured false

`remote_only` 下必须同时配置 `LLM_REMOTE_BASE_URL`、`LLM_REMOTE_API_KEY`、`LLM_REMOTE_MODEL`（或通过 `providers.toml` + 对应 `api_key_env`）。

### @ 牛无回复，但 health 正常

1. Bot 侧 `LLM_CHAT_ENABLED` 是否为 `true`
2. `CALLBACK_HOST` / `CALLBACK_PORT` 是否指向** Bot 可达**的地址（Docker 内常用 `host.docker.internal`）
3. 查看 AI 仓日志：`logs/` 或 `docker compose logs pallasbot-ai`
4. Bot 是否收到 callback：查 Bot 日志中 `llm` / `callback` 相关条目

### categorizer 报错或拖慢首包

`remote_only` 且无本地 Ollama 时，设 `LLM_CATEGORIZER_ENABLED=false`（回退启发式路由），或把 categorizer 也配成远端 provider。

### 能否完全不要 Pallas-Bot-AI？

当前架构**不支持** Bot 直连第三方 API。AI 仓承担队列、session、tool loop、熔断与 callback；去掉它需要重构双仓契约，不在 remote-only 文档 scope 内。

---

## 相关阅读

- [部署指南](../Deployment.md)（全量 Docker / 手动 / Ollama）
- [Provider 路由（README）](../../README.md#provider-路由)
- [Bot 侧 AI Runtime 安装](https://github.com/PallasBot/Pallas-Bot/blob/dev/docs/maintainer/install/ai-runtime.md)
- [LLM 与 AI 运维](https://github.com/PallasBot/Pallas-Bot/blob/dev/docs/maintainer/operate/llm-and-ai.md)
