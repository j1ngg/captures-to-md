from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import httpx
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from captures_to_md.config import Config
from captures_to_md.history import IngestHistory
from captures_to_md.processor import (
    ExtendClientProtocol,
    ProcessResult,
    process_file,
)

log = logging.getLogger(__name__)

ProcessFn = Callable[[Path], ProcessResult]


class Dispatcher:
    """Owns the worker pool, shared HTTP client, and in-flight tracking."""

    def __init__(
        self,
        cfg: Config,
        history: IngestHistory,
        client: ExtendClientProtocol,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.cfg = cfg
        self.history = history
        self.client = client
        self._pool = ThreadPoolExecutor(
            max_workers=cfg.workers, thread_name_prefix="ingest"
        )
        self._http = http_client or httpx.Client(timeout=30.0)
        self._owns_http = http_client is None
        self._in_flight: set[str] = set()
        self._lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.counters = {"processed": 0, "failed": 0, "skipped": 0}

    def submit(self, path: Path) -> Future[ProcessResult] | None:
        key = str(path)
        with self._lock:
            if key in self._in_flight:
                log.debug("%s already in flight; ignoring", path.name)
                return None
            self._in_flight.add(key)
        fut = self._pool.submit(self._run, path)
        fut.add_done_callback(lambda f: self._done(key, f))
        return fut

    def _run(self, path: Path) -> ProcessResult:
        return process_file(
            path,
            cfg=self.cfg,
            history=self.history,
            client=self.client,
            http_client=self._http,
            cancel_event=self.cancel_event,
        )

    def _done(self, key: str, fut: Future[ProcessResult]) -> None:
        with self._lock:
            self._in_flight.discard(key)
        exc = fut.exception()
        if exc is not None:
            self.counters["failed"] += 1
            log.exception("ingest failed for %s: %s", key, exc, exc_info=exc)
            return
        result = fut.result()
        if result.status == "saved":
            self.counters["processed"] += 1
        elif result.status == "skipped":
            self.counters["skipped"] += 1
        else:
            self.counters["failed"] += 1

    def shutdown(self) -> None:
        self.cancel_event.set()
        self._pool.shutdown(wait=True, cancel_futures=True)
        if self._owns_http:
            try:
                self._http.close()
            except Exception:  # noqa: BLE001 - best-effort during shutdown
                pass


class _IngestEventHandler(PatternMatchingEventHandler):
    def __init__(self, cfg: Config, dispatcher: Dispatcher) -> None:
        patterns = [f"*{ext}" for ext in cfg.supported_extensions]
        patterns += [p.upper() for p in patterns]
        ignore_patterns = [
            f"*/{cfg.assets_dirname}/*",
            f"*\\{cfg.assets_dirname}\\*",
            f"*/{cfg.history_filename}",
            f"*\\{cfg.history_filename}",
            "*/.*",
            "*\\.*",
            "*.tmp",
        ]
        super().__init__(
            patterns=patterns,
            ignore_patterns=ignore_patterns,
            ignore_directories=True,
            case_sensitive=False,
        )
        self._dispatcher = dispatcher

    def on_created(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        self._dispatcher.submit(Path(event.src_path))

    def on_moved(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        dest = getattr(event, "dest_path", None)
        if dest:
            self._dispatcher.submit(Path(dest))


def build_observer(cfg: Config, dispatcher: Dispatcher):
    observer = Observer()
    handler = _IngestEventHandler(cfg, dispatcher)
    observer.schedule(handler, str(cfg.watch_dir), recursive=True)
    return observer


__all__ = ["Dispatcher", "build_observer"]
