from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from app.core.logger import log_id_suffix, logger
from app.media_task_store import update_task_record
from app.services.callback import CALLBACK_URL, send_callback

if TYPE_CHECKING:
    from app.media_task_store import MediaTaskRecord


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
            log_id_suffix(request_id),
            exc,
        )
        return
    update_task_record(record.task_id, bot_callback_notified=True)


async def notify_image_media_task_result(record: MediaTaskRecord) -> None:
    if record.capability != "image.generate":
        return
    request_id = (record.request_id or "").strip()
    if not request_id:
        return
    callback_url = f"{CALLBACK_URL}/{request_id}"
    if record.state == "succeeded":
        data = record.data or {}
        raw_b64 = str(data.get("b64_data") or "").strip()
        if not raw_b64:
            try:
                await send_callback(callback_url, {"status": "failed"})
            except Exception as exc:
                logger.warning(
                    "image media task callback failed{}: {}",
                    log_id_suffix(request_id),
                    exc,
                )
            return
        try:
            image_bytes = base64.b64decode(raw_b64, validate=True)
        except (ValueError, TypeError):
            try:
                await send_callback(callback_url, {"status": "failed"})
            except Exception as exc:
                logger.warning(
                    "image media task callback failed{}: {}",
                    log_id_suffix(request_id),
                    exc,
                )
            return
        try:
            await send_callback(callback_url, {"status": "success"}, files={"file": image_bytes})
        except Exception as exc:
            logger.warning(
                "image media task callback failed{}: {}",
                log_id_suffix(request_id),
                exc,
            )
        return
    if record.state == "failed":
        try:
            await send_callback(callback_url, {"status": "failed"})
        except Exception as exc:
            logger.warning(
                "image media task callback failed{}: {}",
                log_id_suffix(request_id),
                exc,
            )
