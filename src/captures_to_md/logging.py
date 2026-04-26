from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

console = Console()


class FileLoggerAdapter(logging.LoggerAdapter):
    """Prefixes every record with ``[filename]`` and its lifecycle stage."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        file_tag = self.extra.get("file", "-") if self.extra else "-"
        stage = kwargs.pop("stage", None)
        prefix = f"[{file_tag}]"
        if stage:
            prefix += f" {stage}:"
        return f"{prefix} {msg}", kwargs


def setup_logging(level: str = "INFO") -> None:
    handler = RichHandler(console=console, show_time=True, show_path=False, markup=False)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def file_logger(name: str, file_tag: str) -> FileLoggerAdapter:
    return FileLoggerAdapter(logging.getLogger(name), {"file": file_tag})
