"""Pre-flight check for the extend-ai SDK shape.

Run once before implementing against a new SDK version. Assumes EXTEND_API_KEY
is in your env and a `fidelity-example.pdf` sits in the repo root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def probe(name: str, ok: bool) -> bool:
    print(("OK  " if ok else "FAIL") + "  " + name)
    return ok


def main() -> int:
    from extend_ai import Extend

    api_key = os.environ.get("EXTEND_API_KEY")
    if not api_key:
        print("EXTEND_API_KEY not set")
        return 2

    c = Extend(token=api_key)

    ok = True
    ok &= probe("files.upload is callable", callable(getattr(c.files, "upload", None)))
    ok &= probe(
        "parse_runs.create_and_poll is callable",
        callable(getattr(c.parse_runs, "create_and_poll", None)),
    )

    sample = Path(__file__).resolve().parent.parent / "fidelity-example.pdf"
    if not sample.exists():
        print(f"missing sample file: {sample}")
        return 2

    with sample.open("rb") as f:
        resp = c.files.upload(file=f)
    file_id = getattr(resp, "id", None)
    if file_id is None and isinstance(resp, dict):
        file_id = resp.get("id")
    ok &= probe("upload response exposes .id", bool(file_id))

    run = c.parse_runs.create_and_poll(file={"id": file_id})
    output = getattr(run, "output", None)
    ok &= probe("run.output exists", output is not None)
    chunks = getattr(output, "chunks", None)
    ok &= probe("run.output.chunks is a list", isinstance(chunks, list) and len(chunks) > 0)
    if chunks:
        chunk = chunks[0]
        has_markdown = hasattr(chunk, "markdown") or (
            isinstance(chunk, dict) and "markdown" in chunk
        )
        has_content = hasattr(chunk, "content") or (
            isinstance(chunk, dict) and "content" in chunk
        )
        ok &= probe(
            "chunk exposes markdown text (.markdown or .content)",
            has_markdown or has_content,
        )
        print("\nFirst chunk dump:")
        print(chunk)
        blocks = getattr(chunk, "blocks", None) or (
            chunk.get("blocks") if isinstance(chunk, dict) else None
        )
        if blocks:
            figure_block = next(
                (
                    b
                    for b in blocks
                    if (
                        getattr(b, "details", None)
                        or (isinstance(b, dict) and b.get("details"))
                    )
                ),
                blocks[0],
            )
            details = getattr(figure_block, "details", None)
            if details is None and isinstance(figure_block, dict):
                details = figure_block.get("details")
            url = None
            for attr in ("figureImageUrl", "figure_image_url", "imageUrl", "image_url"):
                v = getattr(details, attr, None)
                if v is None and isinstance(details, dict):
                    v = details.get(attr)
                if v:
                    url = v
                    break
            ok &= probe(
                "figure block exposes an image URL (figureImageUrl/image_url/...)",
                bool(url),
            )
            print("\nFirst block dump:")
            print(figure_block)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
