from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from captures_to_md.markdown_assets import (
    collect_figure_urls,
    download_figures,
    join_chunks_markdown,
    rewrite_figure_links,
)


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


def test_collect_figure_urls_dedup_and_ext() -> None:
    c1 = _Chunk(
        markdown="![](https://s3/a.png?sig=1)",
        blocks=[_Block(details=_Details(figureImageUrl="https://s3/a.png?sig=1"))],
    )
    c2 = _Chunk(
        markdown="no figures",
        blocks=[
            _Block(details=_Details(figureImageUrl="https://s3/a.png?sig=1")),
            _Block(details=_Details(figureImageUrl="https://s3/b.jpg")),
            _Block(details=None),
        ],
    )
    refs = collect_figure_urls([c1, c2], stem="doc")
    assert [r.url for r in refs] == ["https://s3/a.png?sig=1", "https://s3/b.jpg"]
    assert refs[0].local_name == "doc-fig-1.png"
    assert refs[1].local_name == "doc-fig-2.jpg"


def test_collect_figure_urls_fallback_extension() -> None:
    c = _Chunk(blocks=[_Block(details=_Details(figureImageUrl="https://s3/thing?x=1"))])
    refs = collect_figure_urls([c], stem="d")
    assert refs[0].local_name == "d-fig-1.png"


def test_join_chunks_markdown_skips_empty() -> None:
    chunks = [_Chunk(markdown="# A"), _Chunk(markdown=""), _Chunk(markdown="# B")]
    assert join_chunks_markdown(chunks).strip() == "# A\n\n# B"


def test_rewrite_inline(tmp_path: Path) -> None:
    md = "![](https://s3/a.png?sig=1) and again https://s3/a.png?sig=1"
    out = rewrite_figure_links(
        md,
        {"https://s3/a.png?sig=1": "assets/doc-fig-1.png"},
        assets_dirname="assets",
    )
    assert "https://s3/" not in out
    assert out.count("assets/doc-fig-1.png") == 2


def test_rewrite_adds_assets_section_when_no_inline_match() -> None:
    md = "body without figure links"
    out = rewrite_figure_links(
        md,
        {"https://s3/lost.png": "assets/doc-fig-1.png"},
        assets_dirname="assets",
    )
    assert "## Assets" in out
    assert "assets/doc-fig-1.png" in out


def test_download_figures_writes_files_and_returns_map(tmp_path: Path, httpx_mock) -> None:
    png = b"\x89PNG\r\n\x1a\nfake"
    httpx_mock.add_response(url="https://s3/a.png", content=png)
    httpx_mock.add_response(url="https://s3/b.jpg", content=b"jpgbytes")

    from captures_to_md.markdown_assets import FigureRef

    refs = [
        FigureRef(url="https://s3/a.png", local_name="doc-fig-1.png"),
        FigureRef(url="https://s3/b.jpg", local_name="doc-fig-2.jpg"),
    ]
    assets_dir = tmp_path / "assets"
    with httpx.Client() as client:
        mapping = download_figures(refs, assets_dir, client)

    assert mapping == {
        "https://s3/a.png": "assets/doc-fig-1.png",
        "https://s3/b.jpg": "assets/doc-fig-2.jpg",
    }
    assert (assets_dir / "doc-fig-1.png").read_bytes() == png


def test_download_figures_skips_failed(tmp_path: Path, httpx_mock) -> None:
    httpx_mock.add_response(url="https://s3/good.png", content=b"ok")
    httpx_mock.add_response(url="https://s3/bad.png", status_code=403)

    from captures_to_md.markdown_assets import FigureRef

    refs = [
        FigureRef(url="https://s3/good.png", local_name="g.png"),
        FigureRef(url="https://s3/bad.png", local_name="b.png"),
    ]
    with httpx.Client() as client:
        mapping = download_figures(refs, tmp_path / "assets", client)

    assert "https://s3/good.png" in mapping
    assert "https://s3/bad.png" not in mapping
    assert not (tmp_path / "assets" / "b.png").exists()


@pytest.fixture
def _noop() -> None:  # placeholder so pytest discovers pytest_httpx fixture plugin
    return None
