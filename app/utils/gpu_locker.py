import asyncio
import contextlib
import threading
import time
import uuid

from app.core.logger import logger
from app.core.redis import redis_client


class GPULockTimeoutError(RuntimeError):
    """等待 GPU 锁超时。"""


class GPUHoldTimeoutError(RuntimeError):
    """持有 GPU 锁的执行超过硬上限，看门狗已强制释放。"""


class GPULockManager:
    """GPU 读写锁。

    单卡显存装不下 LLM 推理与媒体任务（demucs/SVC/TTS）同时上卡，但二者需求不同：
    - LLM 推理高频、短时，ollama 服务端自身会排队，彼此**无需**互斥 → 读锁（共享）。
    - 媒体任务低频、长时、独占显存 → 写锁（排他）。

    规则：读者之间并发；写者排他，且与任何读者互斥。写优先——有写者在场时新读者
    让路并等待，避免持续的 LLM 流量把媒体任务饿死。

    防卡死同旧版：短 TTL + 看门狗续租（进程崩溃后自动过期），写者持锁超 ``max_hold``
    秒看门狗强制释放并在退出时抛 GPUHoldTimeoutError（防 CUDA hang 永久占卡）。
    """

    def __init__(
        self,
        gpu_id: int,
        wait_timeout: int = 60,
        lease_ttl: int = 60,
        max_hold: int = 1800,
        renew_interval: float | None = None,
    ):
        self.gpu_id = gpu_id
        self.write_key = f"gpu_lock:{gpu_id}"
        self.reader_prefix = f"gpu_reader:{gpu_id}:"
        self.wait_timeout = wait_timeout
        self.lease_ttl = lease_ttl
        self.max_hold = max_hold
        # 续租周期默认取租约的 1/3，保证至少续两次才会过期。
        self.renew_interval = renew_interval if renew_interval is not None else max(1.0, lease_ttl / 3)

    # ── 写锁（媒体任务，排他）───────────────────────────────────────────
    @contextlib.contextmanager
    def acquire_write(self, unload_llm: bool = False):
        lock = redis_client.lock(
            self.write_key,
            timeout=self.lease_ttl,
            blocking=True,
            blocking_timeout=self.wait_timeout,
            # token 存锁实例而非 threading.local：看门狗在独立线程续租，
            # thread_local=True 会让续租线程读不到 token；每次新建独立 lock，关闭是安全的。
            thread_local=False,
        )
        if not lock.acquire():
            raise GPULockTimeoutError(f"GPU {self.gpu_id} write wait timeout {self.wait_timeout}s")

        # 已占住写锁（挡住新读者），再等在途读者（LLM）全部退出。
        try:
            self._wait_readers_drain()
        except GPULockTimeoutError:
            _safe_release(lock)
            raise

        if unload_llm:
            # 媒体任务上卡前卸下 ollama 常驻模型，腾显存给 demucs/SVC/TTS。释放后 LLM 自动重载。
            _unload_resident_llm()

        stop = threading.Event()
        hold_exceeded = threading.Event()
        started = time.monotonic()

        def _watchdog() -> None:
            while not stop.wait(self.renew_interval):
                if time.monotonic() - started >= self.max_hold:
                    logger.error(
                        "GPU {} 写锁持有超过硬上限 {}s，看门狗强制释放",
                        self.gpu_id,
                        self.max_hold,
                    )
                    hold_exceeded.set()
                    _safe_release(lock)
                    return
                try:
                    lock.extend(self.lease_ttl, replace_ttl=True)
                except Exception as exc:
                    logger.warning("GPU {} 写锁续租失败：{}", self.gpu_id, exc)

        watcher = threading.Thread(target=_watchdog, name=f"gpu-wlock-{self.gpu_id}", daemon=True)
        watcher.start()
        try:
            yield self.gpu_id
        finally:
            stop.set()
            watcher.join(timeout=self.renew_interval + 1)
            _safe_release(lock)
            if hold_exceeded.is_set():
                raise GPUHoldTimeoutError(f"GPU {self.gpu_id} write hold exceeded {self.max_hold}s")

    # 兼容旧调用：acquire == 写锁（媒体任务历史用法 with locker.acquire(...)）
    acquire = acquire_write

    # ── 读锁（LLM 推理，共享）───────────────────────────────────────────
    @contextlib.contextmanager
    def acquire_read(self):
        reader_key = f"{self.reader_prefix}{uuid.uuid4().hex}"
        deadline = time.monotonic() + self.wait_timeout
        while True:
            # 有写者在场 → 让路等待。
            if redis_client.exists(self.write_key):
                if time.monotonic() >= deadline:
                    raise GPULockTimeoutError(f"GPU {self.gpu_id} read wait timeout {self.wait_timeout}s")
                time.sleep(0.2)
                continue
            # 乐观登记读者，再复查写者：写者若在登记瞬间出现，撤销并重试（写优先）。
            redis_client.set(reader_key, "1", ex=self.lease_ttl)
            if redis_client.exists(self.write_key):
                redis_client.delete(reader_key)
                if time.monotonic() >= deadline:
                    raise GPULockTimeoutError(f"GPU {self.gpu_id} read wait timeout {self.wait_timeout}s")
                time.sleep(0.2)
                continue
            break

        stop = threading.Event()

        def _watchdog() -> None:
            while not stop.wait(self.renew_interval):
                try:
                    redis_client.expire(reader_key, self.lease_ttl)
                except Exception as exc:
                    logger.warning("GPU {} 读锁续租失败：{}", self.gpu_id, exc)

        watcher = threading.Thread(target=_watchdog, name=f"gpu-rlock-{self.gpu_id}", daemon=True)
        watcher.start()
        try:
            yield self.gpu_id
        finally:
            stop.set()
            watcher.join(timeout=self.renew_interval + 1)
            try:
                redis_client.delete(reader_key)
            except Exception:
                pass

    def _wait_readers_drain(self) -> None:
        deadline = time.monotonic() + self.wait_timeout
        while True:
            if not self._active_reader_count():
                return
            if time.monotonic() >= deadline:
                raise GPULockTimeoutError(f"GPU {self.gpu_id} readers drain timeout {self.wait_timeout}s")
            time.sleep(0.2)

    def _active_reader_count(self) -> int:
        count = 0
        for _ in redis_client.scan_iter(match=f"{self.reader_prefix}*", count=100):
            count += 1
        return count


