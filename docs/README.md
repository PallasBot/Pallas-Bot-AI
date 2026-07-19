# 文档索引

面向 **部署用户 / 运维** 与 **扩展开发者**。内部开发日记与已落地设计稿已清理，不再放在本目录。

## 用户与运维

| 文档 | 说明 |
| --- | --- |
| [Deployment.md](Deployment.md) | 部署总览：Docker / 本机、环境变量、双仓版本 |
| [deploy/remote-only.md](deploy/remote-only.md) | 纯远端 API（无本地 Ollama / GPU） |
| [operate/ollama-gpu-watchdog.md](operate/ollama-gpu-watchdog.md) | Ollama GPU 假死探活与修复 |

快速入口也见仓库根 [README.md](../README.md)。

## 开发者

| 文档 | 说明 |
| --- | --- |
| [architecture/runtime.md](architecture/runtime.md) | uvicorn + Celery + provider 运行时 |
| [architecture/platform-roadmap.md](architecture/platform-roadmap.md) | V4+ 定位、兼容策略与能力基线 |
| [architecture/persona-affect-refine.md](architecture/persona-affect-refine.md) | 群风格 affect-refine API 契约 |
| [architecture/local-models.md](architecture/local-models.md) | 本地模型选型笔记（历史快照，非产品默认） |

架构目录总览：[architecture/README.md](architecture/README.md)。
