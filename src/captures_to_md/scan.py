from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from captures_to_md.config import Config
from captures_to_md.extend_client import ExtendClient
from captures_to_md.history import IngestHistory
from captures_to_md.processor import ExtendClientProtocol, process_file

log = logging.getLogger(__name__)


def _candidate_paths(cfg: Config) -> list[Path]:
    root = cfg.watch_dir
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in cfg.supported_extensions:
            continue
        rel_parts = p.relative_to(root).parts
        if any(part == cfg.assets_dirname for part in rel_parts):
            continue
        if any(part.startswith(".") for part in rel_parts):
            continue
        if p.name == cfg.history_filename:
            continue
        if p.suffix == ".tmp":
            continue
        out.append(p)
    return sorted(out)


def run_scan(cfg: Config, *, client: ExtendClientProtocol | None = None) -> int:
    """Scan ``cfg.watch_dir`` once, processing anything unprocessed. Returns an
    exit code: 0 if every candidate either succeeded or was skipped, 1 if any
    failed."""
    history = IngestHistory(cfg.watch_dir / cfg.history_filename)
    history.load()

    if client is None:
        client = ExtendClient(cfg.api_key.get_secret_value())

    paths = _candidate_paths(cfg)
    if not paths:
        log.info("no supported files found in %s", cfg.watch_dir)
        return 0

    log.info("scanning %d file(s) in %s", len(paths), cfg.watch_dir)

    cancel_event = threading.Event()
    counters = {"processed": 0, "failed": 0, "skipped": 0}

    with httpx.Client(timeout=30.0) as http, ThreadPoolExecutor(
        max_workers=cfg.workers, thread_name_prefix="scan"
    ) as pool:
        futures = {
            pool.submit(
                process_file,
                p,
                cfg=cfg,
                history=history,
                client=client,
                http_client=http,
                cancel_event=cancel_event,
            ): p
            for p in paths
        }
        for fut in as_completed(futures):
            path = futures[fut]
            try:
                result = fut.result()
            except Exception:
                counters["failed"] += 1
                log.exception("scan failed for %s", path)
                continue
            if result.status == "saved":
                counters["processed"] += 1
            elif result.status == "skipped":
                counters["skipped"] += 1
            else:
                counters["failed"] += 1

    history.flush()
    log.info(
        "scan done: processed=%d failed=%d skipped=%d",
        counters["processed"],
        counters["failed"],
        counters["skipped"],
    )
    return 0 if counters["failed"] == 0 else 1


__all__ = ["run_scan"]
