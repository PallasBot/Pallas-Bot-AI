from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tomllib import loads

PACKAGE_NAME = "pallas-bot-ai"


def package_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        metadata = loads(pyproject.read_text(encoding="utf-8"))
        return str(metadata["project"]["version"])


VERSION = package_version()
