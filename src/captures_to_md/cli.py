from __future__ import annotations

import logging
import os
import signal
import threading
import time
from pathlib import Path

import typer

from captures_to_md.config import Config
from captures_to_md.extend_client import ExtendClient
from captures_to_md.history import IngestHistory
from captures_to_md.logging import console, setup_logging
from captures_to_md.scan import run_scan
from captures_to_md.watcher import Dispatcher, build_observer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def _main() -> None:
    """captures-to-md: ingest files from a directory via the Extend Parse API."""


@app.command()
def scan(
    directory: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=False,
        help="Directory to scan. Symlinks are preserved; ~ is expanded.",
    ),
    workers: int = typer.Option(None, "--workers", "-w", help="Override concurrent workers."),
    log_level: str = typer.Option(None, "--log-level", help="DEBUG/INFO/WARNING/ERROR."),
    env_file: Path = typer.Option(None, "--env-file", help="Path to a .env file."),
) -> None:
    """Scan DIRECTORY once for unparsed files, process them, and exit."""
    watch_dir = directory.expanduser()
    cfg = Config.load(
        watch_dir=watch_dir,
        workers=workers,
        log_level=log_level,
        env_file=env_file,
    )
    setup_logging(cfg.log_level)
    code = run_scan(cfg)
    raise typer.Exit(code=code)


@app.command()
def watch(
    directory: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=False,
        help="Directory to watch. Symlinks are preserved; ~ is expanded.",
    ),
    workers: int = typer.Option(None, "--workers", "-w", help="Override concurrent ingest workers."),
    log_level: str = typer.Option(None, "--log-level", help="DEBUG/INFO/WARNING/ERROR."),
    env_file: Path = typer.Option(None, "--env-file", help="Path to a .env file."),
) -> None:
    """Watch DIRECTORY and ingest new PDFs / images / Office docs via Extend."""
    watch_dir = directory.expanduser()
    cfg = Config.load(
        watch_dir=watch_dir,
        workers=workers,
        log_level=log_level,
        env_file=env_file,
    )
    setup_logging(cfg.log_level)
    log = logging.getLogger("captures_to_md.cli")

    history = IngestHistory(watch_dir / cfg.history_filename)
    history.load()

    client = ExtendClient(cfg.api_key.get_secret_value())
    dispatcher = Dispatcher(cfg, history, client)
    observer = build_observer(cfg, dispatcher)

    stop_event = threading.Event()
    last_sigint_at: list[float] = [0.0]

    def handle_signal(signum, _frame) -> None:
        now = time.monotonic()
        if stop_event.is_set() and now - last_sigint_at[0] < 5.0:
            console.print("[red]second signal; hard-exiting[/red]")
            os._exit(130)
        last_sigint_at[0] = now
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    try:
        signal.signal(signal.SIGTERM, handle_signal)
    except (AttributeError, ValueError):
        pass  # Windows / non-main-thread fallback

    observer.start()
    console.print(
        f"[green]watching[/green] {watch_dir} (workers={cfg.workers}, "
        f"stability={cfg.stability_seconds}s)  — Ctrl-C to stop"
    )
    try:
        while not stop_event.wait(0.5):
            pass
    finally:
        log.info("shutting down")
        observer.stop()
        observer.join()
        dispatcher.shutdown()
        try:
            history.flush()
        except Exception:  # noqa: BLE001
            log.exception("history flush during shutdown failed")
        c = dispatcher.counters
        console.print(
            f"[bold]done[/bold]  processed={c['processed']} "
            f"failed={c['failed']} skipped={c['skipped']}"
        )


if __name__ == "__main__":
    app()
