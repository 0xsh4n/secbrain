from __future__ import annotations

from app.services import extraction
from app.services.chunking import chunk_document
from app.services.extraction import ExtractionResult


def test_extract_plain_text():
    res = extraction.extract("txt", b"Hello\r\nworld\n\n\n\nend")
    assert "Hello" in res.text
    assert "\r" not in res.text


def test_extract_markdown_title():
    res = extraction.extract("markdown", b"# My Title\n\nbody text here")
    assert res.title == "My Title"


def test_extract_html_strips_scripts_and_gets_title():
    html = b"<html><head><title>Doc</title></head><body><script>bad()</script><p>keep this</p></body></html>"
    res = extraction.extract("html", html)
    assert res.title == "Doc"
    assert "keep this" in res.text
    assert "bad()" not in res.text


def test_chunking_respects_headings_and_order():
    text = "# Intro\n\n" + ("word " * 400) + "\n\n## Section Two\n\n" + ("alpha " * 400)
    result = ExtractionResult(text=text)
    chunks = chunk_document(result)
    assert len(chunks) >= 2
    # Ordinals are sequential and start at 0.
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    # A heading is captured on at least one chunk.
    assert any(c.section_heading for c in chunks)


def test_chunking_pages_from_segments():
    from app.services.extraction import PageSegment

    result = ExtractionResult(
        text="",
        segments=[PageSegment(1, "page one content " * 50), PageSegment(2, "page two content " * 50)],
    )
    chunks = chunk_document(result)
    pages = {c.page_number for c in chunks}
    assert pages == {1, 2}