def _safe_release(lock) -> None:
    try:
        lock.release()
    except Exception:
        # 锁可能已过期/已被看门狗释放，忽略即可。
        pass


def _unload_resident_llm() -> None:
    from app.core.config import settings

    if not settings.llm_chat_enabled:
        return
    try:
        from app.core.llm_backend_runtime import unload_resident_backend_model_sync

        status, _ = unload_resident_backend_model_sync()
        logger.info("媒体任务上卡前卸载 LLM 常驻模型 status={}", status)
    except Exception as exc:
        # 卸载失败不阻断媒体任务，最坏情况退化为旧的共卡行为。
        logger.warning("卸载 LLM 常驻模型失败：{}", exc)


_shared_locks: dict[int, GPULockManager] = {}


def get_gpu_locker(gpu_id: int | None = None) -> GPULockManager:
    """返回按配置构造的共享 GPU 读写锁（同一 gpu_id 复用同一实例）。"""
    from app.core.config import settings

    gid = settings.sing_cuda_device if gpu_id is None else gpu_id
    locker = _shared_locks.get(gid)
    if locker is None:
        locker = GPULockManager(
            gid,
            wait_timeout=settings.gpu_lock_wait_timeout,
            lease_ttl=settings.gpu_lock_lease_ttl,
            max_hold=settings.gpu_lock_max_hold,
        )
        _shared_locks[gid] = locker
    return locker


@contextlib.asynccontextmanager
async def acquire_gpu_read_async(gpu_id: int | None = None):
    """async 场景下获取 GPU 读锁（LLM 推理用）。

    读锁的等待/登记是同步 redis 调用，直接在协程里执行会卡住事件循环，
    故 enter/exit 都丢到线程里。读者之间并发，仅与媒体写者互斥。
    """
    locker = get_gpu_locker(gpu_id)
    cm = locker.acquire_read()
    await asyncio.to_thread(cm.__enter__)
    try:
        yield locker.gpu_id
    finally:
        await asyncio.to_thread(cm.__exit__, None, None, None)
