from __future__ import annotations

import uuid

import pytest

from app.config import settings
from app.core.security import hash_password
from app.models.audit import Engagement
from app.models.organization import Organization, User
from app.services import actions


def _org_user(db):
    org = Organization(name="A", slug="a-" + uuid.uuid4().hex[:6])
    db.add(org)
    db.flush()
    u = User(organization_id=org.id, email=f"u-{uuid.uuid4().hex[:6]}@x.test", hashed_password=hash_password("x"), role="admin")
    db.add(u)
    db.commit()
    return org, u


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "actions_enabled", True)
    monkeypatch.setattr(settings, "action_scope_allowlist", '["127.0.0.1/32"]')
    monkeypatch.setattr(settings, "allowed_apps", '{"demo": ["/bin/echo", "hi"]}')
    yield


def test_disabled_by_default_fails_closed(db, monkeypatch):
    monkeypatch.setattr(settings, "actions_enabled", False)
    org, _ = _org_user(db)
    with pytest.raises(actions.ActionError):
        actions.authorize_target(db, org.id, "127.0.0.1")


def test_allowlist_authorizes_loopback_only(db, enabled):
    org, _ = _org_user(db)
    actions.authorize_target(db, org.id, "127.0.0.1")  # no raise
    with pytest.raises(actions.ActionError):
        actions.authorize_target(db, org.id, "10.0.0.5")


def test_invalid_target_rejected(db, enabled):
    org, _ = _org_user(db)
    for bad in ["foo; rm -rf /", "1.2.3.4 && x", "$(whoami)", "a b"]:
        with pytest.raises(actions.ActionError):
            actions.authorize_target(db, org.id, bad)


def test_engagement_scope_authorizes_and_excludes(db, enabled):
    org, _ = _org_user(db)
    db.add(
        Engagement(
            organization_id=org.id,
            name="lab",
            allowed_ip_ranges='["192.168.56.0/24"]',
            excluded_assets='["192.168.56.1"]',
            authorization_status="authorized",
        )
    )
    db.commit()
    actions.authorize_target(db, org.id, "192.168.56.10")  # in scope
    with pytest.raises(actions.ActionError):
        actions.authorize_target(db, org.id, "192.168.56.1")  # excluded
    with pytest.raises(actions.ActionError):
        actions.authorize_target(db, org.id, "192.168.99.9")  # out of scope


def test_pending_engagement_not_authorized(db, enabled):
    org, _ = _org_user(db)
    db.add(
        Engagement(
            organization_id=org.id,
            name="pending",
            allowed_ip_ranges='["10.10.0.0/16"]',
            authorization_status="pending",  # not authorized -> fail closed
        )
    )
    db.commit()
    with pytest.raises(actions.ActionError):
        actions.authorize_target(db, org.id, "10.10.0.5")


def test_run_nmap_builds_safe_argv_no_shell(db, enabled, monkeypatch):
    org, _ = _org_user(db)
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = "Nmap scan report for 127.0.0.1\n"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["shell"] = kwargs.get("shell")
        return FakeProc()

    monkeypatch.setattr(actions.subprocess, "run", fake_run)
    res = actions.run_nmap(db, org.id, "127.0.0.1", profile="quick")
    assert res.ok
    assert isinstance(captured["argv"], list)
    assert captured["argv"][0] == settings.nmap_binary
    assert captured["argv"][-1] == "127.0.0.1"
    assert captured["shell"] is False
    # Profile flags present; no output/report-file flags injected.
    assert "-F" in captured["argv"]
    assert not any(a.startswith("-o") for a in captured["argv"])


def test_run_nmap_rejects_bad_ports_before_exec(db, enabled, monkeypatch):
    org, _ = _org_user(db)
    called = {"run": False}
    monkeypatch.setattr(actions.subprocess, "run", lambda *a, **k: called.__setitem__("run", True))
    with pytest.raises(actions.ActionError):
        actions.run_nmap(db, org.id, "127.0.0.1", profile="quick", ports="80;22")
    assert called["run"] is False


def test_run_nmap_unknown_profile(db, enabled):
    org, _ = _org_user(db)
    with pytest.raises(actions.ActionError):
        actions.run_nmap(db, org.id, "127.0.0.1", profile="evil")


def test_launch_app_allowlist(db, enabled, monkeypatch):
    launched = {}
    monkeypatch.setattr(actions.subprocess, "Popen", lambda argv, **k: launched.setdefault("argv", argv))
    res = actions.launch_app("demo")
    assert res.ok
    assert launched["argv"] == ["/bin/echo", "hi"]
    with pytest.raises(actions.ActionError):
        actions.launch_app("rm")  # not in allowlist
