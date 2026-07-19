"""媒体权重（chat/sing/tts）就绪探测与源码侧下载任务。"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from app.core.celery import celery_task_package_enabled
from app.core.logger import logger

REPO_ROOT = Path(__file__).resolve().parents[1]

ASSET_SPECS: tuple[tuple[str, str, str], ...] = (
    ("chat", "resource/chat/models/.extracted", "resource/chat/models/models.zip"),
    (
        "sing_pallas",
        "resource/sing/models/pallas/.extracted",
        "resource/sing/models/pallas/pallas.zip",
    ),
    (
        "sing_pretrain",
        "resource/sing/models/pretrain/.extracted",
        "resource/sing/models/pretrain/pretrain.zip",
    ),
    ("tts", "resource/tts/.extracted", "resource/tts/tts.zip"),
)

_DEFAULT_URLS: dict[str, str] = {
    "resource/chat/models/models.zip": (
        "https://hf-mirror.com/pallasbot/Pallas-Bot/resolve/main/chat/models/models.zip"
    ),
    "resource/sing/models/pallas/pallas.zip": (
        "https://hf-mirror.com/pallasbot/Pallas-Bot/resolve/main/sing/models/pallas/pallas.zip"
    ),
    "resource/sing/models/pretrain/pretrain.zip": (
        "https://hf-mirror.com/pallasbot/Pallas-Bot/resolve/main/sing/models/pretrain/pretrain.zip"
    ),
    "resource/tts/tts.zip": ("https://hf-mirror.com/pallasbot/Pallas-Bot/resolve/main/tts/tts.zip"),
}

_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


@dataclass
class MediaAssetStatus:
    deploy_mode: str
    media_packages_enabled: dict[str, bool]
    assets: dict[str, dict[str, Any]]
    all_media_assets_ready: bool
    hints: list[str] = field(default_factory=list)
    download_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "deploy_mode": self.deploy_mode,
            "media_packages_enabled": self.media_packages_enabled,
            "assets": self.assets,
            "all_media_assets_ready": self.all_media_assets_ready,
            "hints": self.hints,
            "download_allowed": self.download_allowed,
        }


def repo_root(root: Path | None = None) -> Path:
    return root if root is not None else REPO_ROOT


def detect_deploy_mode(root: Path | None = None) -> str:
    forced = (os.environ.get("AI_DEPLOY_MODE") or "").strip().lower()
    if forced in {"source", "docker", "unknown"}:
        return forced
    if Path("/.dockerenv").is_file() or (os.environ.get("PALLAS_AI_IN_DOCKER") or "").strip() == "1":
        return "docker"
    base = repo_root(root)
    resource = base / "resource"
    try:
        resource.mkdir(parents=True, exist_ok=True)
        probe = resource / ".pallas_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        return "unknown"
    return "source"


def parse_models_txt(models_txt: Path) -> dict[str, str]:
    """解析 Docker/models.txt：url 行后跟 out=相对路径。"""
    if not models_txt.is_file():
        return dict(_DEFAULT_URLS)
    mapping: dict[str, str] = {}
    pending_url = ""
    for raw in models_txt.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("out="):
            out = line[4:].strip()
            if pending_url and out:
                mapping[out] = pending_url
            pending_url = ""
            continue
        if line.startswith(("http://", "https://")):
            pending_url = line
    for key, url in _DEFAULT_URLS.items():
        mapping.setdefault(key, url)
    return mapping


def media_packages_enabled() -> dict[str, bool]:
    return {
        "sing": celery_task_package_enabled("sing"),
        "tts": celery_task_package_enabled("tts"),
        "chat": celery_task_package_enabled("chat"),
    }


def asset_content_ready(asset_id: str, base: Path) -> bool:
    """按运行时实际依赖探测权重是否已落地（兼容老用户无 .extracted 的情况）。"""
    if asset_id == "chat":
        models = base / "resource/chat/models"
        return any(models.glob("*.pth")) and (models / "rwkv_vocab_v20230424.txt").is_file()
    if asset_id == "sing_pallas":
        return (base / "resource/sing/models/pallas/pallas.pt").is_file()
    if asset_id == "sing_pretrain":
        contentvec = base / "resource/sing/models/pretrain/contentvec"
        rmvpe = base / "resource/sing/models/pretrain/rmvpe/model.pt"
        return rmvpe.is_file() and (
            (contentvec / "checkpoint_best_legacy_500.pt").is_file() or any(contentvec.glob("*.pt"))
        )
    if asset_id == "tts":
        pm = base / "resource/tts/pretrained_models"
        if not pm.is_dir():
            return False
        return (
            (pm / "chinese-hubert-base").is_dir()
            or (pm / "s1v3.ckpt").is_file()
            or any(pm.rglob("*.pth"))
            or any(pm.rglob("*.ckpt"))
        )
    return False


def heal_extracted_markers(*, root: Path | None = None) -> list[str]:
    """内容已就绪但缺标记时补写 .extracted，避免升级后误报缺失或重复下载。"""
    base = repo_root(root)
    healed: list[str] = []
    for asset_id, marker_rel, _zip_rel in ASSET_SPECS:
        marker = base / marker_rel
        if marker.is_file():
            continue
        if not asset_content_ready(asset_id, base):
            continue
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except OSError as exc:
            logger.warning("media assets heal marker failed for {}: {}", asset_id, exc)
            continue
        healed.append(asset_id)
        logger.info("media assets healed marker for {} -> {}", asset_id, marker_rel)
    return healed


def asset_is_ready(asset_id: str, marker_rel: str, base: Path) -> bool:
    marker = base / marker_rel
    if marker.is_file():
        return True
    return asset_content_ready(asset_id, base)


def collect_asset_status(root: Path | None = None) -> MediaAssetStatus:
    base = repo_root(root)
    # 老用户升级：有权重无标记时先补标记，再汇总状态
    heal_extracted_markers(root=base)
    mode = detect_deploy_mode(base)
    packages = media_packages_enabled()
    assets: dict[str, dict[str, Any]] = {}
    hints: list[str] = []
    all_ready = True
    for asset_id, marker_rel, zip_rel in ASSET_SPECS:
        ready = asset_is_ready(asset_id, marker_rel, base)
        assets[asset_id] = {
            "ready": ready,
            "marker": marker_rel,
            "zip": zip_rel,
        }
        if not ready:
            all_ready = False
            hints.append(f"missing_{asset_id}")
    if not any(packages.values()):
        hints.append("media_packages_disabled")
    # source 模式已在 detect_deploy_mode 验证可写；docker/unknown 禁止 API 下载
    download_allowed = mode == "source"
    if mode == "docker":
        hints.append("docker_use_latest_image")
    elif not download_allowed and not all_ready:
        hints.append("download_not_allowed")
    return MediaAssetStatus(
        deploy_mode=mode,
        media_packages_enabled=packages,
        assets=assets,
        all_media_assets_ready=all_ready,
        hints=hints,
        download_allowed=download_allowed,
    )


def _extract_zip(zip_path: Path, target_dir: Path, marker: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)
    zip_path.unlink(missing_ok=True)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def download_and_extract_missing(*, root: Path | None = None, progress: list[str] | None = None) -> None:
    """同步下载并解压缺失资产（供脚本/job 调用）。"""
    base = repo_root(root)
    log = progress if progress is not None else []
    for asset_id in heal_extracted_markers(root=base):
        log.append(f"heal {asset_id}: content present, marker restored")
    urls = parse_models_txt(base / "Docker" / "models.txt")
    for asset_id, marker_rel, zip_rel in ASSET_SPECS:
        marker = base / marker_rel
        if asset_is_ready(asset_id, marker_rel, base):
            log.append(f"skip {asset_id}: already extracted")
            continue
        url = urls.get(zip_rel) or _DEFAULT_URLS.get(zip_rel)
        if not url:
            raise RuntimeError(f"无下载地址: {zip_rel}")
        zip_path = base / zip_rel
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        log.append(f"download {asset_id}: {url}")
        logger.info("media assets download {} from {}", asset_id, url)
        urlretrieve(url, zip_path)  # noqa: S310 — 官方镜像列表，运维可控
        log.append(f"extract {asset_id}")
        _extract_zip(zip_path, zip_path.parent, marker)
        log.append(f"ready {asset_id}")


def get_download_job(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def start_download_job(*, root: Path | None = None) -> dict[str, Any]:
    status = collect_asset_status(root)
    if not status.download_allowed:
        raise PermissionError(
            "当前部署不允许通过 API 下载媒体权重（Docker 请换 pallas-bot-ai:latest 并由启动脚本拉取）"
        )
    if status.all_media_assets_ready:
        job_id = uuid.uuid4().hex
        payload = {
            "job_id": job_id,
            "state": "done",
            "message": "媒体权重已就绪，无需下载",
            "lines": [],
            "error": "",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with _jobs_lock:
            _jobs[job_id] = payload
        return dict(payload)

    job_id = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "job_id": job_id,
        "state": "running",
        "message": "正在下载媒体权重…",
        "lines": [],
        "error": "",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    with _jobs_lock:
        _jobs[job_id] = payload

    base = repo_root(root)

    def worker() -> None:
        lines: list[str] = []
        try:
            script = base / "scripts" / "download_media_assets.sh"
            if script.is_file() and shutil.which("bash"):
                lines.append(f"run {script}")
                completed = subprocess.run(
                    ["bash", str(script)],
                    cwd=str(base),
                    check=False,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PALLAS_AI_ROOT": str(base)},
                )
                out = ((completed.stdout or "") + (completed.stderr or "")).strip()
                if out:
                    lines.extend(out.splitlines()[-80:])
                if completed.returncode != 0:
                    raise RuntimeError(out or f"download script exit {completed.returncode}")
            else:
                download_and_extract_missing(root=base, progress=lines)
            with _jobs_lock:
                job = _jobs[job_id]
                job["state"] = "done"
                job["message"] = "媒体权重下载完成"
                job["lines"] = lines[-120:]
                job["updated_at"] = time.time()
        except Exception as exc:
            logger.exception("media assets download failed: {}", exc)
            with _jobs_lock:
                job = _jobs[job_id]
                job["state"] = "failed"
                job["message"] = "媒体权重下载失败"
                job["error"] = str(exc)
                job["lines"] = lines[-120:]
                job["updated_at"] = time.time()

    threading.Thread(target=worker, name=f"media-assets-{job_id[:8]}", daemon=True).start()
    return dict(payload)
