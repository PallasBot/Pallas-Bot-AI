from __future__ import annotations

from threading import RLock, Timer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class TtsPipelineCache[T]:
    def __init__(
        self,
        loader: Callable[[], T],
        on_unload: Callable[[], None],
        idle_sec: float,
        timer_factory: Callable[[float, Callable[[], None]], Timer] = Timer,
    ) -> None:
        self._loader = loader
        self._on_unload = on_unload
        self._idle_sec = idle_sec
        self._timer_factory = timer_factory
        self._lock = RLock()
        self._pipeline: T | None = None
        self._timer: Timer | None = None
        self._generation = 0

    def get(self) -> T:
        with self._lock:
            self._cancel_pending_unload()
            self._generation += 1
            if self._pipeline is None:
                self._pipeline = self._loader()
            return self._pipeline

    def schedule_unload(self) -> None:
        with self._lock:
            self._cancel_pending_unload()
            if self._pipeline is None:
                return
            self._generation += 1
            generation = self._generation
            timer = self._timer_factory(self._idle_sec, lambda: self._unload_if_current(generation))
            timer.daemon = True
            timer.start()
            self._timer = timer

    def unload(self) -> bool:
        with self._lock:
            self._cancel_pending_unload()
            if self._pipeline is None:
                return False
            self._pipeline = None
            self._generation += 1
            self._on_unload()
            return True

    @property
    def is_loaded(self) -> bool:
        with self._lock:
            return self._pipeline is not None

    def _cancel_pending_unload(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _unload_if_current(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation or self._pipeline is None:
                return
            self.unload()
