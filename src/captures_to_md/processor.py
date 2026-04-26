from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from captures_to_md.config import Config
from captures_to_md.history import IngestHistory, sha256_file
from captures_to_md.logging import file_logger
from captures_to_md.markdown_assets import (
    collect_figure_urls,
    download_figures,
    join_chunks_markdown,
    rewrite_figure_links,
)
from captures_to_md.retry import call_with_retry
from captures_to_md.stability import wait_until_stable


class ExtendClientProtocol(Protocol):
    def upload(self, path: Path) -> str: ...

    def parse_and_poll(self, *, file_id: str, timeout: float) -> Any: ...


class ExtendSchemaError(RuntimeError):
    """Raised when the parsed result doesn't look like we expect."""


@dataclass
class ProcessResult:
    status: str  # "saved" | "skipped" | "failed"
    output_md: Path | None = None


def atomic_write_text(target: Path, text: str) -> None:
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def _chunks_of(result: Any) -> list[Any]:
    output = getattr(result, "output", None)
    if output is None and isinstance(result, dict):
        output = result.get("output")
    chunks = getattr(output, "chunks", None) if output is not None else None
    if chunks is None and isinstance(output, dict):
        chunks = output.get("chunks")
    if chunks is None:
        raise ExtendSchemaError(
            f"parse result has no .output.chunks (got: {type(result).__name__})"
        )
    return list(chunks)


def _resolve_output_path(source: Path, history: IngestHistory, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    primary = output_dir / f"{source.stem}.md"
    if not primary.exists():
        return primary
    previous = history.output_for_path(source)
    if previous and Path(previous) == primary:
        return primary
    return output_dir / f"{source.stem}.parsed.md"


def process_file(
    path: Path,
    *,
    cfg: Config,
    history: IngestHistory,
    client: ExtendClientProtocol,
    http_client: httpx.Client,
    cancel_event: threading.Event,
) -> ProcessResult:
    log = file_logger(__name__, path.name)
    log.info("detected", stage="detected")

    if not wait_until_stable(
        path,
        stability_seconds=cfg.stability_seconds,
        poll_interval=cfg.stability_poll_interval,
        max_wait_seconds=cfg.stability_max_wait_seconds,
        cancel_event=cancel_event,
    ):
        log.warning("file never stabilized or vanished; skipping")
        return ProcessResult(status="skipped")
    log.info("stable", stage="stable")

    if path.suffix.lower() not in cfg.supported_extensions:
        log.info("unsupported extension %s; skipping", path.suffix)
        return ProcessResult(status="skipped")

    try:
        digest = sha256_file(path)
        source_size = path.stat().st_size
    except FileNotFoundError:
        log.warning("file vanished before hashing; skipping")
        return ProcessResult(status="skipped")

    previous = history.already_processed_digest(digest)
    if previous is not None:
        log.info("already processed (sha match %s); skipping", previous)
        return ProcessResult(status="skipped")

    log.info("uploading", stage="uploading")
    file_id = call_with_retry(
        lambda: client.upload(path),
        description=f"upload {path.name}",
        max_attempts=cfg.retry_max_attempts,
        base_seconds=cfg.retry_base_seconds,
        cap_seconds=cfg.retry_cap_seconds,
    )
    log.info("uploaded (id=%s)", file_id, stage="uploaded")

    log.info("parsing", stage="parsing")
    result = call_with_retry(
        lambda: client.parse_and_poll(file_id=file_id, timeout=cfg.parse_timeout_seconds),
        description=f"parse {path.name}",
        max_attempts=cfg.retry_max_attempts,
        base_seconds=cfg.retry_base_seconds,
        cap_seconds=cfg.retry_cap_seconds,
    )
    log.info("parsed", stage="parsed")

    chunks = _chunks_of(result)
    body = join_chunks_markdown(chunks)
    figures = collect_figure_urls(chunks, stem=path.stem)
    output_dir = cfg.watch_dir / "parsed_outputs"
    assets_dir = output_dir / cfg.assets_dirname
    url_to_local = download_figures(figures, assets_dir, http_client) if figures else {}
    body = rewrite_figure_links(body, url_to_local, assets_dirname=cfg.assets_dirname)

    out_path = _resolve_output_path(path, history, output_dir)
    atomic_write_text(out_path, body)
    history.record(path, digest=digest, output_md=out_path, source_size=source_size)
    history.flush()
    log.info("saved %s", out_path.name, stage="saved")
    return ProcessResult(status="saved", output_md=out_path)


__all__ = [
    "ExtendClientProtocol",
    "ExtendSchemaError",
    "ProcessResult",
    "atomic_write_text",
    "process_file",
]
