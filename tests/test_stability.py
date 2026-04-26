from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from captures_to_md.stability import wait_until_stable


def test_returns_true_after_quiet_period(tmp_path: Path) -> None:
    f = tmp_path / "a.pdf"
    f.write_bytes(b"hello")
    cancel = threading.Event()
    assert wait_until_stable(
        f,
        stability_seconds=0.2,
        poll_interval=0.05,
        max_wait_seconds=5.0,
        cancel_event=cancel,
    )


def test_returns_false_when_file_vanishes(tmp_path: Path) -> None:
    f = tmp_path / "b.pdf"
    f.write_bytes(b"x")
    cancel = threading.Event()

    def remover() -> None:
        time.sleep(0.05)
        f.unlink()

    threading.Thread(target=remover, daemon=True).start()
    assert not wait_until_stable(
        f,
        stability_seconds=0.5,
        poll_interval=0.02,
        max_wait_seconds=2.0,
        cancel_event=cancel,
    )


def test_returns_false_on_cancel(tmp_path: Path) -> None:
    f = tmp_path / "c.pdf"
    f.write_bytes(b"x")
    cancel = threading.Event()

    def canceller() -> None:
        time.sleep(0.05)
        cancel.set()

    threading.Thread(target=canceller, daemon=True).start()
    assert not wait_until_stable(
        f,
        stability_seconds=5.0,
        poll_interval=0.02,
        max_wait_seconds=5.0,
        cancel_event=cancel,
    )


def test_extends_wait_while_file_keeps_changing(tmp_path: Path) -> None:
    f = tmp_path / "d.pdf"
    f.write_bytes(b"0")
    cancel = threading.Event()

    stopped = threading.Event()

    def writer() -> None:
        for i in range(5):
            if stopped.is_set():
                return
            time.sleep(0.05)
            f.write_bytes(str(i).encode() * (i + 1))

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    start = time.monotonic()
    ok = wait_until_stable(
        f,
        stability_seconds=0.1,
        poll_interval=0.02,
        max_wait_seconds=5.0,
        cancel_event=cancel,
    )
    elapsed = time.monotonic() - start
    stopped.set()
    t.join(timeout=1.0)
    assert ok
    # Must have waited beyond just the stability window because the file kept changing.
    assert elapsed >= 0.25


def test_returns_false_on_timeout(tmp_path: Path) -> None:
    f = tmp_path / "e.pdf"
    f.write_bytes(b"x")
    cancel = threading.Event()
    stopped = threading.Event()

    def writer() -> None:
        i = 0
        while not stopped.is_set():
            f.write_bytes(f"v{i}".encode())
            i += 1
            time.sleep(0.05)

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    try:
        with pytest.MonkeyPatch.context() as _:
            pass
        assert not wait_until_stable(
            f,
            stability_seconds=1.0,
            poll_interval=0.02,
            max_wait_seconds=0.3,
            cancel_event=cancel,
        )
    finally:
        stopped.set()
        t.join(timeout=1.0)
