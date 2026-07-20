"""SVC 推理入口。

由 `app.tasks.sing.svc_registry` 提供模型后端注册表,加新模型族改
`resource/sing/registry.yaml` 即可,本文件无需改动。

调用方:`app/tasks/sing/sing_tasks.py:128`
    svc = await asyncify(inference)(vocals, Path("resource/sing/svc"),
                                    key=key, speaker=speaker, locker=gpu_locker)
    if not svc: ...  # None 表示全 backend 失败
    mix(svc, ...)    # 成功后用 svc.stem
"""

from __future__ import annotations

import platform
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from pydub import AudioSegment

from app.core.config import settings
from app.core.logger import logger
from app.media_models import order_backends_by_preference, resolve_preferred_backend, resolve_sing_speaker
from app.tasks.sing.svc_registry import (
    ModelBackend,
    SvcRegistry,
    build_command,
    get_registry,
    run_subprocess,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.utils.gpu_locker import GPULockManager


@contextmanager
def _maybe_lock(locker: GPULockManager | None, *, owner: dict[str, str]) -> Iterator[None]:
    """锁是可选参数——传 None 时退化为无操作 contextmanager。"""
    if locker is None:
        yield
    else:
        with locker.acquire(unload_llm=True, owner=owner):
            yield


def _find_speaker_model(speaker_dir: Path, model_glob: str) -> Path | None:
    """在 speaker_dir 下找一个模型文件,优先挑文件名字典序最大的(即最新训练的)。

    DDSP 风格:`model_100000.pt` / `model_90000.pt` —— 选最大的 step
    SoVITS 风格:`G_240000.pth` / `G_29600.pth` —— 选最大的 step
    """
    candidates = sorted(speaker_dir.glob(model_glob))
    return candidates[-1] if candidates else None


def _resolve_output_path(output_dir: Path, stem: str, key: int, speaker: str, backend: ModelBackend) -> Path:
    """构造输出路径,跨平台都用 Path,Windows/Linux 都安全。"""
    return output_dir / f"{stem}_{key}key_{speaker}{backend.output_suffix}.{backend.output_format}"


def _try_backend(
    backend: ModelBackend,
    speaker_dir: Path,
    song_path: Path,
    output_path: Path,
    key: int,
    model_path: Path,
    locker: GPULockManager | None,
) -> Path | None:
    """在 GPU 锁内执行单个 backend 的推理。成功返回实际产物 Path,失败返回 None。

    重要:DDSP 把 -o 当文件用,SoVITS 把 -o 当目录用(脚本内部决定文件名)——验证产物
    是否真的写出来不能一刀切看 `output_path.exists()`,而是委托 backend 的
    `find_output(output_path, since_mtime=...)` 按约定去找,避免 SoVITS 成功却误判失败。
    """
    cmd = build_command(backend, speaker_dir, song_path, output_path, key, model_path)
    logger.info("svc inference try: backend={} speaker={} cmd={}", backend.name, speaker_dir.name, cmd)

    # 快照:调用前 output_dir 里目标格式文件的最大 mtime。
    # 用作 find_output 的过滤阈值,排除上次推理的残留(尤其是 SoVITS 那种 -o 是目录的情况)。
    pre_max_mtime = max(
        (p.stat().st_mtime for p in output_path.parent.glob(f"*.{backend.output_format}")),
        default=0.0,
    )

    owner = {
        "kind": "sing",
        "step": "svc",
        "song": song_path.name,
        "speaker": speaker_dir.name,
    }
    with _maybe_lock(locker, owner=owner):
        try:
            result = run_subprocess(cmd, timeout=settings.svc_inference_timeout)
        except subprocess.TimeoutExpired:
            logger.error(
                "svc inference timeout: backend={} speaker={} timeout={}s",
                backend.name,
                speaker_dir.name,
                settings.svc_inference_timeout,
            )
            return None
        except Exception:
            logger.exception("svc inference crashed: backend={} speaker={}", backend.name, speaker_dir.name)
            return None

    if result.returncode != 0:
        # 截断 stderr 避免日志爆炸;详细诊断可去 logs/app.log
        stderr_tail = (result.stderr or "")[-500:]
        logger.warning(
            "svc inference failed: backend={} speaker={} rc={} stderr_tail={}",
            backend.name,
            speaker_dir.name,
            result.returncode,
            stderr_tail,
        )
        return None

    actual_output = backend.find_output(output_path, since_mtime=pre_max_mtime)
    if actual_output is None:
        logger.warning(
            "svc inference rc=0 but no fresh output: backend={} speaker={} expected={} dir={}",
            backend.name,
            speaker_dir.name,
            output_path,
            output_path.parent,
        )
        return None

    if actual_output != output_path:
        logger.info(
            "svc inference ok: backend={} predicted={} actual={}",
            backend.name,
            output_path,
            actual_output,
        )
    else:
        logger.info("svc inference ok: backend={} out={}", backend.name, actual_output)
    return actual_output


def inference(
    song_path: Path,
    output_dir: Path,
    key: int = 0,
    speaker: str = "",
    locker: GPULockManager | None = None,
) -> Path | None:
    """按 fallback_order 遍历注册表里"该 speaker 资源齐备"的 backend,首个成功即返回。

    Returns:
        输出音频文件 Path(已存在磁盘上);全 backend 失败返回 None。
    """
    speaker = resolve_sing_speaker(speaker)

    if platform.system() == "Windows":
        song_path = mp3_to_wav(song_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    speaker_dir = (Path(settings.svc_models_root) / speaker).absolute()
    if not speaker_dir.is_dir():
        logger.error("speaker dir 不存在: {}", speaker_dir)
        return None

    registry: SvcRegistry = get_registry()
    candidates = registry.compatible_backends(speaker_dir)
    if not candidates:
        logger.error(
            "speaker={} 在 {} 下没有可用的 backend(检查 .pt/.pth/config.json 是否齐备)",
            speaker,
            speaker_dir,
        )
        return None

    preferred = resolve_preferred_backend()
    candidates = order_backends_by_preference(candidates, preferred)
    if preferred:
        logger.info(
            "svc inference order: preferred={} first={} speaker={}",
            preferred,
            candidates[0].name if candidates else None,
            speaker,
        )

    stem = song_path.stem
    for backend in candidates:
        model_path = _find_speaker_model(speaker_dir, backend.model_glob)
        if model_path is None:
            # 理论上 compatible_backends 已保证 model_glob 命中,这里双保险
            continue
        output_path = _resolve_output_path(output_dir, stem, key, speaker, backend)
        # 缓存命中检查必须用 backend.find_output——SoVITS 的产物文件名跟预测不一致,
        # 直接 `output_path.exists()` 会漏掉 SoVITS 缓存。
        cached = backend.find_output(output_path)
        if cached is not None:
            logger.debug("svc cache hit: backend={} out={}", backend.name, cached)
            return cached
        result = _try_backend(backend, speaker_dir, song_path, output_path, key, model_path, locker)
        if result is not None:
            return result

    logger.error("svc inference 用尽所有 backend 仍未成功: speaker={}", speaker)
    return None


def mp3_to_wav(mp3_file_path: Path) -> Path:
    """Windows 下 DDSP/SoVITS 不直接吃 mp3,转 wav。Linux 上游 submodule 自己处理,不走这里。"""
    wav_file_path = mp3_file_path.parent / (mp3_file_path.stem + ".wav")
    if wav_file_path.exists():
        return wav_file_path
    sound = AudioSegment.from_mp3(mp3_file_path)
    sound.export(wav_file_path, format="wav")
    # os.remove(mp3_file_path)
    return Path(wav_file_path)
