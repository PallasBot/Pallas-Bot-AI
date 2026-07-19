# AI 仓平台化路线（V4+）

> 本仓演进与兼容策略说明。部署步骤见 [Deployment.md](../Deployment.md)；运行时见 [runtime.md](runtime.md)。

Bot 管 persona / 业务路由；本仓管推理、provider、会话与媒体任务。Bot **只连** `:9099`，换 local / remote / chain 不必改 Bot 编译产物。

## 定位

| 做 | 不做 |
| --- | --- |
| 统一 Chat API、provider 链、模型 / runtime | 群风格统计、repeater 触发逻辑 |
| Celery 异步 + `/callback` | Bot ingress / 分片 claim |
| 密钥、远端 `base_url`、GPU 进程 | 主仓 WebUI 业务开关（如 `LLM_CHAT_ENABLED`） |

## 升级兼容策略

**双栈并存**：V4 的 LLM 网关 **不替代** 开箱即用的 legacy 媒体栈（酒后 RWKV、唱歌、TTS）。

| 层级 | 能力 | API | 说明 |
| --- | --- | --- | --- |
| **必须保持** | 酒后 RWKV | `POST /api/chat/{id}` | 低配置用户可不用 Ollama |
| **必须保持** | 唱歌 / TTS | `/api/sing/*`、`/api/tts/*` | 发版前 smoke |
| **主路径** | LLM 闲聊 / 接话辅助 | `/api/v1/chat/completions`、`/api/llm/*` | Bot 开 `LLM_CHAT_ENABLED` |
| **兼容保留** | 旧 Ollama 管理路径 | `/api/ollama/*` | deprecated；新集成用 `/api/llm/*` |

原则：

1. **少折腾**：可继续走 RWKV `/api/chat`，不必开 `LLM_CHAT_ENABLED`。
2. **要 LLM**：Bot 开 `LLM_CHAT_ENABLED`，走统一 Chat API；与 RWKV 互不影响。
3. **回归**：改 LLM / provider / session 时，至少确认 sing / TTS / RWKV 三条 legacy 路径未断。

## 当前能力基线

| 能力 | 状态 |
| --- | --- |
| `POST /api/v1/chat/completions/{id}` | 已交付 |
| `/api/llm/*` 管理接口 | 已交付 |
| Provider `local_only` / `remote_only` / `chain` | 已交付 |
| Session（默认 Redis，`app/session/`） | 已交付 |
| `GET /health` 聚合快照 | 已交付 |
| Tool schema + 执行环 | 已交付 |
| MoE / categorizer / token 统计 | 已交付 |
| 超长会话摘要 | 已交付 |
| Image Runtime / 统一 media task | MVP 已交付 |

## 平台支柱（简）

1. **契约**：`/health.api_version` 与 Bot 启动探测对齐；破坏性变更升版本并写迁移说明。
2. **可靠**：LLM / sing / TTS 分队列；provider `chain` 可 `try_next`；失败经 callback 回 Bot。
3. **可观测**：`/health` + `/api/llm/stats`；Prometheus `/metrics` 仍为后续项。
4. **配置**：密钥与远端只在本仓；模型热更换见 `PUT /api/llm/model`。

## 后续（需运行环境验证）

- Redis session 多 worker 生产验证
- `remote_only` 长时间无本地依赖验证
- 与 Bot `dev-v2` 维护窗双仓联调
- 可选：Prometheus 指标导出

> 删除 RWKV `tasks/chat/` **不做**——留给不想折腾 Ollama 的用户。

## 相关文档

- [runtime.md](runtime.md) — 运行时
- [local-models.md](local-models.md) — 本地模型选型笔记
- [persona-affect-refine.md](persona-affect-refine.md) — affect-refine API
- [docs/README.md](../README.md) — 文档总索引
