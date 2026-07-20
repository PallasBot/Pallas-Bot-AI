"""唱歌说话人 / TTS 音色清单与默认项（落盘 data/media_models.json）。"""

from __future__ import annotations

import json
import threading
from pathlib import Path  # noqa: TC003
from typing import Any

from app.core.config import settings
from app.core.logger import logger
from app.media_assets import detect_deploy_mode, repo_root

_LOCK = threading.Lock()

_DEFAULT_TTS = {
    "ref_audio_path": "resource/tts/ref_audio/进驻设施.wav",
    "prompt_text": "この角で家具を倒してしまわないよう、気をつけますね。",
    "prompt_lang": "ja",
    "text_lang": "zh",
}

_DEFAULT_SING = {
    "default_speaker": "pallas",
    # 空字符串 = 按 registry.yaml fallback_order；非空则优先尝试该 backend，失败仍回退
    "preferred_backend": "",
}


def media_models_path(root: Path | None = None) -> Path:
    base = repo_root(root)
    return base / "data" / "media_models.json"


def _default_payload() -> dict[str, Any]:
    return {
        "sing": dict(_DEFAULT_SING),
        "tts": dict(_DEFAULT_TTS),
    }


def load_media_models(root: Path | None = None) -> dict[str, Any]:
    path = media_models_path(root)
    payload = _default_payload()
    if not path.is_file():
        return payload
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("media_models.json 读取失败: {}", exc)
        return payload
    if not isinstance(raw, dict):
        return payload
    sing = raw.get("sing") if isinstance(raw.get("sing"), dict) else {}
    tts = raw.get("tts") if isinstance(raw.get("tts"), dict) else {}
    if isinstance(sing.get("default_speaker"), str) and sing["default_speaker"].strip():
        payload["sing"]["default_speaker"] = sing["default_speaker"].strip()
    if isinstance(sing.get("preferred_backend"), str):
        payload["sing"]["preferred_backend"] = sing["preferred_backend"].strip()
    for key in _DEFAULT_TTS:
        val = tts.get(key)
        if isinstance(val, str) and val.strip():
            payload["tts"][key] = val.strip()
    return payload


