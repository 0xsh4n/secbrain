from __future__ import annotations

from app.config import settings
from app.services import actions


def test_execute_disabled_returns_409(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "actions_enabled", False)
    r = client.post(
        "/api/v1/actions/execute",
        headers=auth_headers,
        json={"action": "nmap", "nmap": {"target": "127.0.0.1", "profile": "quick"}},
    )
    assert r.status_code == 409


def test_execute_requires_session_not_api_key(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "actions_enabled", True)
    # Create an API key, then try to use it against the actions endpoint.
    key = client.post("/api/v1/apikeys", headers=auth_headers, json={"name": "k"}).json()["api_key"]
    r = client.post(
        "/api/v1/actions/execute",
        headers={"X-API-Key": key},
        json={"action": "nmap", "nmap": {"target": "127.0.0.1"}},
    )
    assert r.status_code == 403  # require_admin rejects API-key auth


def test_execute_nmap_in_scope(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "actions_enabled", True)
    monkeypatch.setattr(settings, "action_scope_allowlist", '["127.0.0.1/32"]')

    def fake_run(db, org, target, profile="quick", ports=None):
        return actions.ActionResult(action="nmap", ok=True, detail=f"{profile} {target}", output="report")

    monkeypatch.setattr(actions, "run_nmap", fake_run)
    r = client.post(
        "/api/v1/actions/execute",
        headers=auth_headers,
        json={"action": "nmap", "nmap": {"target": "127.0.0.1", "profile": "quick"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_execute_out_of_scope_refused(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "actions_enabled", True)
    monkeypatch.setattr(settings, "action_scope_allowlist", '["127.0.0.1/32"]')
    r = client.post(
        "/api/v1/actions/execute",
        headers=auth_headers,
        json={"action": "nmap", "nmap": {"target": "8.8.8.8", "profile": "quick"}},
    )
    assert r.status_code == 403


def test_parse_command(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "actions_enabled", True)
    r = client.post("/api/v1/actions/parse", headers=auth_headers, json={"text": "scan service 127.0.0.1"})
    body = r.json()
    assert body["action"] == "nmap"
    assert body["nmap"]["target"] == "127.0.0.1"
    assert body["nmap"]["profile"] == "service"

    r2 = client.post("/api/v1/actions/parse", headers=auth_headers, json={"text": "open firefox"})
    assert r2.json()["action"] == "launch_app"
    assert r2.json()["launch"]["name"] == "firefox"
