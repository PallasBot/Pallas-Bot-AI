# 部署指南

文档总索引：[README.md](README.md)。快速入口见仓库根 [README.md](../README.md)。

本仓提供唱歌 / TTS 等媒体任务，以及可选遗留酒后 RWKV。普通 `@` 聊天在 Bot 内核配置 Provider，不依赖本服务。

## 双仓最低版本

| 组件 | 最低要求 | 校验方式 |
| --- | --- | --- |
| **Pallas-Bot-AI** | `api_version` ≥ `4.1.0` | `GET /health` → `api_version` |
| **Pallas-Bot** | 支持 `AI_SERVER_*` 的 V4 线 | 启动日志 / WebUI 媒体服务 |
| **Redis** | 可达（Celery broker） | AI 仓 `REDIS_URL`；compose 已含 redis |

本机一键：`./scripts/ai_bootstrap.sh`（默认装媒体栈并启动 media worker + API）。

后台任务拆两个 Celery worker：**media**（AI 翻唱 / TTS，吃 GPU）与 **fast**（随机播放 / 点歌，不吃 GPU，独立并发），避免轻任务被翻唱/TTS 长任务堵在队列里。`pallas-ai start` 与 `ctl.sh` 的 `all` 目标会同时拉起两者。

**Windows 本机**：需 [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) 已安装且引擎在跑（bootstrap 用其拉 Redis）；也可用 WSL/本机 Redis，在 `.env` 写 `REDIS_URL`。引擎未开时日志会提示，勿依赖 WSL Containers 公测替代 Compose。

## 方式一：Docker

### 前置

