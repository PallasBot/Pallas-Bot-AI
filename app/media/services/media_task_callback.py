from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logger import log_id_suffix, logger
from app.media.services.callback import CALLBACK_URL, send_callback
from app.media.store import update_task_record

if TYPE_CHECKING:
    from app.media.store import MediaTaskRecord


async def notify_sing_media_task_failed(record: MediaTaskRecord) -> None:
    if record.capability != "media.sing":
        return
    if record.bot_callback_notified:
        return
    request_id = (record.request_id or "").strip()
    if not request_id:
        return
    callback_url = f"{CALLBACK_URL}/{request_id}"
    try:
        await send_callback(callback_url, {"status": "failed"})
    except Exception as exc:
        logger.warning(
            "sing media task callback failed{}: {}",
            log_id_suffix(request_id, label="request_id"),
            exc,
        )
        return
    update_task_record(record.task_id, bot_callback_notified=True)
