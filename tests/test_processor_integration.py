from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import httpx

from captures_to_md.config import Config
from captures_to_md.history import IngestHistory
from captures_to_md.processor import process_file


@dataclass
class _Details:
    figureImageUrl: str | None = None


@dataclass
class _Block:
    details: _Details | None = None


@dataclass
class _Chunk:
    markdown: str = ""
    blocks: list[_Block] | None = None


@dataclass
class _Output:
    chunks: list[_Chunk]


@dataclass
class _Result:
    output: _Output


def _fake_result(figure_url: str) -> _Result:
    return _Result(
        output=_Output(
            chunks=[
                _Chunk(
                    markdown=f"# First chunk\n\n![fig]({figure_url})\n",
                    blocks=[_Block(details=_Details(figureImageUrl=figure_url))],
                ),
                _Chunk(markdown="# Second chunk\n\nbody text.", blocks=[]),
            ]
        )
    )


def test_end_to_end_saves_md_and_figure(tmp_path: Path, httpx_mock) -> None:
    cfg = Config.load(watch_dir=tmp_path, workers=1)
    cfg = cfg.model_copy(update={"stability_seconds": 0.05, "stability_poll_interval": 0.02})
    hist = IngestHistory(tmp_path / cfg.history_filename)
    hist.load()

    figure_url = "https://example.test/a.png?sig=abc"
    png = b"\x89PNG\r\n\x1a\nfakefigurebytes"
    httpx_mock.add_response(url=figure_url, content=png)

    client = MagicMock()
    client.upload.return_value = "file_123"
    client.parse_and_poll.return_value = _fake_result(figure_url)

    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n...\n%%EOF")

    http = httpx.Client()
    try:
        result = process_file(
            pdf,
            cfg=cfg,
            history=hist,
            client=client,
            http_client=http,
            cancel_event=threading.Event(),
        )
    finally:
        http.close()

    assert result.status == "saved"
    md_path = tmp_path / "parsed_outputs" / "sample.md"
    assert md_path.exists()
    body = md_path.read_text()
    assert figure_url not in body  # rewritten
    assert "assets/sample-fig-1.png" in body
    assert (tmp_path / "parsed_outputs" / "assets" / "sample-fig-1.png").read_bytes() == png
    # History reflects the write.
    assert hist.already_processed(pdf)


def test_rerun_is_skipped_via_sha_dedup(tmp_path: Path, httpx_mock) -> None:
    cfg = Config.load(watch_dir=tmp_path, workers=1)
    cfg = cfg.model_copy(update={"stability_seconds": 0.05, "stability_poll_interval": 0.02})
    hist = IngestHistory(tmp_path / cfg.history_filename)
    hist.load()

    figure_url = "https://example.test/a.png"
    httpx_mock.add_response(url=figure_url, content=b"png")

    client = MagicMock()
    client.upload.return_value = "file_1"
    client.parse_and_poll.return_value = _fake_result(figure_url)

    pdf = tmp_path / "same.pdf"
    pdf.write_bytes(b"identical-bytes")

    http = httpx.Client()
    try:
        first = process_file(
            pdf,
            cfg=cfg,
            history=hist,
            client=client,
            http_client=http,
            cancel_event=threading.Event(),
        )
        second = process_file(
            pdf,
            cfg=cfg,
            history=hist,
            client=client,
            http_client=http,
            cancel_event=threading.Event(),
        )
    finally:
        http.close()

    assert first.status == "saved"
    assert second.status == "skipped"
    assert client.upload.call_count == 1
    assert client.parse_and_poll.call_count == 1


def test_collision_resolves_to_parsed_md(tmp_path: Path, httpx_mock) -> None:
    cfg = Config.load(watch_dir=tmp_path, workers=1)
    cfg = cfg.model_copy(update={"stability_seconds": 0.05, "stability_poll_interval": 0.02})
    hist = IngestHistory(tmp_path / cfg.history_filename)
    hist.load()

    figure_url = "https://example.test/a.png"
    httpx_mock.add_response(url=figure_url, content=b"png")

    client = MagicMock()
    client.upload.return_value = "file_1"
    client.parse_and_poll.return_value = _fake_result(figure_url)

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"bytes")
    # Pre-existing .md not in history — should force `.parsed.md` fallback.
    (tmp_path / "parsed_outputs").mkdir()
    (tmp_path / "parsed_outputs" / "report.md").write_text("hand-written notes")

    http = httpx.Client()
    try:
        result = process_file(
            pdf,
            cfg=cfg,
            history=hist,
            client=client,
            http_client=http,
            cancel_event=threading.Event(),
        )
    finally:
        http.close()

    assert result.status == "saved"
    assert (tmp_path / "parsed_outputs" / "report.md").read_text() == "hand-written notes"
    assert (tmp_path / "parsed_outputs" / "report.parsed.md").exists()


def test_non_retryable_chunks_error_surfaces(tmp_path: Path) -> None:
    cfg = Config.load(watch_dir=tmp_path, workers=1)
    cfg = cfg.model_copy(update={"stability_seconds": 0.05, "stability_poll_interval": 0.02})
    hist = IngestHistory(tmp_path / cfg.history_filename)
    hist.load()

    client = MagicMock()
    client.upload.return_value = "file_1"

    class _NoChunks:
        pass

    client.parse_and_poll.return_value = _NoChunks()

    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"bytes")

    http = httpx.Client()
    try:
        try:
            process_file(
                pdf,
                cfg=cfg,
                history=hist,
                client=client,
                http_client=http,
                cancel_event=threading.Event(),
            )
        except Exception as exc:  # noqa: BLE001
            assert "chunks" in str(exc).lower()
        else:
            raise AssertionError("expected schema error")
    finally:
        http.close()

    # History must NOT record a failed run — users can retry manually.
    assert not hist.already_processed(pdf)