- [Docker Compose](https://github.com/PallasBot/Pallas-Bot/blob/main/docs/deploy/docker.md)；Windows 用 Docker Desktop
- GPU 镜像需宿主机 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

### 快速部署

1. 复制本仓根目录 `docker-compose.yml` 到工作目录（也可整仓克隆）。
2. （可选）准备 `pallas-bot-ai/.env`（自本仓 `.env.example`）与 Bot 侧配置。
3. 启动：

```bash
docker compose up -d
```

首次可能下载镜像与模型，耗时较长。

4. 状态与日志：

```bash
docker compose ps
tail -f ./pallas-bot-ai/logs/uvicorn.log
tail -f ./pallas-bot-ai/logs/celery-media.log
```

与 Bot 全栈 compose 联用时，Bot 可将该日志目录只读挂到 `/ai-logs`，供 WebUI「AI 观测」跟读。

Bot 与本栈不同网络时：`AI_SERVER_HOST=pallasbot-ai`，本侧 `CALLBACK_HOST` 用 Bot 容器名。示例：`deploy/docker-compose.bot-join-ai.example.yml`。

## 方式二：本机手动部署

### 前置

- `uv`（推荐经 `pipx install uv`）
- Redis（例如 `docker run -d --name redis -p 6379:6379 redis`）

### 步骤

1. 依赖（媒体栈，含 torch）：

```bash
uv sync --all-groups --extra cpu   # 或 --extra gpu
git submodule update --init --recursive
```

`--extra gpu` 使用 **torch 2.7.1 + cu128**（含 RTX 50 / `sm_120`）；需宿主机 NVIDIA 驱动支持 CUDA 12.8。CPU 线仍为 torch 2.5.1。从旧 cu124 安装升级后须重新 `uv sync --extra gpu`（或 `PALLAS_GPU=1 ./scripts/ai_bootstrap.sh`）。

按需收窄 group：`sing` / `tts` / `chat`（遗留 RWKV）。

#### 手动补充 DDSP-SVC 6.3 / 6.1（可选）

默认子模块只有 `app/workers/sing/DDSP-SVC`（分支 **6.2**）。`ai_bootstrap.sh` 会初始化它；若源码仓已存在但该目录为空，可在 AI Runtime 根目录恢复默认子模块：

```bash
git submodule update --init app/workers/sing/DDSP-SVC
```

若控制台优先后端选 `ddsp_6.3` / `ddsp_6.1`，需另检出对应目录（约 1.6G/份）。`git clone` 的 URL 与目标路径须在**同一条命令**。

PowerShell（代理；改端口）：

```powershell
$env:HTTPS_PROXY="http://127.0.0.1:7890"; $env:HTTP_PROXY="http://127.0.0.1:7890"
Remove-Item -Recurse -Force app\workers\sing\DDSP-SVC-6.3 -ErrorAction SilentlyContinue
git clone --depth 1 --branch 6.3 https://github.com/PallasBot/DDSP-SVC.git app/workers/sing/DDSP-SVC-6.3
```

终端无代理时可用镜像，例如：

```powershell
git clone --depth 1 --branch 6.3 https://ghproxy.net/https://github.com/PallasBot/DDSP-SVC.git app/workers/sing/DDSP-SVC-6.3
```

6.1：`--branch 6.1` → `app/workers/sing/DDSP-SVC-6.1`。权重与版本须匹配（6.2+ 不兼容旧 checkpoint）。可为每个音色单独指定优先后端（`speaker_backends` / 控制台音色行下拉）；官方 `pallas`（RectifiedFlow）用 **`ddsp_6.2`**，**不是** 6.1。

#### DDSP 权重与音色

优先在控制台 **AI 配置 → 媒体 → 媒体资产** 下载官方 `sing_pallas` 和 `sing_pretrain`：前者提供官方 `pallas` 音色，后者提供 DDSP 预训练资产。自备 DDSP 音色必须将 `*.pt` 与同目录 `config.yaml` 一起放入 `resource/sing/models/<音色 id>/`；缺少 `config.yaml` 时推理会失败。

| 后端 | 音色 | 必需共享权重 |
| --- | --- | --- |
| `ddsp_6.2` / `ddsp_6.1` | `resource/sing/models/<id>/<name>.pt` + `config.yaml` | `resource/sing/models/pretrain/contentvec/checkpoint_best_legacy_500.pt`、`resource/sing/models/pretrain/rmvpe/model.pt`，以及音色 `config.yaml` 指向的 NSF / PC-NSF HiFiGAN 目录 |
| `ddsp_6.3` | 同上；权重需由 6.3 训练 | `resource/sing/models/pretrain/contentvec/pytorch_model.bin`；首次使用会从 [lengyue233/content-vec-best](https://huggingface.co/lengyue233/content-vec-best) 自动下载 |

不要跨版本混用 DDSP `.pt`。`sing_pretrain` 是默认来源；若手工准备，请以该音色的 `config.yaml` 中 `encoder_ckpt` 与 vocoder 路径为准。

#### 社区 RVC 音色（可选）

registry 后端 ID：`rvc`（薄入口 `app/workers/sing/rvc_launcher/infer_rvc.py` → 子模块 `app/workers/sing/RVC`）。

在 AI Runtime 根目录初始化引擎、安装依赖并下载共享权重：

```bash
git submodule update --init app/workers/sing/RVC
uv sync --group sing   # 含 av、faiss-cpu、ffmpeg-python
python -m pip install --upgrade huggingface_hub
hf download lj1995/VoiceConversionWebUI --revision main \
  --include "hubert_base/*" --local-dir resource/sing/models/pretrain/rvc
hf download lj1995/VoiceConversionWebUI rmvpe.pt --revision main \
  --local-dir resource/sing/models/pretrain/rvc
```

下载完成后应是：

```text
resource/sing/models/pretrain/rvc/
├── hubert_base/
│   ├── config.json
│   ├── preprocessor_config.json
│   └── pytorch_model.bin
└── rmvpe.pt
```

若已有旧版 fairseq `hubert_base.pt`，可放在 `resource/sing/models/pretrain/rvc/hubert_base.pt`（或 `hubert_base/hubert_base.pt`），再执行：

```bash
uv run python tools/convert_rvc_hubert.py
```

它会生成上述 Transformers `hubert_base/` 目录。Windows 无软链接权限时，也可直接将同一批文件放到 `app/workers/sing/RVC/assets/hubert_base/` 与 `app/workers/sing/RVC/assets/rmvpe/rmvpe.pt`。

自备音色目录示例：

```text
resource/sing/models/<音色id>/
  xxx.pth          # 必需（社区 RVC；扩展名 .pth，与 DDSP 的 .pt 分流）
  xxx.index        # 可选；优先同 stem，否则目录内唯一 .index
```

控制台「优先后端」可选 `rvc`。RVC 音色必须使用可推理的 `*.pth`，不要放训练过程的 `G_*.pth`；`.index` 可选。默认回退：`ddsp_*` → `rvc` → `sovits_*`。

2. 模型放到 `resource/` 下对应目录（`sing` / `tts` / `chat`），可从 [Hugging Face pallasbot](https://huggingface.co/pallasbot/Pallas-Bot/tree/main) 获取。
3. 配置 `.env`：至少 `CALLBACK_HOST` / `CALLBACK_PORT` 指向 Bot；建议设置 `PALLAS_AI_API_TOKEN`（与 Bot / 插件 Bearer 一致）。

4. 启动（`pallas-ai` 会同时管理 API 与 media；默认目标为 `all`）：

```bash
uv run pallas-ai start
uv run pallas-ai status
# 只重启媒体任务进程；API 不受影响
uv run pallas-ai restart media
# 轻任务（随机播放/点歌）单独重启；默认并发由 CELERY_FAST_WORKER_CONCURRENCY 控制
uv run pallas-ai restart fast
# 仅在需要清理遗留 Celery 任务状态时执行
uv run pallas-ai purge-stale
# 或
./scripts/ai_bootstrap.sh
```

开发热重载（不扫 workers 下大目录）：

```bash
UVICORN_RELOAD=true uv run python -m app.run_api
```

## API Bearer Token

Bot WebUI「媒体服务」里的 **Bearer Token** 须与 AI 侧 **`PALLAS_AI_API_TOKEN`** 一致。

- 非空时：`GET /api/ops/logs` 及推荐的 **`/v1/*`** 要求 `Authorization: Bearer <token>`
- 留空：不对 Bearer 校验（仅建议本机调试）

```bash
curl -H "Authorization: Bearer 你的token" "http://127.0.0.1:9099/api/ops/logs?kind=uvicorn&n=5"
curl -s http://127.0.0.1:9099/health | python3 -m json.tool
```

对外推荐 **`/v1`**；`/api` 为兼容入口。运行时边界见 [architecture/runtime.md](architecture/runtime.md)。
