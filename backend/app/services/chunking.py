"""Heading-aware, size-bounded text chunking with overlap.

Token counts are estimated (~4 chars/token) to stay dependency-free and
provider-agnostic. Chunks carry a section heading (nearest preceding markdown
or ALL-CAPS heading) and, when available, a page number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings
from app.services.extraction import ExtractionResult, PageSegment

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class TextChunk:
    ordinal: int
    text: str
    token_estimate: int
    section_heading: str = ""
    page_number: int | None = None


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _split_paragraphs(text: str) -> list[str]:
    # Split on blank lines but keep fenced code blocks intact.
    blocks: list[str] = []
    in_fence = False
    buf: list[str] = []
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            buf.append(line)
            continue
        if not in_fence and line.strip() == "":
            if buf:
                blocks.append("\n".join(buf).strip())
                buf = []
        else:
            buf.append(line)
    if buf:
        blocks.append("\n".join(buf).strip())
    return [b for b in blocks if b]


def _chunk_segment(
    text: str,
    start_ordinal: int,
    page_number: int | None,
    target: int,
    overlap: int,
) -> list[TextChunk]:
    paras = _split_paragraphs(text)
    chunks: list[TextChunk] = []
    current: list[str] = []
    current_tokens = 0
    heading = ""
    ordinal = start_ordinal

    def flush():
        nonlocal current, current_tokens, ordinal
        if not current:
            return
        body = "\n\n".join(current).strip()
        if body:
            chunks.append(
                TextChunk(
                    ordinal=ordinal,
                    text=body,
                    token_estimate=estimate_tokens(body),
                    section_heading=heading,
                    page_number=page_number,
                )
            )
            ordinal += 1
        current = []
        current_tokens = 0

    for para in paras:
        m = _HEADING_RE.match(para.split("\n", 1)[0])
        if m:
            heading = m.group(2).strip()[:480]
        ptokens = estimate_tokens(para)
        # A single oversized paragraph: hard-split it.
        if ptokens > target * 1.5:
            flush()
            words = para.split()
            step = max(1, target * 4 // 6)  # approx words per chunk
            for i in range(0, len(words), step):
                piece = " ".join(words[i : i + step])
                chunks.append(
                    TextChunk(
                        ordinal=ordinal,
                        text=piece,
                        token_estimate=estimate_tokens(piece),
                        section_heading=heading,
                        page_number=page_number,
                    )
                )
                ordinal += 1
            continue
        if current_tokens + ptokens > target and current:
            flush()
            # Overlap: carry the tail of the previous chunk forward.
            if overlap > 0 and chunks:
                tail = chunks[-1].text[-overlap * 4 :]
                current.append(tail)
                current_tokens += estimate_tokens(tail)
        current.append(para)
        current_tokens += ptokens
    flush()
    return chunks


def chunk_document(result: ExtractionResult) -> list[TextChunk]:
    target = settings.chunk_target_tokens
    overlap = settings.chunk_overlap_tokens
    chunks: list[TextChunk] = []
    if result.segments:
        for seg in result.segments:
            seg_chunks = _chunk_segment(
                seg.text, len(chunks), seg.page_number, target, overlap
            )
            chunks.extend(seg_chunks)
    else:
        chunks = _chunk_segment(result.text, 0, None, target, overlap)
    # Re-number ordinals sequentially.
    for i, c in enumerate(chunks):
        c.ordinal = i
    return chunks
