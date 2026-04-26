from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import httpx

from captures_to_md.config import Config
from captures_to_md.history import IngestHistory
from captures_to_md.processor import ProcessResult
from captures_to_md.watcher import Dispatcher


def test_submit_dedups_in_flight_same_path(tmp_path: Path, monkeypatch) -> None:
    cfg = Config.load(watch_dir=tmp_path, workers=2)
    history = IngestHistory(tmp_path / cfg.history_filename)
    history.load()
    client = MagicMock()

    started = threading.Event()
    release = threading.Event()
    call_count = {"n": 0}

    def fake_process_file(path, **_kwargs):
        call_count["n"] += 1
        started.set()
        release.wait(timeout=2.0)
        return ProcessResult(status="saved")

    monkeypatch.setattr("captures_to_md.watcher.process_file", fake_process_file)

    http = httpx.Client()
    try:
        dispatcher = Dispatcher(cfg, history, client, http_client=http)
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"x")
        fut1 = dispatcher.submit(pdf)
        assert fut1 is not None
        # Wait for the worker to actually be inside process_file, then submit again.
        assert started.wait(timeout=2.0)
        fut2 = dispatcher.submit(pdf)
        assert fut2 is None
        release.set()
        fut1.result(timeout=2.0)
    finally:
        dispatcher.shutdown()
        http.close()

    assert call_count["n"] == 1


def test_submit_after_completion_allows_requeue(tmp_path: Path, monkeypatch) -> None:
    cfg = Config.load(watch_dir=tmp_path, workers=1)
    history = IngestHistory(tmp_path / cfg.history_filename)
    history.load()
    client = MagicMock()

    call_count = {"n": 0}

    def fake_process_file(path, **_kwargs):
        call_count["n"] += 1
        return ProcessResult(status="skipped")

    monkeypatch.setattr("captures_to_md.watcher.process_file", fake_process_file)

    http = httpx.Client()
    try:
        dispatcher = Dispatcher(cfg, history, client, http_client=http)
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"x")
        dispatcher.submit(pdf).result(timeout=2.0)
        fut2 = dispatcher.submit(pdf)
        assert fut2 is not None
        fut2.result(timeout=2.0)
    finally:
        dispatcher.shutdown()
        http.close()

    assert call_count["n"] == 2
