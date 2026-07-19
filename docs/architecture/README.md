# 架构文档

面向扩展与联调开发者。部署与 env 见 [Deployment.md](../Deployment.md)；文档总索引见 [docs/README.md](../README.md)。

| 文档 | 说明 |
| --- | --- |
| [runtime.md](runtime.md) | uvicorn + Celery + LLM / media 运行时 |
| [platform-roadmap.md](platform-roadmap.md) | **V4+** 定位、兼容策略与能力基线 |
| [persona-affect-refine.md](persona-affect-refine.md) | 群风格 affect-refine API（已落地） |
| [local-models.md](local-models.md) | 本地模型选型笔记（2026-06 快照，非产品默认） |

跨仓职责：Bot 管 persona / 业务路由与 `LLM_CHAT_ENABLED` 等开关；本仓管推理、provider、会话与媒体任务。Bot 只连本服务 `:9099`。
