import asyncio
from functools import wraps


def async_retry(max_attempts=3, delay=1):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return await func(*args, **kwargs)
                except BaseException:
                    attempts += 1
                    if attempts == max_attempts:
                        raise
                    await asyncio.sleep(delay)

        return wrapper

    return decorator