def save_media_models(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    path = media_models_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = _default_payload()
    sing = payload.get("sing") if isinstance(payload.get("sing"), dict) else {}
    tts = payload.get("tts") if isinstance(payload.get("tts"), dict) else {}
    if isinstance(sing.get("default_speaker"), str) and sing["default_speaker"].strip():
        merged["sing"]["default_speaker"] = sing["default_speaker"].strip()
    if isinstance(sing.get("preferred_backend"), str):
        merged["sing"]["preferred_backend"] = sing["preferred_backend"].strip()
    for key in _DEFAULT_TTS:
        val = tts.get(key)
        if isinstance(val, str) and val.strip():
            merged["tts"][key] = val.strip()
    with _LOCK:
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged


def defaults_writable(root: Path | None = None) -> bool:
    """源码可写；Docker 若 data/ 可写也允许改默认（不删镜像权重）。"""
    mode = detect_deploy_mode(root)
    if mode == "source":
        return True
    base = repo_root(root)
    data = base / "data"
    try:
        data.mkdir(parents=True, exist_ok=True)
        probe = data / ".pallas_media_models_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def get_svc_registry():
    """懒加载，避免与 sing.svc_inference ↔ media_models 循环导入。"""
    try:
        from app.tasks.sing.svc_registry import get_registry  # noqa: PLC0415
    except ImportError:
        return None
    try:
        return get_registry()
    except Exception as exc:
        logger.debug("svc registry unavailable: {}", exc)
        return None


def list_sing_speakers(root: Path | None = None) -> dict[str, Any]:
    base = repo_root(root)
    models_root = (base / settings.svc_models_root).resolve()
    speakers: list[dict[str, Any]] = []
    registry = get_svc_registry()

    if models_root.is_dir():
        for child in sorted(models_root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            # pretrain 是公共权重，不是说话人
            if child.name == "pretrain":
                continue
            backends: list[str] = []
            model_files: list[str] = []
            ready = False
            if registry is not None:
                try:
                    compatible = registry.compatible_backends(child)
                    backends = [b.name for b in compatible]
                    model_files.extend(
                        match.name
                        for backend in compatible
                        for match in sorted(child.glob(backend.model_glob))
                        if match.is_file()
                    )
                    # 多 backend 可能命中同一文件
                    model_files = list(dict.fromkeys(model_files))
                    ready = bool(compatible)
                except Exception:
                    ready = False
            if not model_files:
                for pattern in ("*.pt", "*.pth", "G_*.pth"):
                    for match in sorted(child.glob(pattern)):
                        if match.is_file() and match.name not in model_files:
                            model_files.append(match.name)
                if not ready:
                    ready = bool(model_files) or (child / ".extracted").is_file()
            speakers.append({
                "id": child.name,
                "path": str(child.relative_to(base)).replace("\\", "/"),
                "backends": backends,
                "model_files": model_files,
                "ready": ready,
            })

    cfg = load_media_models(base)
    return {
        "speakers": speakers,
        "default_speaker": str(cfg["sing"]["default_speaker"]),
        "preferred_backend": str(cfg["sing"].get("preferred_backend") or ""),
        "sing_speakers_map": dict(settings.sing_speakers or {}),
        "writable": defaults_writable(base),
        "deploy_mode": detect_deploy_mode(base),
    }


def list_svc_backends(root: Path | None = None) -> dict[str, Any]:
    """列出 registry 中的 SVC backend，以及当前 preferred。"""
    base = repo_root(root)
    cfg = load_media_models(base)
    preferred = str(cfg["sing"].get("preferred_backend") or "")
    backends: list[dict[str, Any]] = []
    fallback_order: list[str] = []
    registry = get_svc_registry()
    if registry is not None:
        try:
            fallback_order = list(registry.fallback_order)
            for name in fallback_order:
                backend = registry.backends.get(name)
                if backend is None:
                    continue
                backends.append({
                    "id": name,
                    "arg_style": getattr(backend.arg_style, "value", str(backend.arg_style)),
                    "model_glob": backend.model_glob,
                    "enabled": bool(backend.enabled),
                    "output_suffix": backend.output_suffix,
                })
            for name, backend in registry.backends.items():
                if name in {b["id"] for b in backends}:
                    continue
                backends.append({
                    "id": name,
                    "arg_style": getattr(backend.arg_style, "value", str(backend.arg_style)),
                    "model_glob": backend.model_glob,
                    "enabled": bool(backend.enabled),
                    "output_suffix": backend.output_suffix,
                })
        except Exception as exc:
            logger.debug("list_svc_backends: registry unavailable: {}", exc)
    return {
        "backends": backends,
        "fallback_order": fallback_order,
        "preferred_backend": preferred,
        "writable": defaults_writable(base),
        "deploy_mode": detect_deploy_mode(base),
    }


def get_sing_defaults(root: Path | None = None) -> dict[str, Any]:
    base = repo_root(root)
    cfg = load_media_models(base)
    return {
        "default_speaker": cfg["sing"]["default_speaker"],
        "preferred_backend": str(cfg["sing"].get("preferred_backend") or ""),
        "writable": defaults_writable(base),
    }


def set_sing_defaults(
    *,
    default_speaker: str | None = None,
    preferred_backend: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    base = repo_root(root)
    if not defaults_writable(base):
        raise PermissionError("当前部署不可写入唱歌默认配置")
    if default_speaker is None and preferred_backend is None:
        raise ValueError("至少提供 default_speaker 或 preferred_backend")

    cfg = load_media_models(base)

    if default_speaker is not None:
        speaker = default_speaker.strip()
        if not speaker:
            raise ValueError("default_speaker 不能为空")
        inventory = list_sing_speakers(base)
        known = {row["id"] for row in inventory["speakers"]}
        if known and speaker not in known:
            raise ValueError(f"未知说话人: {speaker}")
        cfg["sing"]["default_speaker"] = speaker

    if preferred_backend is not None:
        backend = preferred_backend.strip()
        if backend:
            catalog = list_svc_backends(base)
            known_backends = {row["id"] for row in catalog["backends"]}
            if known_backends and backend not in known_backends:
                raise ValueError(f"未知 SVC backend: {backend}")
            enabled = next(
                (row for row in catalog["backends"] if row["id"] == backend),
                None,
            )
            if enabled is not None and not enabled.get("enabled", True):
                raise ValueError(f"backend 已禁用: {backend}")
        cfg["sing"]["preferred_backend"] = backend

    save_media_models(cfg, root=base)
    return get_sing_defaults(base)


def resolve_sing_speaker(speaker: str | None = None, *, root: Path | None = None) -> str:
    raw = (speaker or "").strip()
    if raw:
        return raw
    return str(load_media_models(root)["sing"]["default_speaker"] or "pallas")


def resolve_preferred_backend(*, root: Path | None = None) -> str:
    return str(load_media_models(root)["sing"].get("preferred_backend") or "").strip()


def order_backends_by_preference(candidates: list[Any], preferred: str) -> list[Any]:
    """把 preferred backend 提到队首，其余保持原顺序；找不到则原样返回。"""
    name = (preferred or "").strip()
    if not name or not candidates:
        return list(candidates)
    head = [b for b in candidates if getattr(b, "name", None) == name]
    if not head:
        return list(candidates)
    tail = [b for b in candidates if getattr(b, "name", None) != name]
    return head + tail


def list_tts_voices(root: Path | None = None) -> dict[str, Any]:
    base = repo_root(root)
    ref_dir = base / "resource" / "tts" / "ref_audio"
    voices: list[dict[str, Any]] = []
    if ref_dir.is_dir():
        for path in sorted(ref_dir.iterdir(), key=lambda p: p.name.lower()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".wav", ".mp3", ".flac", ".ogg"}:
                continue
            rel = str(path.relative_to(base)).replace("\\", "/")
            voices.append({
                "id": path.stem,
                "path": rel,
                "name": path.name,
                "size_bytes": path.stat().st_size,
            })
    cfg = load_media_models(base)
    return {
        "voices": voices,
        "defaults": dict(cfg["tts"]),
        "writable": defaults_writable(base),
        "deploy_mode": detect_deploy_mode(base),
    }


def get_tts_defaults(root: Path | None = None) -> dict[str, Any]:
    base = repo_root(root)
    cfg = load_media_models(base)
    return {
        **dict(cfg["tts"]),
        "writable": defaults_writable(base),
    }


def set_tts_defaults(
    *,
    ref_audio_path: str | None = None,
    prompt_text: str | None = None,
    prompt_lang: str | None = None,
    text_lang: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    base = repo_root(root)
    if not defaults_writable(base):
        raise PermissionError("当前部署不可写入 TTS 默认配置")
    cfg = load_media_models(base)
    tts = dict(cfg["tts"])
    if ref_audio_path is not None:
        path = (ref_audio_path or "").strip().replace("\\", "/")
        if not path:
            raise ValueError("ref_audio_path 不能为空")
        abs_path = (base / path).resolve()
        if not str(abs_path).startswith(str(base.resolve())):
            raise ValueError("ref_audio_path 非法")
        if not abs_path.is_file():
            raise ValueError(f"参考音频不存在: {path}")
        tts["ref_audio_path"] = str(abs_path.relative_to(base)).replace("\\", "/")
    if prompt_text is not None:
        tts["prompt_text"] = str(prompt_text)
    if prompt_lang is not None and str(prompt_lang).strip():
        tts["prompt_lang"] = str(prompt_lang).strip()
    if text_lang is not None and str(text_lang).strip():
        tts["text_lang"] = str(text_lang).strip()
    cfg["tts"] = tts
    save_media_models(cfg, root=base)
    return get_tts_defaults(base)


def resolve_tts_request(
    *,
    text: str,
    media_type: str = "wav",
    root: Path | None = None,
) -> dict[str, Any]:
    """构造 GPT-SoVITS tts_handle 请求，读 media_models 默认音色。"""
    base = repo_root(root)
    cfg = load_media_models(base)["tts"]
    ref = str(cfg.get("ref_audio_path") or _DEFAULT_TTS["ref_audio_path"])
    abs_ref = base / ref
    text_lang = str(cfg.get("text_lang") or "zh")
    if settings.translator_enable:
        text_lang = "ja"
    return {
        "text": text,
        "text_lang": text_lang,
        "ref_audio_path": str(abs_ref) if abs_ref.exists() else ref,
        "prompt_text": str(cfg.get("prompt_text") or _DEFAULT_TTS["prompt_text"]),
        "prompt_lang": str(cfg.get("prompt_lang") or _DEFAULT_TTS["prompt_lang"]),
        "media_type": media_type,
        "streaming_mode": False,
        "return_fragment": False,
    }
