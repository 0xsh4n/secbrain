from __future__ import annotations

import httpx
import pytest

from app.services import url_fetcher
from app.services.url_fetcher import FetchError, SsrfError, fetch_url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "file:///etc/passwd",
        "gopher://example.com",
        "http://",
    ],
)
def test_rejects_non_http_schemes(url):
    with pytest.raises(SsrfError):
        url_fetcher._validate_url(url)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost" if False else "10.0.0.5",
        "169.254.169.254",  # cloud metadata
        "192.168.1.1",
        "172.16.5.4",
        "::1",
        "0.0.0.0",
    ],
)
def test_blocks_private_and_metadata_ips(host):
    with pytest.raises(SsrfError):
        url_fetcher._resolve_and_validate(host)


def test_blocks_hostname_resolving_to_private(monkeypatch):
    # Simulate a DNS name that resolves to a private address.
    def fake_getaddrinfo(host, *a, **k):
        return [(2, 1, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(url_fetcher.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(SsrfError):
        url_fetcher._resolve_and_validate("sneaky.internal.example")


def test_blocks_ipv4_mapped_ipv6():
    with pytest.raises(SsrfError):
        url_fetcher._resolve_and_validate("::ffff:127.0.0.1")


def _public_resolver(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(url_fetcher.socket, "getaddrinfo", fake_getaddrinfo)


def test_fetches_public_url_with_pinned_ip(monkeypatch):
    _public_resolver(monkeypatch)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host_header"] = request.headers.get("host")
        seen["url_host"] = request.url.host
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<h1>ok</h1>")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    result = fetch_url("https://example.com/page", client=client)
    assert result.content_type == "text/html"
    assert b"ok" in result.content
    # Connection was pinned to the validated IP, not the hostname.
    assert seen["url_host"] == "93.184.216.34"
    assert seen["host_header"].startswith("example.com")


def test_redirect_to_internal_is_blocked(monkeypatch):
    _public_resolver(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    with pytest.raises(SsrfError):
        fetch_url("https://example.com/redir", client=client)


def test_rejects_unexpected_content_type(monkeypatch):
    _public_resolver(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=b"x")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    with pytest.raises(FetchError):
        fetch_url("https://example.com/file", client=client)
