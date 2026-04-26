from __future__ import annotations

from pathlib import Path
from typing import Any


class ExtendClient:
    """Thin wrapper around ``extend_ai.Extend`` so the rest of the codebase can be
    unit-tested without touching the real SDK."""

    def __init__(self, api_key: str) -> None:
        from extend_ai import Extend  # imported lazily so tests can monkeypatch

        self._c = Extend(token=api_key)

    def upload(self, path: Path) -> str:
        with path.open("rb") as f:
            resp = self._c.files.upload(file=f)
        file_id = getattr(resp, "id", None)
        if file_id is None and isinstance(resp, dict):
            file_id = resp.get("id")
        if not file_id:
            raise RuntimeError(f"Extend upload returned no id: {resp!r}")
        return str(file_id)

    def parse_and_poll(self, *, file_id: str, timeout: float) -> Any:
        # extend-ai 1.9 does not accept a `timeout` kwarg on create_and_poll;
        # the parameter is kept in our wrapper signature so callers can pass it
        # for future SDK versions without reshaping the call site.
        del timeout
        return self._c.parse_runs.create_and_poll(file={"id": file_id})
