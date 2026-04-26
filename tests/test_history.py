from __future__ import annotations

import json
from pathlib import Path

from captures_to_md.history import IngestHistory, sha256_file


def test_record_and_persist_roundtrip(tmp_path: Path) -> None:
    hist_path = tmp_path / ".ingest_history.json"
    h = IngestHistory(hist_path)
    h.load()

    source = tmp_path / "doc.pdf"
    source.write_bytes(b"hello world")
    digest = sha256_file(source)
    out = source.with_suffix(".md")
    out.write_text("body")

    assert not h.already_processed(source)
    assert h.already_processed_digest(digest) is None
    h.record(source, digest=digest, output_md=out, source_size=source.stat().st_size)
    h.flush()

    assert hist_path.exists()
    raw = json.loads(hist_path.read_text())
    assert raw["version"] == 1
    assert str(source) in raw["entries"]
    assert raw["digest_index"][digest] == str(source)

    h2 = IngestHistory(hist_path)
    h2.load()
    assert h2.already_processed(source)
    assert h2.already_processed_digest(digest) == str(source)


def test_digest_dedup_across_paths(tmp_path: Path) -> None:
    h = IngestHistory(tmp_path / ".ingest_history.json")
    h.load()
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    digest_a = sha256_file(a)
    digest_b = sha256_file(b)
    assert digest_a == digest_b
    h.record(a, digest=digest_a, output_md=a.with_suffix(".md"), source_size=a.stat().st_size)
    assert h.already_processed_digest(digest_b) == str(a)


def test_corrupt_history_starts_fresh(tmp_path: Path) -> None:
    path = tmp_path / ".ingest_history.json"
    path.write_text("{not-json")
    h = IngestHistory(path)
    h.load()
    # Able to record after load.
    f = tmp_path / "x.pdf"
    f.write_bytes(b"x")
    h.record(f, digest="d" * 64, output_md=f.with_suffix(".md"), source_size=1)
    h.flush()
    raw = json.loads(path.read_text())
    assert raw["version"] == 1


def test_atomic_write_leaves_prior_intact_on_simulated_crash(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / ".ingest_history.json"
    h = IngestHistory(path)
    h.load()
    f = tmp_path / "y.pdf"
    f.write_bytes(b"y")
    h.record(f, digest="a" * 64, output_md=f.with_suffix(".md"), source_size=1)
    h.flush()
    good_bytes = path.read_bytes()

    # Simulate fsync failure mid-write. Since we write to `.tmp` first and only
    # os.replace if the write succeeds, the original file should remain.
    import os

    original_fsync = os.fsync

    def boom(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(os, "fsync", boom)
    try:
        h.record(f, digest="b" * 64, output_md=f.with_suffix(".md"), source_size=1)
        raised = False
        try:
            h.flush()
        except OSError:
            raised = True
        assert raised
    finally:
        monkeypatch.setattr(os, "fsync", original_fsync)

    assert path.read_bytes() == good_bytes
