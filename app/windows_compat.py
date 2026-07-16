"""Windows 下第三方 CUDA 扩展和 Python 3.10 的兼容处理。"""

from __future__ import annotations

import os
import platform
import site
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, MutableMapping, Sequence


def configure_windows_compatibility(
    *,
    env: MutableMapping[str, str] | None = None,
    site_packages: Iterable[Path] | None = None,
    argv: Sequence[str] | None = None,
    cwd: Path | None = None,
    system: str | None = None,
) -> bool:
    if (system or platform.system()) != "Windows":
        return False

    environment = env if env is not None else os.environ
    compiler_flags = environment.get("_CL_", "").split()
    if "/Zc:preprocessor" not in compiler_flags:
        compiler_flags.append("/Zc:preprocessor")
        environment["_CL_"] = " ".join(compiler_flags)

    command = " ".join(argv if argv is not None else sys.argv).lower()
    role = "celery" if "celery" in command else "api"
    root = cwd if cwd is not None else Path.cwd()
    environment.setdefault("TORCH_EXTENSIONS_DIR", str(root / ".torch_extensions" / role))

    for root in site_packages if site_packages is not None else _site_packages():
        _patch_pyncm_async(root / "pyncm_async" / "apis" / "cloud.py")
        _patch_rwkv(root / "rwkv" / "model.py")
    return True


def _site_packages() -> list[Path]:
    paths = {Path(path) for path in site.getsitepackages()}
    paths.add(Path(sys.prefix) / "Lib" / "site-packages")
    return list(paths)


def _patch_pyncm_async(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    fixed = text.replace('objectKey.replace("/", "%2F")', "objectKey.replace('/', '%2F')", 1)
    if fixed != text:
        path.write_text(fixed, encoding="utf-8")


def _patch_rwkv(path: Path) -> None:
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = False
    for index, line in enumerate(lines):
        if '"-Xptxas -O3"' not in line or "if os.name" in line:
            continue
        lines[index] = line.replace('"-Xptxas -O3"', '"-Xptxas", "-O3"')
        changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
