import httpx

from app.core.config import settings
from app.core.logger import log_id_suffix, logger, task_log
from app.utils.retry import async_retry

CALLBACK_URL = f"http://{settings.callback_host}:{settings.callback_port}/callback"


def should_retry_callback(exc: BaseException) -> bool:
    # ReadTimeout：请求体多半已送达，Bot 可能仍在发语音；再重试会重复投递。
    if isinstance(exc, httpx.ReadTimeout):
        logger.warning(
            "callback ReadTimeout, skip retry to avoid duplicate delivery: {}",
            exc,
        )
        return False
    return not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500


def resolve_callback_timeout(*, use_file_timeout: bool) -> int:
    """显式选择回调超时：带文件投递用 callback_file_timeout，否则用 callback_timeout。"""
    if use_file_timeout:
        return settings.callback_file_timeout
    return settings.callback_timeout


@async_retry(
    max_attempts=settings.callback_max_retries,
    delay=3,
    retry_filter=should_retry_callback,
)
async def send_callback(
    url: str,
    data: dict,
    files: dict = None,
    *,
    use_file_timeout: bool = False,
):
    timeout = resolve_callback_timeout(use_file_timeout=use_file_timeout)
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data, files=files, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


async def callback(
    request_id: str,
    status: str = "success",
    text: str = None,
    audio: bytes = None,
    song_id: str = None,
    chunk_index: int = None,
    key: int = None,
    history_summary: str | None = None,
    history_keep_messages: int | None = None,
    agent_trace: str | None = None,
):
    callback_url = f"{CALLBACK_URL}/{request_id}"

    data = {"status": status}
    task_log(
        (
            "preparing bot callback{} status={} has_text={} has_audio={} song_id={} chunk_index={} "
            "key={} history_summary={} history_keep_messages={} agent_trace={}"
        ),
        log_id_suffix(request_id, label="request_id"),
        status,
        bool(text),
        audio is not None,
        song_id,
        chunk_index,
        key,
        bool(history_summary),
        history_keep_messages,
        bool(agent_trace),
    )

    if status == "failed":
        try:
            result = await send_callback(callback_url, data, use_file_timeout=False)
            task_log(
                "bot callback completed{} status=failed result={}",
                log_id_suffix(request_id, label="request_id"),
                result,
            )
        except httpx.HTTPStatusError as err:
            logger.warning(
                "bot callback failed{} http={} url={}",
                log_id_suffix(request_id, label="request_id"),
                err.response.status_code,
                callback_url,
            )
        except Exception as exc:
            logger.exception(
                "bot callback error{} status=failed url={} error={}",
                log_id_suffix(request_id, label="request_id"),
                callback_url,
                exc,
            )
        return

    if text:
        data["text"] = text
    if song_id:
        data["song_id"] = song_id
    if chunk_index is not None:
        data["chunk_index"] = chunk_index
    if key is not None:
        data["key"] = key
    if history_summary:
        data["history_summary"] = history_summary
    if history_keep_messages is not None:
        data["history_keep_messages"] = str(int(history_keep_messages))
    if agent_trace:
        data["agent_trace"] = agent_trace

    try:
        if audio:
            result = await send_callback(
                callback_url,
                data,
                files={"file": audio},
                use_file_timeout=True,
            )
        else:
            result = await send_callback(callback_url, data, use_file_timeout=False)
        task_log(
            "bot callback completed{} status={} result={}",
            log_id_suffix(request_id, label="request_id"),
            status,
            result,
        )
    except httpx.HTTPStatusError as err:
        logger.warning(
            "bot callback failed{} http={} url={}",
            log_id_suffix(request_id, label="request_id"),
            err.response.status_code,
            callback_url,
        )
    except Exception as exc:
        logger.exception(
            "bot callback error{} status={} url={} error={}",
            log_id_suffix(request_id, label="request_id"),
            status,
            callback_url,
            exc,
        )
