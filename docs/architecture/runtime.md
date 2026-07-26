# AI 服务运行时架构

## 定位

本仓是 Pallas-Bot 的**可选媒体后端**：唱歌、TTS、图像等异步任务，以及可选的遗留酒后 RWKV。  
**通用 LLM 闲聊与工具循环在 Bot 内核**（`pallas/product/llm`），不经本仓 Chat API。

## 为何 uvicorn + Celery

| 组件 | 职责 |
| --- | --- |
| **uvicorn (FastAPI)** | 健康检查、短同步 API、立即返回 `task_id` |
| **Redis** | Celery broker / result backend |
| **Celery worker** | 长耗时媒体推理 + **callback Bot** |

## 媒体与遗留聊天

| 能力 | 典型 API | 说明 |
| --- | --- | --- |
| 唱歌 / TTS | `/api/sing/*`、`/api/tts/*` | 主路径媒体任务 |
| 图像 / media | `/api/images`、`/api/media/*` | 按启用端点返回 |
| 酒后 RWKV | `POST /api/chat/{id}` | 可选遗留路径；与 Bot 内核 Provider 聊天无关 |

任务完成后经 `/callback` 回推 Bot。

## 与 Bot 的边界

- Bot 配置 `AI_SERVER_HOST` / `AI_SERVER_PORT`（或 WebUI「媒体服务」）仅用于媒体与可选 RWKV。
- `@` 闲聊、接话辅助、工具调用由 Bot 内核 Provider 完成；`:9099` 不可达不影响默认聊天。
