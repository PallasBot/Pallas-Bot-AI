import contextlib

from app.core.redis import redis_client


class GPULockManager:
    def __init__(self, gpu_id: int, wait_timeout: int = 60, lock_timeout: int = 300):
        self.gpu_id = gpu_id
        self.lock_key = f"gpu_lock:{gpu_id}"
        self.wait_timeout = wait_timeout
        self.lock_timeout = lock_timeout

    @contextlib.contextmanager
    def acquire(self):
        lock = redis_client.lock(
            self.lock_key, timeout=self.lock_timeout, blocking=True, blocking_timeout=self.wait_timeout
        )
        acquired = lock.acquire()
        if not acquired:
            raise RuntimeError(f"GPU {self.gpu_id} wait timeout {self.wait_timeout}s")
        try:
            yield self.gpu_id
        finally:
            try:
                lock.release()
            except Exception:
                pass
