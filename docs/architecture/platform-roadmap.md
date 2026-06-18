# AI 仓平台化路线（4.0+）

> **本文档为 Pallas-Bot-AI 4.0+ 演进路线的权威来源。**  
> 主仓只维护 [Bot↔AI 协同契约](https://github.com/PallasBot/Pallas-Bot/blob/dev-v2/docs/architecture/pallas-final-ai-shape.md)（职责切分、配置键、跨仓验收）；具体实现阶段与 backlog 以本文件为准。

Bot 管 persona / 业务路由；AI 仓管推理、provider、会话基础设施。

## 定位

| 做 | 不做 |
| --- | --- |
| 统一 Chat API、provider 链、模型/runtime 管理 | 群风格统计、repeater 触发逻辑 |
| Celery 异步 + `/callback` | Bot ingress / 分片 claim |
| 密钥、远端 base_url、GPU 进程 | 主仓 WebUI 业务开关（`LLM_CHAT_ENABLED` 等） |

Bot **只连** `:9099`；换 local/remote/chain 不改编译主仓。

## 升级兼容策略（4.0+）

**双栈并存**：4.0 新增 LLM 网关，**不替代**「开箱即用、少折腾」的 legacy 媒体栈。

| 层级 | 能力 | API / 路径 | 升级要求 |
| --- | --- | --- | --- |
| **必须保持** | 酒后 RWKV 聊天 | `POST /api/chat/{id}` | 发版前 smoke：模型资源、`chat` Celery task、callback |
| **必须保持** | 唱歌 sing | `/api/sing/*` | 同上；DDSP-SVC / demucs 依赖与 GPU 锁不退化 |
| **必须保持** | TTS | `/api/tts/*` | 同上；GPT-SoVITS 路径与资源目录兼容 |
| **新能力 / 可演进** | LLM 闲聊、repeater LLM | `/api/v1/chat/completions`、`/api/llm/*` | provider 重命名、session Redis 等 **不要求** 用户改 Ollama 以外习惯 |
| **低优先级兼容** | 旧 Ollama 管理路径 | `/api/ollama/*` | deprecated 即可；新集成只用 `/api/llm/*` |

原则：

1. **不想折腾的用户**：继续 `CHAT_ENABLE` + 旧 `/api/chat`（RWKV），无需装 Ollama、无需 `LLM_CHAT_ENABLED`。
2. **要 LLM 的用户**：Bot 开 `LLM_CHAT_ENABLED`，走统一 Chat API；与 RWKV 路径互不影响。
3. **4.0 PR 回归清单**：动 LLM/provider/session 代码时，**至少确认 sing / TTS / RWKV chat 三条 legacy 路径未断**；Ollama 路径名变更可随文档迁移，不单独守旧集成。

## 当前基线（4.0.x）

| 能力 | 状态 |
| --- | --- |
| `POST /api/v1/chat/completions/{id}` | 已交付 |
| `/api/llm/*` management（canonical） | 已交付 |
| `/api/ollama/*` | 兼容保留，deprecated |
| Provider `local_only` / `remote_only` / `chain` | 已交付 |
| `metadata.task` / `temperature` / `token_count` | 已交付 |
| 进程内 session | **已迁 `app/session/`，默认 redis** |
| `GET /health` → `api_version` + `llm`/media/TTS 聚合快照 | 已交付 |
| Tool schema 注入 + 执行环 | **已交付**（`tool_loop` + `bot_tools` 回调执行 + chain 接线 + 干员查人兜底） |
| MoE tier 路由 + categorizer | **已交付**（含 `needs_tools` / `needs_vision` 分类与指标） |
| token 统计（prompt/completion） | **已交付**（`llm_task_metrics`，Celery+API 共享落盘） |
| 超长会话摘要 | **已交付**（达阈值异步摘要旧轮） |
| Image Runtime / 统一 media task | **已交付 MVP**（画图 callback、参考图 edits、sing 失败兜底） |

## 成熟平台四支柱

### 1. 契约稳定（与 Bot 同频）

- **Semver**：`/health.api_version` 与 Bot 启动探测对齐；破坏性变更升 minor/major 并写迁移说明。
- **契约测试**：AI 仓 `tests/` 覆盖 provider/router；Bot `integration_llm_chat.py` 为跨仓冒烟；目标 nightly compose 双仓。
- **Deprecation 策略**：LLM 侧 `/api/ollama/*` 保留 ≥1 个小版本；**RWKV `/api/chat` 与 sing/tts 不在此列**（长期保留给低配置用户）。

### 2. 运行时可靠

- **队列隔离**：LLM / sing / TTS 分 task；LLM 长耗时不进 uvicorn 同步路径（见 [runtime.md](runtime.md)）。
- **Provider 失败**：chain `try_next`；单次任务 `LLM_MAX_RETRIES`；callback `status=failed` 由 Bot 回退。
- **local 拉起**：`LLM_AUTO_START` 仅 dev/单机；Docker 全栈由 compose 管后端进程。

### 3. 可观测

- **Health**：provider 模式、remote 是否配置、moe/tools 开关（已有）。
- **待补**：按 task/provider 的延迟与失败率指标；Celery queue depth；可选 Prometheus `/metrics`。
- **日志**：request_id / session / task 贯穿 uvicorn → Celery → callback。

### 4. 配置与部署

- **单源**：AI 仓 `.env` / compose env；Bot 不存 remote 密钥。
- **热更换模型**：`logs/llm_runtime.json`，API `PUT /api/llm/model`。
- **文档**： [Deployment.md](../Deployment.md) 双仓最低版本表（待维护）。

## 阶段交付（与主仓 persona-llm-roadmap 对齐）

| 阶段 | AI 仓 | 主仓依赖 | 目标 |
| --- | --- | --- | --- |
| **4.0.0** ✓ | 统一网关 + provider + rename | `features/llm` 统一客户端 | 可联调 staging |
| **4.0.1** ✓ | session Redis 可选；health 增强；CI pytest | P3 分片会话验收 | 多 worker 无重复回复（代码已交付，生产验证待跑） |
| **4.0.2** ~ | remote_only 配置校验与健康探测 | repeater fallback/polish 联调 | 远端薄侧车稳定（联调待跑） |
| **4.0.x** ✓ | Tool call 执行环（schema → 调 Bot 或内联 handler） | P9 方舟 KB tools | `@牛牛` 带工具 |
| **4.0.x+** ✓ | MoE / categorizer / tier→remote / token metrics | [llm-efficiency-roadmap](https://github.com/PallasBot/Pallas-Bot/blob/main/docs/architecture/llm-efficiency-roadmap.md) A1–A4 | 省 Token + 可观测 |
| **4.1** ~ | 会话持久化 + 超长摘要（embedding 记忆可选） | P8 / A2 RAG | 长上下文（摘要已交付；embedding 待评估） |
| **4.1+** ✓ | Media 栈（Image/sing/TTS）独立于 Chat provider | sing/draw 插件 | 算力分池（Image Runtime MVP 已交付） |

## 4.0.1 交付包（当前冲刺）

> 目标：CI 守门 + 多 worker 会话一致 + 跨仓联调前置。拆为 **3 个 PR**，按序合入。

### PR-1 · 工程底座（优先） ✓

| 项 | 路径 / 动作 |
| --- | --- |
| pytest 只收集 `tests/` | `pyproject.toml` → `[tool.pytest.ini_options]` |
| CI 跑 ruff + pytest | `.github/workflows/ci.yml`；触发分支含 `feat/4.0` |
| 版本对齐 | `pyproject` `version` 与 `main.API_VERSION` 均为 `4.0.0` |

### PR-2 · Session 抽象 ✓

| 项 | 路径 / 动作 |
| --- | --- |
| 会话 store 接口 | `app/session/`（`memory.py` / `redis.py` / `get_session_store()`） |
| Celery 任务改用 store | `app/tasks/llm/chat_tasks.py` |
| 配置 | `LLM_SESSION_BACKEND=redis`（默认）；`memory` 仅本地调试 |
| 删除进程内 dict | 移除 `app/tasks/llm/session.py` |
| 单测 | `tests/test_session.py` |
| health | `/health.llm.session_backend` |

### PR-3 · 契约补齐与联调（进行中）

| 项 | 路径 / 动作 | 状态 |
| --- | --- | --- |
| legacy chat 传 metadata | `llm_manage` → `submit_llm_chat_completion` | ✓ |
| integration compose | `docker-compose.4.0-ci.yml` | ✓ |
| Deployment 双仓版本表 | `docs/Deployment.md` | ✓ |
| Bot 版本协商 | 主仓 `startup_probe` 比对 `api_version` 下限 | ✓ |
| pg_session 推理 | Bot PG messages → AI 直推，不叠 Redis | ✓ |
| 维护窗联调 | Bot `integration_*`（含 `--memory-test`） | 待运行（需双仓+Redis+多 worker 环境） |

### 路径演进（4.0.1 后）

```
app/session/          # 会话存储（memory / redis）
app/providers/        # LLM 推理链（不变）
app/services/llm_*    # HTTP 入队与 options 解析（不变）
app/tasks/llm/        # 仅 Celery 任务；不再含 session 实现
app/tasks/chat/       # RWKV legacy，4.0.2 标 deprecated 或迁 tasks/legacy/
```

### 暂缓（4.0.2+）

- remote_only 生产加固、rate limit（配置校验骨架在，7×24 验证待跑）
- `/metrics` Prometheus 导出（task/provider 延迟与失败率、queue depth）
- 删除 RWKV `tasks/chat/`（**不做**；保留给不折腾 Ollama 的用户，见 [platform-roadmap · 升级兼容策略](platform-roadmap.md#升级兼容策略40)）

> Tool call 执行环、MoE/categorizer、token 统计、超长摘要、Image/media 栈已于 4.0.x 提前交付，不再列入暂缓。

## 4.0.1 优先 backlog（历史条目，已并入上表）

1. ~~Session 后端抽象~~ → PR-2
2. ~~版本协商~~ → PR-3 + Bot
3. ~~Integration compose~~ → PR-3
4. ~~文档同步~~ → PR-3
5. ~~pytest 排除 GPT_SoVITS~~ → PR-1

## 验收（AI 仓侧）

- [x] `tests/` provider + llm_chat 通过
- [x] `/health.llm` 反映 provider 配置
- [x] Session store 抽象（`app/session/`，默认 redis）
- [x] Tool call 端到端（`tool_loop` + `bot_tools` callback 执行环已交付，代码级通过）
- [x] MoE / categorizer / token 统计 / 超长摘要（A1–A4 对应能力已交付）
- [x] Image Runtime / 统一 media task MVP
- [ ] Redis session 多 worker 生产验证（需运行环境）
- [ ] remote_only 7×24 无 local 依赖（需运行环境）
- [ ] 与 Bot `dev-v2` 维护窗联调通过（需双仓+Redis+多 worker 环境）

## 相关文档

- [runtime.md](runtime.md) — uvicorn + Celery + provider
- [4.0-local-models.md](4.0-local-models.md) — 本地模型选型参考
- [persona-affect-refine.md](persona-affect-refine.md) — 群风格 refine API
