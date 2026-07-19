# AI 服务运行时架构

## 为何 uvicorn + Celery

| 组件 | 职责 |
| --- | --- |
| **uvicorn (FastAPI)** | 健康检查、短同步 API（模型管理、unload、affect-refine）、立即返回 `task_id` |
| **Redis** | Celery broker / result backend；**LLM 会话默认也走 Redis**（`REDIS_URL`） |
| **Celery worker** | 长耗时推理（LLM 闲聊、sing、TTS）+ **callback Bot**；默认 `threads` 池、`CELERY_WORKER_CONCURRENCY=6` |

**不建议去掉 Celery**：sing / TTS 与 GPU 锁依赖 worker 线程池排队；LLM 单次可达 90s，若全塞进 uvicorn 会阻塞 health 与其余 API。

## 双栈：LLM 与 legacy 媒体

| 栈 | 任务 | 典型 API | 用户场景 |
| --- | --- | --- | --- |
| **LLM** | `llm_chat` | `/api/v1/chat/completions` | 开 `LLM_CHAT_ENABLED`、有 Ollama/远端 |
| **Legacy** | `chat_task`（RWKV）、sing、tts | `/api/chat`、`/api/sing/*`、`/api/tts/*` | 不折腾 Ollama；**4.0 升级须保持可用** |

两栈共用 Celery + Redis + `/callback`，队列与 GPU 锁逻辑互不替换。

## LLM 闲聊路径

```
Bot POST /api/v1/chat/completions/{id}
  → uvicorn 解析 metadata（mode / task / temperature / token_count）
  → 入队 Celery task `llm_chat`
  → worker provider chain（local / remote OpenAI 兼容）
  → POST Bot /callback/{id}
```

清会话 `DELETE /api/v1/chat/completions/session/{id}` 通过 **`llm_del_session` Celery 任务** 在 worker 进程清会话。

会话存储：默认 **`LLM_SESSION_BACKEND=redis`**（与 Celery 共用 `REDIS_URL`）。`memory` 仅适合无 Redis 的单进程本地调试。

## Provider 模式

| `LLM_PROVIDER_MODE` | 行为 |
| --- | --- |
| `local_only` | 仅本地后端（`LLM_BACKEND_URL`，当前多为 Ollama `/api/chat`） |
| `remote_only` | 仅 OpenAI 兼容 HTTPS；启动时不拉起本地后端 |
| `chain` | 按 `LLM_CHAIN_ORDER` 顺序尝试；失败时 `try_next` 切换下一 provider |

Bot 仍只连 `:9099`；密钥与远端 base_url 仅在 AI 仓配置。

## metadata.task（Bot 下发）

| task | 典型场景 |
| --- | --- |
| `llm_chat` | 随时 @ |
| `drunk` | 酒后聊天 |
| `repeater_fallback` | 语料 miss 生成 |
| `repeater_polish_lite` | 语料 hit 偶尔轻顺口气（select_polish_lite） |
| `repeater_select` | 语料 hit 情绪选句（推荐） |
| `repeater_polish` | 语料 hit 轻改写（遗留） |
| `affect_refine` | 群风格批次 refine |

`repeater_select` / `repeater_polish_lite` / `repeater_polish` / `repeater_fallback` / `drunk` 属于 `_NO_TOOL_TASKS`：**跳过 categorizer**，固定 `tier=simple`、不注入 tools。`repeater_select` 推荐绑定与 `LLM_CATEGORIZER_MODEL` / `LLM_MOE_MODEL_SIMPLE` 同档小模型；**不要**为选句再调用 categorizer（避免双次推理）。

可通过 `LLM_TASK_MODEL_*` / `providers.toml` `[routing.tasks]` 为各 task 指定模型；`LLM_MOE_ENABLED=true` 时未指定 task 模型则按 tier 选 MoE 模型。

## 后续

见 [platform-roadmap.md](platform-roadmap.md)。
