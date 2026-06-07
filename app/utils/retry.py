import asyncio
from collections.abc import Callable
from functools import wraps


def async_retry(max_attempts=3, delay=1, retry_filter: Callable[[BaseException], bool] | None = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async def attempt_once(attempts: int):
                try:
                    return await func(*args, **kwargs)
                except BaseException as exc:
                    attempts += 1
                    should_retry = retry_filter(exc) if retry_filter is not None else True
                    if attempts == max_attempts or not should_retry:
                        raise
                    await asyncio.sleep(delay)
                    return await attempt_once(attempts)

            return await attempt_once(0)

        return wrapper

    return decorator
