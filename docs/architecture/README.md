# 架构文档

面向扩展与联调开发者。部署与 env 见 [Deployment.md](../Deployment.md)；文档总索引见 [docs/README.md](../README.md)。

| 文档 | 说明 |
| --- | --- |
| [runtime.md](runtime.md) | uvicorn + Celery 媒体运行时；与 Bot 的边界 |

跨仓职责：Bot 管普通 LLM 闲聊、业务路由与开关；本仓管媒体推理、队列、健康、callback，以及可选遗留 RWKV。Bot 通过 `AI_SERVER_*` 连接本服务 `:9099`。
