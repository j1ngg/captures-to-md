from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_SHA_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_SHA_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


class IngestHistory:
    """Thread-safe JSON-backed record of processed files, keyed by absolute path with a
    secondary SHA index for content-level dedup across paths."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._empty()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"version": _SCHEMA_VERSION, "entries": {}, "digest_index": {}}

    def load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._data = self._empty()
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.warning("history file unreadable (%s); starting fresh", e)
                self._data = self._empty()
                return
            if not isinstance(raw, dict) or raw.get("version") != _SCHEMA_VERSION:
                log.warning("history schema mismatch; starting fresh")
                self._data = self._empty()
                return
            raw.setdefault("entries", {})
            raw.setdefault("digest_index", {})
            self._data = raw

    def already_processed(self, path: Path) -> bool:
        with self._lock:
            return str(path) in self._data["entries"]

    def already_processed_digest(self, digest: str) -> str | None:
        """Return the path we previously wrote output for, or None."""
        with self._lock:
            return self._data["digest_index"].get(digest)

    def record(self, path: Path, *, digest: str, output_md: Path, source_size: int) -> None:
        with self._lock:
            self._data["entries"][str(path)] = {
                "sha256": digest,
                "parsed_at": time.time(),
                "output_md": str(output_md),
                "source_size": source_size,
            }
            self._data["digest_index"][digest] = str(path)

    def output_for_path(self, path: Path) -> str | None:
        with self._lock:
            entry = self._data["entries"].get(str(path))
            return entry["output_md"] if entry else None

    def flush(self) -> None:
        with self._lock:
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            payload = json.dumps(self._data, indent=2, sort_keys=True)
            with tmp.open("w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
