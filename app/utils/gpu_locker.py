import asyncio
import contextlib
import json
import os
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Mapping
from typing import Any

from app.core.logger import logger
from app.core.redis import redis_client


class GPULockTimeoutError(RuntimeError):
    """等待 GPU 锁超时。"""


class GPUHoldTimeoutError(RuntimeError):
    """持有 GPU 锁的执行超过硬上限，看门狗已强制释放。"""


class MediaSubprocessTimeoutError(RuntimeError):
    """媒体子进程执行超过单次硬超时，已被杀掉。"""


def _kill_process_tree(proc: subprocess.Popen, grace: float = 5.0) -> None:
    """杀掉子进程及其整个进程组（demucs 会 fork ffmpeg 等子进程）。

    先 SIGTERM 给进程组留 ``grace`` 秒清理，再 SIGKILL 兜底。子进程以
    ``start_new_session=True`` 启动，自成进程组，故可整组 kill 不误伤本进程。
    """
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        return
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, OSError):
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


class GPUWriteHandle:
    """写锁 yield 出的句柄：在持锁期间跑媒体子进程，超时即杀。

    旧调用方用 ``with locker.acquire(...):`` 不接收 yield 值，新调用方可
    ``with locker.acquire(...) as gpu:`` 拿到本句柄并调用 ``run_subprocess``。
    为兼容历史把 ``gpu_id`` 暴露为属性，``int(handle)`` 也回退到 gpu_id。
    """

    def __init__(self, gpu_id: int, subprocess_timeout: int):
        self.gpu_id = gpu_id
        self._subprocess_timeout = subprocess_timeout
        self._procs: set[subprocess.Popen] = set()
        self._lock = threading.Lock()

    def __int__(self) -> int:
        return self.gpu_id

    def __index__(self) -> int:
        return self.gpu_id

    def run_subprocess(self, cmd: str, timeout: int | None = None) -> int:
        """在持锁期间执行 shell 命令，带硬超时；超时杀进程组并抛异常。

        替代裸 ``os.system(cmd)``：os.system 无超时，子进程卡死会让写锁的
        with 块永久退不出，GPU 空着锁却占满 max_hold。这里超时即整组 kill，
        写锁随 with 退出立即释放，远早于看门狗硬上限。
        """
        limit = self._subprocess_timeout if timeout is None else timeout
        proc = subprocess.Popen(cmd, shell=True, start_new_session=True)
        with self._lock:
            self._procs.add(proc)
        try:
            return proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            logger.error("GPU {} 媒体子进程超过 {}s 硬超时，强制杀进程组", self.gpu_id, limit)
            _kill_process_tree(proc)
            raise MediaSubprocessTimeoutError(f"media subprocess timeout {limit}s") from None
        finally:
            with self._lock:
                self._procs.discard(proc)

    def _kill_all(self) -> None:
        """看门狗触发硬上限时调用：杀掉所有在跑的子进程，让 with 块尽快退出。"""
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            _kill_process_tree(proc)


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
        subprocess_timeout: int = 600,
    ):
        self.gpu_id = gpu_id
        self.write_key = f"gpu_lock:{gpu_id}"
        self.meta_key = f"gpu_lock_meta:{gpu_id}"
        self.reader_prefix = f"gpu_reader:{gpu_id}:"
        self.wait_timeout = wait_timeout
        self.lease_ttl = lease_ttl
        self.max_hold = max_hold
        self.subprocess_timeout = subprocess_timeout
        # 续租周期默认取租约的 1/3，保证至少续两次才会过期。
        self.renew_interval = renew_interval if renew_interval is not None else max(1.0, lease_ttl / 3)

    def _normalize_owner(self, owner: Mapping[str, Any] | None) -> dict[str, str]:
        if not isinstance(owner, Mapping):
            return {}
        out: dict[str, str] = {}
        for key, value in owner.items():
            name = str(key or "").strip()
            text = str(value or "").strip()
            if name and text:
                out[name] = text
        return out

    def _owner_text(self, owner: Mapping[str, Any] | None) -> str:
        normalized = self._normalize_owner(owner)
        if not normalized:
            return "unknown"
        preferred = ("kind", "request_id", "task_id", "step")
        parts: list[str] = []
        for key in preferred:
            value = normalized.pop(key, "")
            if value:
                parts.append(f"{key}={value}")
        for key in sorted(normalized):
            parts.append(f"{key}={normalized[key]}")
        return " ".join(parts) or "unknown"

    def _set_writer_meta(self, owner: Mapping[str, Any] | None, started: float) -> None:
        payload = dict(self._normalize_owner(owner))
        payload["started_at"] = f"{started:.6f}"
        try:
            redis_client.set(self.meta_key, json.dumps(payload, ensure_ascii=False), ex=self.lease_ttl)
        except Exception as exc:
            logger.warning("GPU {} 写锁元信息写入失败：{}", self.gpu_id, exc)

    def _refresh_writer_meta(self, owner: Mapping[str, Any] | None, started: float) -> None:
        payload = dict(self._normalize_owner(owner))
        payload["started_at"] = f"{started:.6f}"
        try:
            redis_client.set(self.meta_key, json.dumps(payload, ensure_ascii=False), ex=self.lease_ttl)
        except Exception as exc:
            logger.warning("GPU {} 写锁元信息续期失败：{}", self.gpu_id, exc)

    def _clear_writer_meta(self) -> None:
        try:
            redis_client.delete(self.meta_key)
        except Exception:
            pass

    def current_writer_owner_text(self) -> str:
        try:
            raw = redis_client.get(self.meta_key)
        except Exception:
            raw = None
        text = str(raw or "").strip()
        if not text:
            return "unknown"
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text
        if not isinstance(data, dict):
            return text
        data.pop("started_at", None)
        return self._owner_text(data)

    # ── 写锁（媒体任务，排他）───────────────────────────────────────────
    @contextlib.contextmanager
    def acquire_write(self, unload_llm: bool = False, owner: Mapping[str, Any] | None = None):
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
        handle = GPUWriteHandle(self.gpu_id, self.subprocess_timeout)
        owner_text = self._owner_text(owner)
        self._set_writer_meta(owner, started)
        logger.info("GPU {} 写锁已获取 owner={}", self.gpu_id, owner_text)

        def _watchdog() -> None:
            while not stop.wait(self.renew_interval):
                if time.monotonic() - started >= self.max_hold:
                    logger.error(
                        "GPU {} 写锁持有超过硬上限 {}s，看门狗强制释放并杀子进程 owner={}",
                        self.gpu_id,
                        self.max_hold,
                        owner_text,
                    )
                    hold_exceeded.set()
                    # 先杀子进程，让阻塞的 with 块（os 级命令）尽快退出，再放 redis 锁。
                    handle._kill_all()
                    self._clear_writer_meta()
                    _safe_release(lock)
                    return
                try:
                    lock.extend(self.lease_ttl, replace_ttl=True)
                    self._refresh_writer_meta(owner, started)
                except Exception as exc:
                    logger.warning("GPU {} 写锁续租失败：{}", self.gpu_id, exc)

        watcher = threading.Thread(target=_watchdog, name=f"gpu-wlock-{self.gpu_id}", daemon=True)
        watcher.start()
        try:
            yield handle
        finally:
            stop.set()
            watcher.join(timeout=self.renew_interval + 1)
            self._clear_writer_meta()
            _safe_release(lock)
            logger.info(
                "GPU {} 写锁已释放 owner={} hold_ms={}",
                self.gpu_id,
                owner_text,
                int((time.monotonic() - started) * 1000),
            )
            if hold_exceeded.is_set():
                raise GPUHoldTimeoutError(f"GPU {self.gpu_id} write hold exceeded {self.max_hold}s")

    # 兼容旧调用：acquire == 写锁（媒体任务历史用法 with locker.acquire(...)）
    acquire = acquire_write

    # ── 读锁（LLM 推理，共享）───────────────────────────────────────────
    @contextlib.contextmanager
    def acquire_read(self, owner: Mapping[str, Any] | None = None):
        reader_key = f"{self.reader_prefix}{uuid.uuid4().hex}"
        deadline = time.monotonic() + self.wait_timeout
        owner_text = self._owner_text(owner)
        while True:
            # 有写者在场 → 让路等待。
            if redis_client.exists(self.write_key):
                if time.monotonic() >= deadline:
                    logger.warning(
                        "GPU {} 读锁等待超时 owner={} current_writer={}",
                        self.gpu_id,
                        owner_text,
                        self.current_writer_owner_text(),
                    )
                    raise GPULockTimeoutError(f"GPU {self.gpu_id} read wait timeout {self.wait_timeout}s")
                time.sleep(0.2)
                continue
            # 乐观登记读者，再复查写者：写者若在登记瞬间出现，撤销并重试（写优先）。
            redis_client.set(reader_key, "1", ex=self.lease_ttl)
            if redis_client.exists(self.write_key):
                redis_client.delete(reader_key)
                if time.monotonic() >= deadline:
                    logger.warning(
                        "GPU {} 读锁等待超时 owner={} current_writer={}",
                        self.gpu_id,
                        owner_text,
                        self.current_writer_owner_text(),
                    )
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
            subprocess_timeout=settings.media_subprocess_timeout,
        )
        _shared_locks[gid] = locker
    return locker


@contextlib.asynccontextmanager
async def acquire_gpu_read_async(
    gpu_id: int | None = None,
    owner: Mapping[str, Any] | None = None,
):
    """async 场景下获取 GPU 读锁（LLM 推理用）。

    读锁的等待/登记是同步 redis 调用，直接在协程里执行会卡住事件循环，
    故 enter/exit 都丢到线程里。读者之间并发，仅与媒体写者互斥。
    """
    locker = get_gpu_locker(gpu_id)
    cm = locker.acquire_read(owner=owner)
    await asyncio.to_thread(cm.__enter__)
    try:
        yield locker.gpu_id
    finally:
        await asyncio.to_thread(cm.__exit__, None, None, None)
