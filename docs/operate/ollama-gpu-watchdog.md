# Ollama GPU 探活与自动修复

Ollama 在 Docker + NVIDIA GPU 下**长跑**后，可能出现 HTTP 仍正常、但推理已回退 CPU 的情况。

**首选（AI 服务内置）**：`LLM_OLLAMA_GPU_GUARD=true`（默认）时，Celery/API 启动与后台线程会探活；失败且宿主机可执行 `docker` 时自动 `docker restart`（需配置 `OLLAMA_CONTAINER`，如 1Panel 常为 `ollama`）。`/health` → `llm.ollama_gpu` 可观测。

**备选（宿主机 cron）**：本仓 `scripts/ollama_gpu_watchdog.sh`（AI 进程无 docker 权限时使用）。

## 现象

| 检查项 | 正常 | GPU 假死 |
| --- | --- | --- |
| `curl …/api/tags` | 200 | 200 |
| 容器内 `nvidia-smi` | 正常 | `Failed to initialize NVML: Unknown Error` |
| Ollama 日志 | `CUDA0` buffer | `no CUDA-capable device`、`CPU KV buffer` |
| 单次 chat | 数秒 | **1～2 分钟** |

## 原因（简述）

容器启动时 GPU 设备会挂进容器；宿主机若发生驱动重载、GPU 重置、`nvidia-persistenced` 变化，或 NVIDIA Container Toolkit 与**旧容器**之间的 NVML 通道异常，容器进程仍存活，但容器内 CUDA/NVML 失效。Ollama 会静默回退 CPU。

`ollama list` 与普通 healthcheck **发现不了**；需 `nvidia-smi` 或看推理日志。

## 脚本用法

```bash
cd Pallas-Bot-AI
chmod +x scripts/ollama_gpu_watchdog.sh

# 仅检查（异常 exit 1）
./scripts/ollama_gpu_watchdog.sh

# 异常时 restart 容器后再验
./scripts/ollama_gpu_watchdog.sh --fix

# cron 用：少输出
./scripts/ollama_gpu_watchdog.sh --fix --quiet
```

`./scripts/ai_bootstrap.sh --check-only` 会顺带跑 GPU 探活（`LLM_PROVIDER_MODE=remote_only` 或 `OLLAMA_SKIP_GPU=1` 时跳过）。

### 环境变量

| 变量 | 说明 |
| --- | --- |
| `OLLAMA_CONTAINER` | 容器名；不设则自动探测 `pallas-ai-ollama` / `pallas-full-ollama` / `ollama` |
| `OLLAMA_COMPOSE_DIR` | 设置后 `--fix` 用 `docker compose restart ollama`（而非 `docker restart`） |
| `OLLAMA_COMPOSE_FILES` | compose 文件列表，空格分隔，相对 `OLLAMA_COMPOSE_DIR` |
| `OLLAMA_SKIP_GPU=1` | 跳过 GPU 检查 |

### 1Panel / 独立 Ollama 容器

```bash
OLLAMA_CONTAINER=ollama ./scripts/ollama_gpu_watchdog.sh --fix
```

### LLM compose（本仓）

```bash
OLLAMA_COMPOSE_DIR=/path/to/Pallas-Bot-AI \
OLLAMA_COMPOSE_FILES="docker-compose.llm.yml docker-compose.llm.gpu.yml" \
./scripts/ollama_gpu_watchdog.sh --fix
```

## 定时任务（推荐）

复制示例并按路径修改：

```bash
cp deploy/ollama-gpu-watchdog.cron.example /etc/cron.d/pallas-ollama-gpu
# 编辑 OLLAMA_CONTAINER、脚本绝对路径
sudo chmod 644 /etc/cron.d/pallas-ollama-gpu
```

或一键安装（需 root，会写入 `/etc/cron.d/pallas-ollama-gpu`）：

```bash
sudo ./scripts/install_ollama_gpu_watchdog_cron.sh
sudo OLLAMA_CONTAINER=ollama ./scripts/install_ollama_gpu_watchdog_cron.sh
```

用户 crontab 示例：

```cron
*/10 * * * * OLLAMA_CONTAINER=ollama /path/to/Pallas-Bot-AI/scripts/ollama_gpu_watchdog.sh --fix --quiet >>/var/log/ollama-gpu-watchdog.log 2>&1
```

## Compose healthcheck

使用 GPU 覆盖层时，Ollama healthcheck 为 `ollama list && nvidia-smi`：

- 本仓：`docker compose -f docker-compose.llm.yml -f docker-compose.llm.gpu.yml up -d`
- Bot 全栈：`docker-compose.full.gpu.yml`（Bot 仓）

`docker ps` 中 Ollama 可能显示 **unhealthy**；Docker **不会**仅因 unhealthy 自动 restart，仍建议配合本脚本或手动重启。

## 手动恢复

```bash
docker restart ollama
# 或 compose 目录下
docker compose restart ollama
```

重启后确认：

```bash
docker exec ollama nvidia-smi
docker logs ollama --tail 20 | grep -E 'CUDA|CPU'
```

若仍失败，再查宿主机 `nvidia-smi`、`nvidia-container-toolkit`、驱动与 `nvidia-persistenced`。
