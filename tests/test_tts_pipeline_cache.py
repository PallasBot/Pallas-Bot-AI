from app.workers.tts.pipeline_cache import TtsPipelineCache


class FakeTimer:
    def __init__(self, delay: float, callback) -> None:
        self.delay = delay
        self.callback = callback
        self.cancelled = False
        self.started = False
        self.daemon = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.callback()


def test_tts_pipeline_cache_releases_pipeline_after_idle_timeout() -> None:
    pipeline = object()
    released: list[str] = []
    timers: list[FakeTimer] = []
    cache = TtsPipelineCache(
        loader=lambda: pipeline,
        on_unload=lambda: released.append("released"),
        idle_sec=120,
        timer_factory=lambda delay, callback: timers.append(FakeTimer(delay, callback)) or timers[-1],
    )

    assert cache.get() is pipeline
    cache.schedule_unload()
    timers[0].fire()

    assert timers[0].delay == 120
    assert released == ["released"]


def test_tts_pipeline_cache_ignores_cancelled_timer_callback_after_new_request() -> None:
    pipeline = object()
    released: list[str] = []
    timers: list[FakeTimer] = []
    cache = TtsPipelineCache(
        loader=lambda: pipeline,
        on_unload=lambda: released.append("released"),
        idle_sec=120,
        timer_factory=lambda delay, callback: timers.append(FakeTimer(delay, callback)) or timers[-1],
    )

    cache.get()
    cache.schedule_unload()
    cache.get()
    timers[0].fire()

    assert timers[0].cancelled is True
    assert released == []


def test_tts_pipeline_cache_unload_deferred_while_in_use() -> None:
    pipeline = object()
    released: list[str] = []
    timers: list[FakeTimer] = []
    cache = TtsPipelineCache(
        loader=lambda: pipeline,
        on_unload=lambda: released.append("released"),
        idle_sec=120,
        timer_factory=lambda delay, callback: timers.append(FakeTimer(delay, callback)) or timers[-1],
    )

    cache.get()
    cache.retain()
    assert cache.unload() is True
    assert released == []

    cache.release()

    assert released == ["released"]


def test_tts_pipeline_cache_unload_immediate_when_not_in_use() -> None:
    pipeline = object()
    released: list[str] = []
    timers: list[FakeTimer] = []
    cache = TtsPipelineCache(
        loader=lambda: pipeline,
        on_unload=lambda: released.append("released"),
        idle_sec=120,
        timer_factory=lambda delay, callback: timers.append(FakeTimer(delay, callback)) or timers[-1],
    )

    cache.get()
    assert cache.unload() is True
    assert released == ["released"]


def test_tts_pipeline_cache_get_after_pending_unload_reuses_pipeline() -> None:
    pipeline = object()
    released: list[str] = []
    timers: list[FakeTimer] = []
    cache = TtsPipelineCache(
        loader=lambda: pipeline,
        on_unload=lambda: released.append("released"),
        idle_sec=120,
        timer_factory=lambda delay, callback: timers.append(FakeTimer(delay, callback)) or timers[-1],
    )

    cache.get()
    cache.retain()
    assert cache.unload() is True
    assert released == []

    assert cache.get() is pipeline
    cache.release()

    assert released == ["released"]


def test_tts_pipeline_cache_can_be_unloaded_immediately_for_sing() -> None:
    pipeline = object()
    released: list[str] = []
    timers: list[FakeTimer] = []
    cache = TtsPipelineCache(
        loader=lambda: pipeline,
        on_unload=lambda: released.append("released"),
        idle_sec=120,
        timer_factory=lambda delay, callback: timers.append(FakeTimer(delay, callback)) or timers[-1],
    )

    cache.get()
    cache.schedule_unload()

    assert cache.unload() is True
    assert timers[0].cancelled is True
    assert released == ["released"]

    timers[0].fire()

    assert released == ["released"]
