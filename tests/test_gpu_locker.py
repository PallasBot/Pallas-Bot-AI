from __future__ import annotations

import asyncio
import time

import pytest

import app.utils.gpu_locker as gl
from app.utils.gpu_locker import GPUHoldTimeoutError, GPULockManager, GPULockTimeoutError


class FakeLock:
    def __init__(self, store: dict, key: str, acquirable: bool = True):
        self._store = store
        self._key = key
        self.acquirable = acquirable
        self.extend_calls = 0
        self.released = False

    def acquire(self):
        if self.acquirable:
            self._store[self._key] = "wlock"
        return self.acquirable

    def extend(self, ttl, replace_ttl=True):
        self.extend_calls += 1

    def release(self):
        self.released = True
        self._store.pop(self._key, None)


class FakeRedis:
    """支持写锁(lock) + 读者键(set/exists/delete/expire/scan_iter) 的内存假实现。"""

    def __init__(self, write_acquirable: bool = True):
        self.store: dict[str, str] = {}
        self.lock_kwargs: dict = {}
        self.write_acquirable = write_acquirable
        self.last_lock: FakeLock | None = None

    def lock(self, name, **kwargs):
        self.lock_kwargs = kwargs
        self.last_lock = FakeLock(self.store, name, acquirable=self.write_acquirable)
        return self.last_lock

    def exists(self, key):
        return 1 if key in self.store else 0

    def set(self, key, val, ex=None):
        self.store[key] = val

    def delete(self, key):
        self.store.pop(key, None)

    def expire(self, key, ttl):
        return key in self.store

    def scan_iter(self, match=None, count=100):
        prefix = (match or "").rstrip("*")
        return [k for k in list(self.store) if k.startswith(prefix)]


@pytest.fixture
def patch_redis(monkeypatch):
    def _install(fake: FakeRedis):
        monkeypatch.setattr(gl, "redis_client", fake)
        return fake

    return _install


# ── 写锁 ────────────────────────────────────────────────────────────────
def test_write_acquire_release_normal(patch_redis):
    fake = patch_redis(FakeRedis())
    mgr = GPULockManager(0, lease_ttl=30, max_hold=1800)
    with mgr.acquire_write() as gid:
        assert gid == 0
    assert fake.last_lock.released is True


def test_acquire_alias_is_write(patch_redis):
    patch_redis(FakeRedis())
    mgr = GPULockManager(0)
    # 旧媒体调用 with locker.acquire() 仍走写锁
    with mgr.acquire() as gid:
        assert gid == 0


def test_write_timeout_raises(patch_redis):
    patch_redis(FakeRedis(write_acquirable=False))
    mgr = GPULockManager(0)
    with pytest.raises(GPULockTimeoutError):
        with mgr.acquire_write():
            pass


def test_write_watchdog_renews_lease(patch_redis):
    fake = patch_redis(FakeRedis())
    mgr = GPULockManager(0, lease_ttl=30, max_hold=1800, renew_interval=0.05)
    with mgr.acquire_write():
        time.sleep(0.2)
    assert fake.last_lock.extend_calls >= 1


def test_write_lock_thread_local_false(patch_redis):
    # 回归保护：看门狗在独立线程续租，必须 thread_local=False。
    fake = patch_redis(FakeRedis())
    mgr = GPULockManager(0, lease_ttl=30, max_hold=1800, renew_interval=0.05)
    with mgr.acquire_write():
        pass
    assert fake.lock_kwargs.get("thread_local") is False


def test_write_max_hold_forces_release(patch_redis):
    fake = patch_redis(FakeRedis())
    mgr = GPULockManager(0, lease_ttl=30, max_hold=0.1, renew_interval=0.05)
    with pytest.raises(GPUHoldTimeoutError):
        with mgr.acquire_write():
            time.sleep(0.4)
    assert fake.last_lock.released is True


def test_write_unloads_llm(patch_redis, monkeypatch):
    patch_redis(FakeRedis())
    called = {"n": 0}
    monkeypatch.setattr(gl, "_unload_resident_llm", lambda: called.__setitem__("n", called["n"] + 1))
    mgr = GPULockManager(0, lease_ttl=30, max_hold=1800, renew_interval=0.05)
    with mgr.acquire_write(unload_llm=True):
        pass
    assert called["n"] == 1


# ── 读锁 ────────────────────────────────────────────────────────────────
def test_read_acquire_registers_and_cleans(patch_redis):
    patch_redis(FakeRedis())
    mgr = GPULockManager(0, lease_ttl=30, renew_interval=0.05)
    with mgr.acquire_read() as gid:
        assert gid == 0
        # 持读锁期间应有一个 reader 键
        assert mgr._active_reader_count() == 1
    # 退出后清理
    assert mgr._active_reader_count() == 0


def test_readers_are_concurrent(patch_redis):
    patch_redis(FakeRedis())
    mgr = GPULockManager(0, lease_ttl=30, renew_interval=0.05)
    with mgr.acquire_read():
        with mgr.acquire_read():
            # 两个读者可同时持有，不互相阻塞
            assert mgr._active_reader_count() == 2


def test_read_blocks_when_writer_present(patch_redis):
    fake = patch_redis(FakeRedis())
    # 模拟已有写者
    fake.store["gpu_lock:0"] = "wlock"
    mgr = GPULockManager(0, wait_timeout=0, lease_ttl=30, renew_interval=0.05)
    with pytest.raises(GPULockTimeoutError):
        with mgr.acquire_read():
            pass


def test_write_waits_for_readers_drain_timeout(patch_redis):
    fake = patch_redis(FakeRedis())
    # 预置一个在途读者，写锁应等待 drain 超时
    fake.store["gpu_reader:0:existing"] = "1"
    mgr = GPULockManager(0, wait_timeout=0, lease_ttl=30, renew_interval=0.05)
    with pytest.raises(GPULockTimeoutError):
        with mgr.acquire_write():
            pass
    # 写锁应已释放（不残留）
    assert "gpu_lock:0" not in fake.store


def test_acquire_read_async(patch_redis, monkeypatch):
    patch_redis(FakeRedis())
    mgr = GPULockManager(0, lease_ttl=30, renew_interval=0.05)
    monkeypatch.setattr(gl, "get_gpu_locker", lambda gpu_id=None: mgr)

    async def _run():
        async with gl.acquire_gpu_read_async() as gid:
            assert gid == 0
            await asyncio.sleep(0.02)

    asyncio.run(_run())
    assert mgr._active_reader_count() == 0
