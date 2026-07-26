# AI 仓平台化说明

> 部署步骤见 [Deployment.md](../Deployment.md)；运行时见 [runtime.md](runtime.md)。

本仓负责媒体推理与可选遗留 RWKV；Bot 内核负责通用 LLM 闲聊、工具循环与会话。

## 定位

| 做 | 不做 |
| --- | --- |
| 唱歌 / TTS / 图像等媒体任务 | 群风格统计、repeater 触发逻辑 |
| Celery 异步 + `/callback` | Bot ingress / 分片 claim |
| 可选酒后 RWKV | 通用 LLM Chat API / Agent 工具循环 |
| GPU 进程与媒体健康探测 | 主仓 WebUI 业务开关（如 `LLM_CHAT_ENABLED`） |

## 必须保持

| 能力 | API | 说明 |
| --- | --- | --- |
| 酒后 RWKV | `POST /api/chat/{id}` | 低配置用户可不用外部 LLM Provider |
| 唱歌 / TTS | `/api/sing/*`、`/api/tts/*` | 发版前 smoke |
| 媒体健康 | `GET /health` | 聚合媒体能力快照 |

## 已迁出（勿再按本仓实现）

以下能力已在 Bot 内核交付，本仓文档中的旧「LLM 网关 / Celery llm_chat / session Redis」描述作废：

- 统一 Chat Completions
- Provider 链与模型管理（Bot 侧）
- 工具 schema 与执行环
- 会话摘要与记忆注入

## 原则

1. **少折腾**：可继续走 RWKV `/api/chat`，不必装完整媒体栈。
2. **要 LLM 闲聊**：在 Bot 配置 Provider 与 `LLM_CHAT_ENABLED`；与本仓媒体互不影响。
3. **回归**：改媒体链路时至少确认 sing / TTS / RWKV 未断。
