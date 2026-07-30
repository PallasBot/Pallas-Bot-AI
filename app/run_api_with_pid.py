"""Write native ``os.getpid()`` then start the API.

Git Bash ``echo $!`` often records an MSYS pseudo-PID that Bot's Win32
``OpenProcess`` / ``os.kill`` cannot see, while HTTP ``/health`` still works.
Celery already writes a real Windows PID via ``--pidfile``; API needs the same.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m app.run_api_with_pid <pidfile>", file=sys.stderr)
        raise SystemExit(2)
    pidfile = Path(args[0])
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    pidfile.write_text(f"{os.getpid()}\n", encoding="utf-8")
    runpy.run_module("app.run_api", run_name="__main__")


if __name__ == "__main__":
    main()
