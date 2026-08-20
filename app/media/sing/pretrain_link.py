"""为上游 DDSP 默认路径 ``pretrain/...`` 提供仓根兼容链接。

官方 pallas 的 config 已写成 ``resource/sing/models/pretrain/...``；
用户自训 / 社区权重常仍写 ``pretrain/nsf_hifigan``、且 DDSP-SVC 6.3
分支里 rmvpe 仍硬编码 ``pretrain/rmvpe/model.pt``。
推理 cwd 是 AI Runtime 根目录，在此确保 ``./pretrain`` 指向真实权重目录。
"""

from __future__ import annotations

import platform
import subprocess
from typing import TYPE_CHECKING

from app.core.logger import logger
from app.media.assets import repo_root

if TYPE_CHECKING:
    from pathlib import Path

_REL_TARGET = "resource/sing/models/pretrain"


def ensure_sing_pretrain_cwd_link(root: Path | None = None) -> bool:
    """确保仓根 ``pretrain`` → ``resource/sing/models/pretrain``。成功或已就绪返回 True。"""
    base = repo_root(root)
    target = (base / _REL_TARGET).resolve()
    link = base / "pretrain"

    if not target.is_dir():
        logger.warning(
            "sing pretrain dir missing, cannot create compat link: {}",
            target,
        )
        return False

    if _points_to_target(link, target) or _usable_pretrain_dir(link):
        return True

    if link.exists() or link.is_symlink():
        if not _try_remove_link(link):
            logger.warning(
                "repo root already has an irreplaceable pretrain/ not pointing at {}; "
                "change config manually or delete it before restart",
                target,
            )
            return False

    try:
        link.symlink_to(target, target_is_directory=True)
        logger.info("created pretrain symlink: {} -> {}", link, target)
        return True
    except OSError as exc:
        if platform.system() != "Windows":
            logger.warning("failed to create pretrain symlink: {}", exc)
            return False

    # Windows 无管理员/开发者模式时 symlink 常失败，改用目录联接（无需提权）
    try:
        result = subprocess.run(  # noqa: S603
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        logger.warning("failed to create pretrain junction: {}", exc)
        return False
    if result.returncode != 0 or not (_points_to_target(link, target) or _usable_pretrain_dir(link)):
        logger.warning(
            "failed to create pretrain junction rc={} stderr={}",
            result.returncode,
            (result.stderr or result.stdout or "").strip()[-300:],
        )
        return False
    logger.info("created pretrain junction: {} -> {}", link, target)
    return True


def _usable_pretrain_dir(path: Path) -> bool:
    return path.is_dir() and (path / "nsf_hifigan" / "config.json").is_file()


def _points_to_target(link: Path, target: Path) -> bool:
    if not (link.exists() or link.is_symlink()):
        return False
    try:
        return link.resolve() == target
    except OSError:
        return False


def _try_remove_link(path: Path) -> bool:
    """移除符号链接 / Windows 目录联接；真实非空目录则拒绝删除。"""
    try:
        if path.is_symlink():
            path.unlink()
            return True
        if path.is_dir():
            # 空目录或联接：unlink；有内容的普通目录不动
            try:
                next(path.iterdir())
            except StopIteration:
                path.rmdir()
                return True
            # Windows junction：看起来像目录，unlink 可删联接本身
            if platform.system() == "Windows":
                path.unlink()
                return True
            return False
        path.unlink()
        return True
    except OSError:
        return False
