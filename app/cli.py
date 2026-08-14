from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from app.version import VERSION

_LIFECYCLE_COMMANDS = ("start", "stop", "restart", "restart-clean", "status")
_TARGETS = ("api", "media", "fast", "all")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pallas-ai", description="Pallas AI 统一运维命令")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in _LIFECYCLE_COMMANDS:
        service_parser = commands.add_parser(command, help=f"{command} API 与 media/fast 服务")
        service_parser.add_argument("target", nargs="?", default="all", choices=_TARGETS)
    commands.add_parser("purge-stale", help="清理 Redis 中遗留的 Celery 任务状态")
    return parser


def ctl_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "ctl.sh"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = ["bash", str(ctl_script()), args.command]
    if args.command in _LIFECYCLE_COMMANDS:
        command.append(args.target)
    return subprocess.run(command, check=False).returncode
