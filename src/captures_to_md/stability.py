from __future__ import annotations

import threading
import time
from pathlib import Path


def wait_until_stable(
    path: Path,
    *,
    stability_seconds: float,
    poll_interval: float,
    max_wait_seconds: float,
    cancel_event: threading.Event,
) -> bool:
    """Poll (st_size, st_mtime) until the file has been unchanged for ``stability_seconds``.

    Returns True when stable, False if the file vanished, the timeout elapsed, or the
    cancel event was set. Uses ``cancel_event.wait`` for promptly-cancellable sleeps.
    """
    deadline = time.monotonic() + max_wait_seconds
    last_sig: tuple[int, float] | None = None
    stable_since: float | None = None

    while True:
        if cancel_event.is_set():
            return False
        try:
            st = path.stat()
        except FileNotFoundError:
            return False
        sig = (st.st_size, st.st_mtime)
        now = time.monotonic()

        if last_sig == sig:
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= stability_seconds:
                return True
        else:
            last_sig = sig
            stable_since = now

        if now >= deadline:
            return False
        if cancel_event.wait(poll_interval):
            return False
