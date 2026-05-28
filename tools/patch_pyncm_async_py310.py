"""修复 pyncm-async 1.8.2 在 Python 3.10 下 cloud.py 的 f-string 语法错误。"""

from __future__ import annotations

import sys
from pathlib import Path


def patch_cloud_py(site_packages: Path) -> bool:
    cloud_py = site_packages / "pyncm_async" / "apis" / "cloud.py"
    if not cloud_py.is_file():
        print(f"skip: {cloud_py} not found", file=sys.stderr)
        return False

    text = cloud_py.read_text(encoding="utf-8")
    broken = 'objectKey.replace("/", "%2F")'
    fixed = "objectKey.replace('/', '%2F')"
    if broken not in text:
        if fixed in text:
            return True
        print(f"skip: pattern not found in {cloud_py}", file=sys.stderr)
        return False

    cloud_py.write_text(text.replace(broken, fixed, 1), encoding="utf-8")
    print(f"patched {cloud_py}")
    return True


def main() -> int:
    if len(sys.argv) > 1:
        roots = [Path(p) for p in sys.argv[1:]]
    else:
        ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        roots = [Path(sys.prefix) / "lib" / f"python{ver}" / "site-packages"]

    ok = False
    for root in roots:
        if patch_cloud_py(root):
            ok = True
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
