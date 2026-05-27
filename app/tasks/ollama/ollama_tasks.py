import asyncio
import time

import httpx

from app.core.celery import celery_app
from app.core.config import settings
from app.core.logger import logger
from app.core.ollama_runtime import get_ollama_model, ollama_chat_url
from app.services.callback import callback

from .session import del_session, get_messages, message_count, reset_session

OLLAMA_HISTORY_RESET_REPLY = "等等，刚才说到哪儿来着？我脑子里有点断片……"


@celery_app.task(name="ollama_chat")
def ollama_chat_task(request_id: str, session: str, text: str, system_prompt: str, model: str | None = None):
    logger.info(
        "ollama chat task received: request_id={} session={} text_len={}",
        request_id,
        session,
        len(text or ""),
    )
    started = time.monotonic()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_ollama_chat_async(request_id, session, text, system_prompt, model))
    finally:
        logger.info(
            "ollama chat task finished: request_id={} elapsed={:.2f}s",
            request_id,
            time.monotonic() - started,
        )
        loop.close()


async def _ollama_chat_async(
    request_id: str,
    session: str,
    text: str,
    system_prompt: str,
    model: str | None,
):
    if not settings.ollama_enable:
        logger.warning("ollama chat skipped: backend disabled, request_id={}", request_id)
        await callback(request_id, status="failed")
        return

    active_model = (model or "").strip() or get_ollama_model()
    history_count = message_count(session)
    logger.info(
        "ollama chat start: request_id={} session={} model={} history_msgs={} num_gpu={}",
        request_id,
        session,
        active_model,
        history_count,
        settings.ollama_num_gpu,
    )

    max_messages = 2 * settings.ollama_max_histories
    if history_count >= max_messages:
        reset_session(session, system_prompt)
        logger.warning("ollama histories exceeded, reset session: {}", session)
        await callback(request_id, text=OLLAMA_HISTORY_RESET_REPLY)
        return

    messages = get_messages(session, system_prompt)
    messages.append({"role": "user", "content": text})

    options: dict[str, float | int] = {"temperature": settings.ollama_temperature}
    if settings.ollama_num_gpu is not None:
        options["num_gpu"] = settings.ollama_num_gpu

    payload = {
        "model": active_model,
        "messages": messages,
        "stream": False,
        "options": options,
    }

    timeout = httpx.Timeout(settings.ollama_request_timeout)
    max_attempts = settings.ollama_max_retries + 1
    last_status = 0
    last_body = ""

    for attempt in range(1, max_attempts + 1):
        try:
            logger.debug(
                "ollama post: request_id={} attempt={}/{} url={}",
                request_id,
                attempt,
                max_attempts,
                ollama_chat_url(),
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(ollama_chat_url(), json=payload)
                if response.status_code == 200:
                    data = response.json()
                    message_obj = data.get("message", {})
                    reply = str(message_obj.get("content", "")).strip()
                    if reply:
                        messages.append(message_obj)
                        logger.info(
                            "ollama chat ok: request_id={} reply_len={} session={}",
                            request_id,
                            len(reply),
                            session,
                        )
                        await callback(request_id, text=reply)
                    else:
                        logger.warning("ollama returned empty content, request_id={} session={}", request_id, session)
                        await callback(request_id, status="failed")
                    return

                last_status = response.status_code
                last_body = response.text
                logger.error(
                    "ollama request failed: request_id={} status={} body={} attempt={}/{}",
                    request_id,
                    response.status_code,
                    last_body[:500],
                    attempt,
                    max_attempts,
                )
        except httpx.TimeoutException:
            logger.error(
                "ollama request timeout: request_id={} timeout={}s session={} attempt={}/{}",
                request_id,
                settings.ollama_request_timeout,
                session,
                attempt,
                max_attempts,
            )
        except Exception as e:
            logger.exception(
                "ollama request exception: request_id={} err={} attempt={}/{}",
                request_id,
                e,
                attempt,
                max_attempts,
            )

        if attempt < max_attempts:
            await asyncio.sleep(settings.ollama_retry_backoff)

    logger.error(
        "ollama chat failed after retries: request_id={} last_status={} last_body_len={}",
        request_id,
        last_status,
        len(last_body),
    )
    await callback(request_id, status="failed")


async def ollama_unload(model: str | None = None) -> tuple[int, str]:
    target = (model or "").strip() or get_ollama_model()
    logger.info("ollama unload task: model={}", target)
    payload = {
        "model": target,
        "messages": [],
        "keep_alive": 0,
    }
    timeout = httpx.Timeout(settings.ollama_request_timeout)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(ollama_chat_url(), json=payload)
        return response.status_code, response.text


def ollama_del_session(session: str) -> None:
    logger.info("ollama del_session task: session={}", session)
    del_session(session)
