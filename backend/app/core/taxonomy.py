"""Security knowledge taxonomy and security-identifier extraction."""
from __future__ import annotations

import re

# Initial security domain categories (used for collections + metadata).
SECURITY_CATEGORIES: list[str] = [
    "web-application-security",
    "api-security",
    "mobile-security",
    "cloud-security",
    "network-security",
    "active-directory-identity",
    "authentication-authorization",
    "cryptography",
    "vulnerability-research",
    "secure-development",
    "malware-analysis",
    "digital-forensics",
    "ot-ics-security",
    "penetration-testing-methodology",
    "bug-bounty-research",
    "threat-intelligence",
    "internal-security-research",
]

# Regexes for exact security identifiers (used to boost keyword retrieval).
_PATTERNS: dict[str, re.Pattern[str]] = {
    "cve": re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE),
    "cwe": re.compile(r"\bCWE-\d{1,5}\b", re.IGNORECASE),
    "capec": re.compile(r"\bCAPEC-\d{1,5}\b", re.IGNORECASE),
    # MITRE ATT&CK technique ids, e.g. T1059 or T1059.001
    "attack": re.compile(r"\bT\d{4}(?:\.\d{3})?\b"),
}


def extract_identifiers(text: str) -> dict[str, list[str]]:
    """Return normalized security identifiers found in text, grouped by kind."""
    found: dict[str, list[str]] = {}
    for kind, pattern in _PATTERNS.items():
        matches = {m.upper() for m in pattern.findall(text or "")}
        if matches:
            found[kind] = sorted(matches)
    return found


def all_identifiers(text: str) -> list[str]:
    """Flat, de-duplicated list of all identifiers found in text."""
    out: list[str] = []
    for ids in extract_identifiers(text).values():
        out.extend(ids)
    return out
