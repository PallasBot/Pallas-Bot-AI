"""媒体任务（demucs / DDSP-SVC）的运行设备解析。

这些子任务通过命令行子进程运行，用 CUDA_VISIBLE_DEVICES 环境变量控制设备：
- media_device=cpu  → CUDA_VISIBLE_DEVICES 置空，强制 CPU（显存吃紧/GPU 专留 LLM 时用）
- media_device=auto → 绑定到 sing_cuda_device 指定的卡
"""

from __future__ import annotations

import platform

from app.core.config import settings


def media_force_cpu() -> bool:
    return str(settings.media_device or "auto").strip().lower() == "cpu"


def cuda_env_prefix() -> str:
    """返回拼接到命令行前的 CUDA_VISIBLE_DEVICES 前缀（含尾部分隔符）。"""
    is_windows = platform.system() == "Windows"
    if media_force_cpu():
        # 置空 = 对子进程隐藏所有 GPU，torch 自动回退 CPU。
        return "set CUDA_VISIBLE_DEVICES= && " if is_windows else "CUDA_VISIBLE_DEVICES= "
    device = settings.sing_cuda_device
    if is_windows:
        return f"set CUDA_VISIBLE_DEVICES={device} && "
    return f"CUDA_VISIBLE_DEVICES={device} "
