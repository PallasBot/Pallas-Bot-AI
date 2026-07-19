"""启动 FastAPI（uvicorn）。"""

from __future__ import annotations

import uvicorn

from app.core.config import settings


def parse_reload_dirs(raw: str) -> list[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def main() -> None:
    kwargs: dict = {
        "app": "app.main:app",
        "host": settings.uvicorn_host,
        "port": settings.uvicorn_port,
        "log_level": settings.server_log_level.lower(),
    }
    if settings.uvicorn_reload:
        kwargs["reload"] = True
        kwargs["reload_dirs"] = parse_reload_dirs(settings.uvicorn_reload_dirs)
    uvicorn.run(**kwargs)


if __name__ == "__main__":
    main()
