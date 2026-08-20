"""DDSP checkpoint 与 backend 版本的轻量兼容探测。

注册表只认「有 *.pt + 脚本存在」，不会区分 6.2（Conv1d）与 6.3（Linear）。
官方 pallas.pt 是 Conv1d；若 preferred=ddsp_6.3 仍会白跑数十秒再 size mismatch。
此处在进 GPU 前读 checkpoint 里 input_projection 的权重维度，跳过不兼容 backend。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logger import logger

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from app.media.sing.registry import ModelBackend

# 6.1 / 6.2 LYNXNet 用 Conv1d → weight ndim=3；6.3 改为 Linear → ndim=2
ARCH_CONV1D = "conv1d"
ARCH_LINEAR = "linear"
ARCH_UNKNOWN = "unknown"

_BACKEND_ARCH: dict[str, str] = {
    "ddsp_6.3": ARCH_LINEAR,
    "ddsp_6.2": ARCH_CONV1D,
    "ddsp_6.1": ARCH_CONV1D,
}

_PROBE_KEY = "reflow_model.velocity_fn.input_projection.weight"
# (resolved path, mtime_ns) → arch
_ARCH_CACHE: dict[tuple[str, int], str] = {}


def clear_ddsp_arch_cache() -> None:
    _ARCH_CACHE.clear()


def required_arch_for_backend(backend_name: str) -> str | None:
    return _BACKEND_ARCH.get(backend_name)


def backend_matches_ddsp_arch(backend_name: str, arch: str) -> bool:
    """unknown 时不拦截（探测失败则保持旧行为：继续尝试）。"""
    required = required_arch_for_backend(backend_name)
    if required is None or arch == ARCH_UNKNOWN:
        return True
    return required == arch


def probe_ddsp_checkpoint_arch(model_path: Path) -> str:
    """返回 conv1d / linear / unknown。优先 mmap，避免整包进内存。"""
    path = model_path.resolve()
    if not path.is_file():
        return ARCH_UNKNOWN
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return ARCH_UNKNOWN
    cache_key = (str(path), mtime_ns)
    cached = _ARCH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    arch = ARCH_UNKNOWN
    try:
        import torch  # noqa: PLC0415

        try:
            ckpt = torch.load(path, map_location="cpu", mmap=True, weights_only=False)
        except TypeError:
            # 旧 torch 无 mmap / weights_only
            ckpt = torch.load(path, map_location="cpu")
        model = ckpt.get("model", ckpt) if isinstance(ckpt, dict) else None
        if isinstance(model, dict) and _PROBE_KEY in model:
            weight = model[_PROBE_KEY]
            ndim = int(getattr(weight, "ndim", 0) or 0)
            if ndim == 3:
                arch = ARCH_CONV1D
            elif ndim == 2:
                arch = ARCH_LINEAR
    except Exception as exc:
        logger.debug("ddsp checkpoint arch probe failed path={} err={}", path, exc)

    _ARCH_CACHE[cache_key] = arch
    return arch


def filter_backends_by_ddsp_checkpoint(
    backends: Iterable[ModelBackend],
    model_path: Path | None,
) -> list[ModelBackend]:
    """按 checkpoint 架构过滤 DDSP backend；非 DDSP 原样保留。"""
    items = list(backends)
    if not items or model_path is None or not model_path.is_file():
        return items

    need_probe = any(required_arch_for_backend(b.name) for b in items)
    if not need_probe:
        return items

    arch = probe_ddsp_checkpoint_arch(model_path)
    if arch == ARCH_UNKNOWN:
        return items

    kept: list[ModelBackend] = []
    for backend in items:
        if backend_matches_ddsp_arch(backend.name, arch):
            kept.append(backend)
            continue
        logger.info(
            "backend {} skipped: checkpoint arch={}, needs {} model={}",
            backend.name,
            arch,
            required_arch_for_backend(backend.name),
            model_path.name,
        )
    return kept


def resolve_ddsp_model_for_probe(speaker_dir: Path, backends: Iterable[ModelBackend]) -> Path | None:
    """在 speaker 目录里找一个用于探测的 *.pt（取字典序最大，与推理选模一致）。"""
    globs: list[str] = []
    for backend in backends:
        if required_arch_for_backend(backend.name) is None:
            continue
        if backend.model_glob not in globs:
            globs.append(backend.model_glob)
    if not globs:
        globs = ["*.pt"]
    candidates: list[Path] = []
    for pattern in globs:
        candidates.extend(p for p in speaker_dir.glob(pattern) if p.is_file())
    if not candidates:
        return None
    return max(candidates)
