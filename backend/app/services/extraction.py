"""Content extraction and normalization for supported document types.

Each extractor returns an ExtractionResult with normalized text, optional
per-page segments (for page-number citations), and detected metadata. Headings
and code blocks are preserved where the source format exposes them.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field


@dataclass
class PageSegment:
    page_number: int | None
    text: str


@dataclass
class ExtractionResult:
    text: str
    segments: list[PageSegment] = field(default_factory=list)
    title: str = ""
    author: str = ""
    mime_type: str = ""


class ExtractionError(Exception):
    pass


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of blank lines, strip trailing spaces per line.
    lines = [ln.rstrip() for ln in text.split("\n")]
    out: list[str] = []
    blank = 0
    for ln in lines:
        if ln.strip() == "":
            blank += 1
            if blank <= 2:
                out.append("")
        else:
            blank = 0
            out.append(ln)
    return "\n".join(out).strip()


def extract_text_plain(data: bytes) -> ExtractionResult:
    text = _normalize(data.decode("utf-8", errors="replace"))
    return ExtractionResult(text=text, mime_type="text/plain")


def extract_markdown(data: bytes) -> ExtractionResult:
    # Keep markdown structure (headings, code fences) as-is; it chunks well.
    text = _normalize(data.decode("utf-8", errors="replace"))
    title = ""
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        title = m.group(1).strip()
    return ExtractionResult(text=text, title=title, mime_type="text/markdown")


def extract_html(data: bytes) -> ExtractionResult:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    author = ""
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author and meta_author.get("content"):
        author = meta_author["content"].strip()
    # Prefer <article>/<main> if present.
    root = soup.find("article") or soup.find("main") or soup.body or soup
    # Preserve code blocks and headings via text extraction with separators.
    text = _normalize(root.get_text(separator="\n"))
    return ExtractionResult(text=text, title=title, author=author, mime_type="text/html")


def extract_pdf(data: bytes) -> ExtractionResult:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # malformed / encrypted
        raise ExtractionError(f"Could not read PDF: {exc}") from exc

    segments: list[PageSegment] = []
    parts: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        page_text = _normalize(page_text)
        if page_text:
            segments.append(PageSegment(page_number=i, text=page_text))
            parts.append(page_text)
    title = ""
    author = ""
    try:
        meta = reader.metadata or {}
        title = (meta.title or "").strip() if meta else ""
        author = (meta.author or "").strip() if meta else ""
    except Exception:
        pass
    full = _normalize("\n\n".join(parts))
    if not full:
        raise ExtractionError("No extractable text found in PDF (may be scanned/image-only).")
    return ExtractionResult(
        text=full, segments=segments, title=title, author=author, mime_type="application/pdf"
    )


def extract_docx(data: bytes) -> ExtractionResult:
    from docx import Document as DocxDocument

    try:
        doc = DocxDocument(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(f"Could not read DOCX: {exc}") from exc
    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            style = (para.style.name or "").lower() if para.style else ""
            if "heading" in style:
                parts.append(f"## {para.text.strip()}")
            else:
                parts.append(para.text)
    # Tables.
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    text = _normalize("\n".join(parts))
    if not text:
        raise ExtractionError("No extractable text found in DOCX.")
    return ExtractionResult(text=text, mime_type=(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ))


# Dispatch table keyed by source_type.
_EXTRACTORS = {
    "txt": extract_text_plain,
    "text": extract_text_plain,
    "markdown": extract_markdown,
    "md": extract_markdown,
    "html": extract_html,
    "pdf": extract_pdf,
    "docx": extract_docx,
}


def extract(source_type: str, data: bytes) -> ExtractionResult:
    fn = _EXTRACTORS.get(source_type.lower())
    if fn is None:
        raise ExtractionError(f"Unsupported source type for extraction: {source_type}")
    return fn(data)


def extract_from_html_string(html: str) -> ExtractionResult:
    return extract_html(html.encode("utf-8"))
