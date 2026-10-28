"""SSRF-resistant outbound URL fetcher.

Defenses implemented:
  * Only http/https schemes are permitted.
  * The hostname is resolved and EVERY resolved address is validated against
    loopback, private, link-local (incl. 169.254.169.254 cloud metadata),
    multicast, reserved and unspecified ranges (IPv4 and IPv6, incl.
    IPv4-mapped IPv6).
  * The connection is pinned to a validated IP address, so the address used by
    the TCP connection is the one that was checked (mitigates DNS rebinding /
    TOCTOU between resolution and connection). TLS still verifies the real
    hostname via SNI.
  * Redirects are followed manually and each hop's destination is re-validated.
  * Response size, total time and content-type are bounded; credentials are
    never forwarded to a redirect target on a different origin.

This is defense in depth: it does not rely on a single string check or a single
DNS lookup.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx

from app.config import settings

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/json",
    "application/xml",
    "text/xml",
    "application/xhtml+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class SsrfError(Exception):
    """Raised when a URL is rejected by the SSRF policy."""


class FetchError(Exception):
    """Raised when a URL could not be fetched (network/size/type)."""


@dataclass
class FetchResult:
    content: bytes
    content_type: str
    final_url: str


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    # Unwrap IPv4-mapped IPv6 (::ffff:a.b.c.d) so the embedded v4 is checked.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_and_validate(host: str) -> list[str]:
    """Resolve host to IPs and validate all of them. Returns safe IP strings."""
    # Reject bare IP literals that are themselves disallowed, and validate.
    try:
        literal = ipaddress.ip_address(host)
        if settings.allow_private_url_fetch:
            return [str(literal)]
        if _ip_is_blocked(literal):
            raise SsrfError(f"Blocked IP address: {host}")
        return [str(literal)]
    except ValueError:
        pass  # not an IP literal; resolve by name

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"DNS resolution failed for {host}: {exc}") from exc

    ips: list[str] = []
    for info in infos:
        ip_str = info[4][0]
        ip = ipaddress.ip_address(ip_str)
        if not settings.allow_private_url_fetch and _ip_is_blocked(ip):
            raise SsrfError(f"Host {host} resolves to blocked address {ip_str}")
        ips.append(ip_str)
    if not ips:
        raise FetchError(f"No addresses resolved for {host}")
    # De-dup while preserving order.
    return list(dict.fromkeys(ips))


def _validate_url(url: str) -> tuple[str, int, list[str]]:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SsrfError(f"Scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise SsrfError("URL has no host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ips = _resolve_and_validate(host)
    return host, port, ips


def _read_capped(resp: httpx.Response, cap: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_bytes():
        total += len(chunk)
        if total > cap:
            raise FetchError(f"Response exceeded size limit of {cap} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_url(url: str, *, client: httpx.Client | None = None) -> FetchResult:
    """Fetch a URL safely, following and re-validating redirects.

    A custom ``client`` may be injected for testing (e.g. with a MockTransport).
    """
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=settings.url_fetch_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "SecBrain-Ingestor/1.0"},
        )
    try:
        current = url
        for _hop in range(settings.url_fetch_max_redirects + 1):
            host, port, ips = _validate_url(current)
            parsed = urlparse(current)
            # Pin the connection to the first validated IP; keep Host + SNI as
            # the real hostname so TLS verification and vhosts still work.
            pinned_netloc = f"{ips[0]}:{port}"
            pinned_url = urlunparse(parsed._replace(netloc=pinned_netloc))
            extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}
            request = client.build_request(
                "GET",
                pinned_url,
                headers={"Host": host if port in (80, 443) else f"{host}:{port}"},
                extensions=extensions,
            )
            resp = client.send(request, stream=True)
            try:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise FetchError("Redirect without Location header")
                    # Resolve relative redirects against the original hostname.
                    current = str(httpx.URL(current).join(location))
                    resp.close()
                    continue
                if resp.status_code >= 400:
                    raise FetchError(f"HTTP {resp.status_code} fetching {url}")
                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                    raise FetchError(f"Unexpected content type: {content_type!r}")
                data = _read_capped(resp, settings.url_fetch_max_bytes)
                return FetchResult(
                    content=data,
                    content_type=content_type or "text/html",
                    final_url=str(resp.url),
                )
            finally:
                resp.close()
        raise FetchError("Too many redirects")
    finally:
        if owns_client:
            client.close()
