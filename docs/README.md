# 文档索引

面向 **部署用户 / 运维** 与 **扩展开发者**。内部开发日记与已落地设计稿已清理，不再放在本目录。

本仓现为 **媒体后端**（唱歌 / TTS / 酒后 RWKV 等）；LLM 对话与 Provider 已迁至 [Pallas-Bot](https://github.com/PallasBot/Pallas-Bot) 内核。

## 用户与运维

| 文档 | 说明 |
| --- | --- |
| [Deployment.md](Deployment.md) | 部署总览：Docker / 本机、环境变量、双仓版本 |

快速入口也见仓库根 [README.md](../README.md)。

## 开发者

| 文档 | 说明 |
| --- | --- |
| [architecture/platform-roadmap.md](architecture/platform-roadmap.md) | V4+ 定位、兼容策略与能力基线（含历史 LLM 职责说明，以现行媒体栈为准） |
| [architecture/runtime.md](architecture/runtime.md) | uvicorn + Celery 运行时（部分章节仍描述旧 LLM worker，联调以根 README 为准） |

架构目录总览：[architecture/README.md](architecture/README.md)。

> 下列文档对应已移除的代码路径，仅作历史参考，勿按文操作：  
> [deploy/remote-only.md](deploy/remote-only.md)、[operate/ollama-gpu-watchdog.md](operate/ollama-gpu-watchdog.md)、  
> [architecture/persona-affect-refine.md](architecture/persona-affect-refine.md)、[architecture/local-models.md](architecture/local-models.md)。
