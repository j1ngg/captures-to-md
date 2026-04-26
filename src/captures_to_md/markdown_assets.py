from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

_FALLBACK_EXT = ".png"


@dataclass(frozen=True)
class FigureRef:
    url: str
    local_name: str


def _figure_url_from_block(block: Any) -> str | None:
    details = getattr(block, "details", None)
    if details is None and isinstance(block, dict):
        details = block.get("details")
    if details is None:
        return None
    for attr in ("figureImageUrl", "figure_image_url", "imageUrl", "image_url"):
        url = getattr(details, attr, None)
        if url is None and isinstance(details, dict):
            url = details.get(attr)
        if url:
            return str(url)
    return None


def _blocks_of(chunk: Any) -> Iterable[Any]:
    blocks = getattr(chunk, "blocks", None)
    if blocks is None and isinstance(chunk, dict):
        blocks = chunk.get("blocks")
    return blocks or []


def _markdown_of(chunk: Any) -> str:
    for attr in ("markdown", "content"):
        v = getattr(chunk, attr, None)
        if v is None and isinstance(chunk, dict):
            v = chunk.get(attr)
        if v:
            return str(v)
    return ""


def join_chunks_markdown(chunks: Iterable[Any]) -> str:
    parts = [_markdown_of(c) for c in chunks]
    return "\n\n".join(p for p in parts if p).strip() + "\n"


def _ext_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix and len(suffix) <= 6:
        return suffix
    return _FALLBACK_EXT


def collect_figure_urls(chunks: Iterable[Any], *, stem: str) -> list[FigureRef]:
    refs: list[FigureRef] = []
    seen: set[str] = set()
    idx = 0
    for chunk in chunks:
        for block in _blocks_of(chunk):
            url = _figure_url_from_block(block)
            if not url or url in seen:
                continue
            idx += 1
            seen.add(url)
            refs.append(FigureRef(url=url, local_name=f"{stem}-fig-{idx}{_ext_from_url(url)}"))
    return refs


def download_figures(
    refs: Iterable[FigureRef],
    assets_dir: Path,
    client: httpx.Client,
) -> dict[str, str]:
    """Stream each figure to ``assets_dir`` and return ``{url: relative_path}``.

    Files that fail to download are omitted from the returned mapping and logged
    so the caller can decide how to surface them in the output markdown.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    for ref in refs:
        target = assets_dir / ref.local_name
        try:
            with client.stream("GET", ref.url) as resp:
                resp.raise_for_status()
                with target.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
        except (httpx.HTTPError, OSError) as exc:
            log.warning("figure download failed for %s: %s", ref.local_name, exc)
            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass
            continue
        out[ref.url] = f"{assets_dir.name}/{ref.local_name}"
    return out


def rewrite_figure_links(
    markdown: str,
    url_to_local: dict[str, str],
    *,
    assets_dirname: str,
) -> str:
    """Replace any inline occurrence of the presigned URL with the local path.

    URLs with no inline match are appended as a trailing ``## Assets`` section so
    downloaded figures are still discoverable even if the SDK didn't reference them
    in the chunk markdown directly.
    """
    body = markdown
    missing: list[tuple[str, str]] = []
    for url, local in url_to_local.items():
        if url in body:
            body = body.replace(url, local)
        else:
            missing.append((url, local))
    if missing:
        extras = "\n".join(f"- ![{Path(local).stem}]({local})" for _, local in missing)
        body = body.rstrip() + f"\n\n## Assets\n\n{extras}\n"
    return body


__all__ = [
    "FigureRef",
    "collect_figure_urls",
    "download_figures",
    "join_chunks_markdown",
    "rewrite_figure_links",
]
