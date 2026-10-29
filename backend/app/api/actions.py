from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Principal, client_ip, require_admin
from app.db import get_db
from app.services import actions, audit

router = APIRouter(prefix="/actions", tags=["actions"])


class NmapParams(BaseModel):
    target: str = Field(min_length=1, max_length=253)
    profile: Literal["quick", "service", "top100", "ping"] = "quick"
    ports: str | None = Field(default=None, max_length=64)


class LaunchParams(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ExecuteRequest(BaseModel):
    action: Literal["nmap", "launch_app"]
    nmap: NmapParams | None = None
    launch: LaunchParams | None = None


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.get("")
def list_available(_principal: Principal = Depends(require_admin)) -> dict:
    return actions.list_actions()


@router.post("/execute")
def execute(
    payload: ExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    if not actions.actions_enabled():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "System actions are disabled. Set SECBRAIN_ACTIONS_ENABLED=true to enable.",
        )
    org = principal.user.organization_id
    try:
        if payload.action == "nmap":
            if payload.nmap is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Missing nmap params")
            result = actions.run_nmap(
                db, org, payload.nmap.target, payload.nmap.profile, payload.nmap.ports
            )
        elif payload.action == "launch_app":
            if payload.launch is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Missing launch params")
            result = actions.launch_app(payload.launch.name)
        else:  # pragma: no cover - guarded by schema
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown action")
    except actions.ActionError as exc:
        audit.record(
            db,
            organization_id=org,
            action="action.refused",
            actor_id=principal.user.id,
            resource_type="action",
            resource_id=payload.action,
            detail=str(exc)[:200],
            ip_address=client_ip(request),
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))

    audit.record(
        db,
        organization_id=org,
        action="action.execute",
        actor_id=principal.user.id,
        resource_type="action",
        resource_id=result.action,
        detail=result.detail[:200],
        ip_address=client_ip(request),
    )
    return {"ok": result.ok, "action": result.action, "detail": result.detail, "output": result.output}


# --- Non-executing command parser (helper for the voice/chat UI) ------------
_SCAN_RE = re.compile(r"\b(?:scan|nmap)\b\s+(?:(?P<prof>quick|service|top100|ping)\s+)?(?P<target>[A-Za-z0-9.\-/]+)", re.I)
_OPEN_RE = re.compile(r"\b(?:open|launch|start)\b\s+(?P<app>[A-Za-z0-9 _.\-]+)", re.I)


@router.post("/parse")
def parse_command(payload: ParseRequest, _principal: Principal = Depends(require_admin)) -> dict:
    """Parse a user utterance into a STRUCTURED command suggestion. Does NOT
    execute. The UI confirms with the user before calling /execute."""
    text = payload.text.strip()
    m = _SCAN_RE.search(text)
    if m:
        return {
            "action": "nmap",
            "nmap": {
                "target": m.group("target"),
                "profile": (m.group("prof") or "quick").lower(),
                "ports": None,
            },
            "confirm": f"Run nmap '{(m.group('prof') or 'quick').lower()}' scan on {m.group('target')}?",
        }
    m = _OPEN_RE.search(text)
    if m:
        name = m.group("app").strip().split()[0].lower()
        return {
            "action": "launch_app",
            "launch": {"name": name},
            "confirm": f"Open application '{name}'?",
        }
    return {"action": None}
