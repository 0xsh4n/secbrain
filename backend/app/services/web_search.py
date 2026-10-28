"""Small, keyless DuckDuckGo HTML search adapter for opt-in chat grounding."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass
class WebResult:
    title: str
    url: str
    snippet: str


def search_web(query: str, limit: int = 5) -> list[WebResult]:
    """Return a few public web snippets; callers must treat them as untrusted."""
    response = httpx.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query[:500]},
        headers={"User-Agent": "SecBrain/1.0 (optional chat web search)"},
        timeout=httpx.Timeout(10.0, connect=4.0),
        follow_redirects=True,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results: list[WebResult] = []
    seen: set[str] = set()
    for node in soup.select(".result"):
        anchor = node.select_one("a.result__a")
        snippet_node = node.select_one(".result__snippet")
        if not anchor:
            continue
        href = str(anchor.get("href") or "")
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc:
            href = parse_qs(parsed.query).get("uddg", [""])[0]
        target = urlparse(href)
        if target.scheme != "https" or not target.hostname or target.hostname.endswith("duckduckgo.com") or href in seen:
            continue
        title = anchor.get_text(" ", strip=True)
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
        if not title:
            continue
        results.append(WebResult(title=title[:300], url=href[:2048], snippet=snippet[:1200]))
        seen.add(href)
        if len(results) >= max(1, min(limit, 8)):
            break
    return results
