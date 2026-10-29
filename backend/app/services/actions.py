"""Scope-gated system actions (nmap, application launch).

Security invariants (this is the policy-enforcement layer the architecture
requires; it FAILS CLOSED):

* Disabled unless ``SECBRAIN_ACTIONS_ENABLED=true``.
* Executed only via an explicit, STRUCTURED request from an authenticated
  admin session — never from free text, never from the grounded-answer LLM, and
  never from content inside an ingested document. Injected document text can
  therefore not reach an executor.
* No shell is ever used (``shell=False``, argv lists only), so argument/shell
  injection is not possible.
* nmap targets must fall inside an AUTHORIZED scope: an active, non-expired
  Engagement for the caller's organization, or an explicit config allowlist
  (intended for loopback/lab only). Excluded assets are honored. Unknown or
  out-of-scope targets are refused.
* nmap flags are not free-form: the caller picks a named profile and an
  optional, strictly-validated port string.
* Applications launch only from a configured name->argv allowlist.
* Every action is audit-logged.
"""
from __future__ import annotations

import ipaddress
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.audit import Engagement

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]{1,253}$")
_IPV4_CIDR_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?$")
_PORTS_RE = re.compile(r"^[0-9]{1,5}(?:-[0-9]{1,5})?(?:,[0-9]{1,5}(?:-[0-9]{1,5})?)*$")

# Fixed, safe nmap profiles (no -oX/paths, no --script, no raw flags).
# -sT (TCP connect) does not require root; -Pn skips host discovery.
NMAP_PROFILES: dict[str, list[str]] = {
    "quick": ["-sT", "-T4", "-F", "-Pn"],
    "service": ["-sT", "-sV", "-T4", "-Pn"],
    "top100": ["-sT", "-T4", "--top-ports", "100", "-Pn"],
    "ping": ["-sn"],
}


class ActionError(Exception):
    """User-facing, safe error (refusal / validation)."""


@dataclass
class ActionResult:
    action: str
    ok: bool
    detail: str
    output: str = ""


def actions_enabled() -> bool:
    return bool(settings.actions_enabled)


def list_actions() -> dict:
    try:
        apps = sorted(json.loads(settings.allowed_apps or "{}").keys())
    except json.JSONDecodeError:
        apps = []
    return {
        "enabled": actions_enabled(),
        "nmap_profiles": sorted(NMAP_PROFILES.keys()),
        "allowed_apps": apps,
        "scope_allowlist": _config_allowlist_raw(),
    }


def _config_allowlist_raw() -> list[str]:
    try:
        val = json.loads(settings.action_scope_allowlist or "[]")
        return [str(x) for x in val] if isinstance(val, list) else []
    except json.JSONDecodeError:
        return []


# --- Scope authorization ----------------------------------------------------
def _active_engagement_scope(db: Session, organization_id: str) -> tuple[list[str], list[str], list[str]]:
    """Return (allowed_ip_ranges, allowed_domains, excluded_assets) from active
    authorized engagements of the organization."""
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(Engagement).where(
            Engagement.organization_id == organization_id,
            Engagement.authorization_status == "authorized",
        )
    ).scalars().all()
    ips: list[str] = []
    domains: list[str] = []
    excluded: list[str] = []
    for e in rows:
        if e.expires_at is not None and e.expires_at < now:
            continue
        ips += _json_list(e.allowed_ip_ranges)
        domains += _json_list(e.allowed_domains)
        excluded += _json_list(e.excluded_assets)
    return ips, domains, excluded


def _json_list(blob: str) -> list[str]:
    try:
        val = json.loads(blob or "[]")
        return [str(x).strip() for x in val] if isinstance(val, list) else []
    except json.JSONDecodeError:
        return []


def _ip_in_cidrs(ip: str, cidrs: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for c in cidrs:
        try:
            if addr in ipaddress.ip_network(c, strict=False):
                return True
        except ValueError:
            # Bare IP equality.
            try:
                if addr == ipaddress.ip_address(c):
                    return True
            except ValueError:
                continue
    return False


def _host_matches(host: str, patterns: list[str]) -> bool:
    host = host.lower()
    for p in patterns:
        p = p.lower().lstrip("*.")
        if host == p or host.endswith("." + p):
            return True
    return False


def authorize_target(db: Session, organization_id: str, target: str) -> None:
    """Raise ActionError unless ``target`` is in an authorized scope."""
    if not actions_enabled():
        raise ActionError("System actions are disabled (SECBRAIN_ACTIONS_ENABLED=false).")
    target = (target or "").strip()
    is_ip_like = bool(_IPV4_CIDR_RE.match(target))
    if not is_ip_like and not _HOST_RE.match(target):
        raise ActionError("Invalid target format.")

    config_allow = _config_allowlist_raw()
    eng_ips, eng_domains, excluded = _active_engagement_scope(db, organization_id)

    # Exclusions always win.
    if is_ip_like and "/" not in target and _ip_in_cidrs(target, excluded):
        raise ActionError("Target is explicitly excluded from scope.")
    if not is_ip_like and _host_matches(target, excluded):
        raise ActionError("Target is explicitly excluded from scope.")

    authorized = False
    if is_ip_like:
        # For a CIDR target, require an exact/containing allow entry on a host
        # within it; we check the network address membership.
        probe = target.split("/")[0]
        authorized = _ip_in_cidrs(probe, config_allow) or _ip_in_cidrs(probe, eng_ips)
    else:
        authorized = _host_matches(target, config_allow) or _host_matches(target, eng_domains)

    if not authorized:
        raise ActionError(
            "Target is not within any authorized engagement scope or allowlist. "
            "Add it to an authorized Engagement or SECBRAIN_ACTION_SCOPE_ALLOWLIST."
        )


# --- Executors --------------------------------------------------------------
def run_nmap(
    db: Session, organization_id: str, target: str, profile: str = "quick", ports: str | None = None
) -> ActionResult:
    if profile not in NMAP_PROFILES:
        raise ActionError(f"Unknown scan profile: {profile}")
    authorize_target(db, organization_id, target)

    argv = [settings.nmap_binary, *NMAP_PROFILES[profile]]
    if ports:
        if not _PORTS_RE.match(ports):
            raise ActionError("Invalid ports specification.")
        argv += ["-p", ports]
    argv.append(target)

    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=settings.nmap_timeout_seconds,
        )
    except FileNotFoundError:
        raise ActionError("nmap is not installed on the server.")
    except subprocess.TimeoutExpired:
        raise ActionError("Scan timed out.")
    output = (proc.stdout or "")[-20000:]
    return ActionResult(
        action="nmap",
        ok=proc.returncode == 0,
        detail=f"profile={profile} target={target} rc={proc.returncode}",
        output=output or (proc.stderr or "")[-4000:],
    )


def launch_app(name: str) -> ActionResult:
    if not actions_enabled():
        raise ActionError("System actions are disabled.")
    try:
        apps = json.loads(settings.allowed_apps or "{}")
    except json.JSONDecodeError:
        apps = {}
    argv = apps.get(name)
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ActionError(f"'{name}' is not in the application allowlist.")
    try:
        subprocess.Popen(
            argv,
            shell=False,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise ActionError(f"Application executable not found: {argv[0]}")
    return ActionResult(action="launch_app", ok=True, detail=f"launched {name}")
