import asyncio

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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_ollama_chat_async(request_id, session, text, system_prompt, model))
    finally:
        loop.close()


async def _ollama_chat_async(
    request_id: str,
    session: str,
    text: str,
    system_prompt: str,
    model: str | None,
):
    if not settings.ollama_enable:
        await callback(request_id, status="failed")
        return

    active_model = (model or "").strip() or get_ollama_model()

    max_messages = 2 * settings.ollama_max_histories
    if message_count(session) >= max_messages:
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
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(ollama_chat_url(), json=payload)
                if response.status_code == 200:
                    data = response.json()
                    message_obj = data.get("message", {})
                    reply = str(message_obj.get("content", "")).strip()
                    if reply:
                        messages.append(message_obj)
                        await callback(request_id, text=reply)
                    else:
                        logger.warning("ollama returned empty content, session={}", session)
                        await callback(request_id, status="failed")
                    return

                last_status = response.status_code
                last_body = response.text
                logger.error(
                    "ollama request failed: status={}, body={}, attempt={}/{}",
                    response.status_code,
                    last_body,
                    attempt,
                    max_attempts,
                )
        except httpx.TimeoutException:
            logger.error(
                "ollama request timeout: {}s, session={}, attempt={}/{}",
                settings.ollama_request_timeout,
                session,
                attempt,
                max_attempts,
            )
        except Exception as e:
            logger.exception("ollama request exception: {}, attempt={}/{}", e, attempt, max_attempts)

        if attempt < max_attempts:
            await asyncio.sleep(settings.ollama_retry_backoff)

    logger.debug(
        "ollama retries exhausted last_status={}, last_body_len={}",
        last_status,
        len(last_body),
    )
    await callback(request_id, status="failed")


async def ollama_unload(model: str | None = None) -> tuple[int, str]:
    payload = {
        "model": (model or "").strip() or get_ollama_model(),
        "messages": [],
        "keep_alive": 0,
    }
    timeout = httpx.Timeout(settings.ollama_request_timeout)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(ollama_chat_url(), json=payload)
        return response.status_code, response.text


def ollama_del_session(session: str) -> None:
    del_session(session)
