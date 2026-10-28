"""Security metadata suggestion.

Heuristic extraction (identifiers, keyword-based category guess) always runs and
needs no model. When a generation model is configured, a richer summary can be
requested, but ingestion never depends on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.taxonomy import SECURITY_CATEGORIES, all_identifiers

# Keyword hints mapping free text -> security category.
_CATEGORY_HINTS: dict[str, str] = {
    "xss": "web-application-security",
    "sql injection": "web-application-security",
    "csrf": "web-application-security",
    "ssrf": "web-application-security",
    "owasp": "web-application-security",
    "api ": "api-security",
    "rest ": "api-security",
    "graphql": "api-security",
    "android": "mobile-security",
    "ios ": "mobile-security",
    "apk": "mobile-security",
    "certificate pinning": "mobile-security",
    "aws": "cloud-security",
    "azure": "cloud-security",
    "s3 bucket": "cloud-security",
    "kubernetes": "cloud-security",
    "firewall": "network-security",
    "tcp": "network-security",
    "kerberos": "active-directory-identity",
    "active directory": "active-directory-identity",
    "ntlm": "active-directory-identity",
    "oauth": "authentication-authorization",
    "jwt": "authentication-authorization",
    "saml": "authentication-authorization",
    "aes": "cryptography",
    "rsa": "cryptography",
    "tls": "cryptography",
    "cve-": "vulnerability-research",
    "malware": "malware-analysis",
    "ransomware": "malware-analysis",
    "forensic": "digital-forensics",
    "scada": "ot-ics-security",
    "modbus": "ot-ics-security",
    "pentest": "penetration-testing-methodology",
    "bug bounty": "bug-bounty-research",
    "threat actor": "threat-intelligence",
    "apt": "threat-intelligence",
}


@dataclass
class SuggestedMetadata:
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)


def suggest_metadata(title: str, text: str) -> SuggestedMetadata:
    sample = f"{title}\n{text[:8000]}".lower()
    categories: list[str] = []
    tags: list[str] = []
    for hint, category in _CATEGORY_HINTS.items():
        if hint in sample:
            if category not in categories:
                categories.append(category)
            tags.append(hint.strip())
    identifiers = all_identifiers(f"{title}\n{text}")
    # Keep category list to known taxonomy, cap tags.
    categories = [c for c in categories if c in SECURITY_CATEGORIES][:5]
    tags = sorted(set(t for t in tags if t))[:12]
    return SuggestedMetadata(categories=categories, tags=tags, identifiers=identifiers[:30])
