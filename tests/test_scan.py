from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock


from captures_to_md.config import Config
from captures_to_md.scan import _candidate_paths, run_scan


@dataclass
class _Details:
    image_url: str | None = None


@dataclass
class _Block:
    details: _Details | dict | None = None


@dataclass
class _Chunk:
    content: str = ""
    blocks: list | None = None


@dataclass
class _Output:
    chunks: list


@dataclass
class _Result:
    output: _Output


def _fake_result() -> _Result:
    return _Result(output=_Output(chunks=[_Chunk(content="# Parsed\n\nbody", blocks=[])]))


def _cfg(tmp_path: Path) -> Config:
    cfg = Config.load(watch_dir=tmp_path, workers=1)
    return cfg.model_copy(update={"stability_seconds": 0.05, "stability_poll_interval": 0.02})


def test_candidate_paths_filters(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "note.txt").write_text("skip me")
    (tmp_path / ".ingest_history.json").write_text("{}")
    (tmp_path / ".hidden.pdf").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.pdf").write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "c.pdf").write_bytes(b"x")
    (tmp_path / "d.pdf.tmp").write_bytes(b"x")

    cfg = _cfg(tmp_path)
    found = {p.name for p in _candidate_paths(cfg)}
    assert found == {"a.pdf", "b.pdf"}


def test_scan_empty_dir_exits_zero(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    client = MagicMock()
    assert run_scan(cfg, client=client) == 0
    client.upload.assert_not_called()


def test_scan_processes_new_files(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"content-a")
    (tmp_path / "b.pdf").write_bytes(b"content-b")
    cfg = _cfg(tmp_path)

    client = MagicMock()
    client.upload.side_effect = ["file_a", "file_b"]
    client.parse_and_poll.return_value = _fake_result()

    code = run_scan(cfg, client=client)
    assert code == 0
    assert (tmp_path / "parsed_outputs" / "a.md").exists()
    assert (tmp_path / "parsed_outputs" / "b.md").exists()
    assert client.upload.call_count == 2


def test_rerun_is_all_skipped(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"same-bytes")
    cfg = _cfg(tmp_path)

    client = MagicMock()
    client.upload.return_value = "file_a"
    client.parse_and_poll.return_value = _fake_result()

    assert run_scan(cfg, client=client) == 0
    assert client.upload.call_count == 1

    # Second scan: SHA dedup → no new SDK calls.
    assert run_scan(cfg, client=client) == 0
    assert client.upload.call_count == 1


def test_scan_recurses_into_subfolders(tmp_path: Path) -> None:
    sub = tmp_path / "inbox" / "nested"
    sub.mkdir(parents=True)
    (sub / "deep.pdf").write_bytes(b"deep-bytes")

    cfg = _cfg(tmp_path)
    client = MagicMock()
    client.upload.return_value = "file_x"
    client.parse_and_poll.return_value = _fake_result()

    assert run_scan(cfg, client=client) == 0
    # All outputs converge to <watch_dir>/parsed_outputs/, regardless of
    # source nesting.
    assert (tmp_path / "parsed_outputs" / "deep.md").exists()


def test_scan_returns_nonzero_on_failure(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"bytes")
    cfg = _cfg(tmp_path)

    client = MagicMock()
    client.upload.side_effect = RuntimeError("upload exploded")

    assert run_scan(cfg, client=client) == 1
