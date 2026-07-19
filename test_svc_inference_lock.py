from contextlib import contextmanager

import pytest

pytest.importorskip("pyncm_async")

from app.tasks.sing.svc_inference import _maybe_lock


def test_svc_lock_unloads_llm_and_records_owner() -> None:
    calls: list[tuple[bool, dict[str, str]]] = []

    class Locker:
        @contextmanager
        def acquire(self, *, unload_llm: bool = False, owner: dict[str, str] | None = None):
            calls.append((unload_llm, owner or {}))
            yield

    owner = {"kind": "sing", "step": "svc", "song": "song.wav", "speaker": "pallas"}
    with _maybe_lock(Locker(), owner=owner):
        pass

    assert calls == [(True, owner)]
