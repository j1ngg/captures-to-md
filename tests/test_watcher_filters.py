from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from captures_to_md.config import Config
from captures_to_md.watcher import Dispatcher, _IngestEventHandler


def _cfg(tmp_path: Path) -> Config:
    return Config.load(watch_dir=tmp_path)


def _fake_dispatcher() -> MagicMock:
    d = MagicMock(spec=Dispatcher)
    d.submit = MagicMock()
    return d


def _created(path: Path):
    return SimpleNamespace(
        src_path=str(path), dest_path="", is_directory=False, event_type="created"
    )


def _moved(src: Path, dest: Path):
    return SimpleNamespace(
        src_path=str(src),
        dest_path=str(dest),
        is_directory=False,
        event_type="moved",
    )


def test_pdf_create_dispatches(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = _fake_dispatcher()
    h = _IngestEventHandler(cfg, d)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"")
    h.dispatch(_created(pdf))
    d.submit.assert_called_once_with(pdf)


def test_txt_is_ignored(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = _fake_dispatcher()
    h = _IngestEventHandler(cfg, d)
    txt = tmp_path / "notes.txt"
    txt.write_bytes(b"")
    h.dispatch(_created(txt))
    d.submit.assert_not_called()


def test_file_under_assets_is_ignored(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = _fake_dispatcher()
    h = _IngestEventHandler(cfg, d)
    (tmp_path / "assets").mkdir()
    pdf = tmp_path / "assets" / "fig.pdf"
    pdf.write_bytes(b"")
    h.dispatch(_created(pdf))
    d.submit.assert_not_called()


def test_history_file_is_ignored(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = _fake_dispatcher()
    h = _IngestEventHandler(cfg, d)
    hist = tmp_path / cfg.history_filename
    hist.write_text("{}")
    h.dispatch(_created(hist))
    d.submit.assert_not_called()


def test_move_dispatches_dest_path(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = _fake_dispatcher()
    h = _IngestEventHandler(cfg, d)
    src = tmp_path / "incoming.pdf"
    dest = tmp_path / "final.pdf"
    dest.write_bytes(b"")
    h.dispatch(_moved(src, dest))
    d.submit.assert_called_once_with(dest)


def test_case_insensitive_extension(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = _fake_dispatcher()
    h = _IngestEventHandler(cfg, d)
    pdf = tmp_path / "Loud.PDF"
    pdf.write_bytes(b"")
    h.dispatch(_created(pdf))
    d.submit.assert_called_once_with(pdf)
