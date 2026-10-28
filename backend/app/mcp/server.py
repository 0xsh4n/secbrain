"""Minimal MCP (Model Context Protocol) stdio server for SecBrain.

This is a dependency-free JSON-RPC 2.0 server over stdio exposing the read-only
tools in ``tools.py``. Messages are newline-delimited JSON objects (one request
per line, one response per line).

Authentication: the server requires a SecBrain API key in the environment
variable ``SECBRAIN_MCP_API_KEY``. The key is resolved to a user and its
collection scope, and every tool call enforces the same authorization as the
REST API. The server has NO filesystem, shell, browser or outbound-network
access of its own — it only talks to the SecBrain database via the service
layer.

Run (from backend/, venv active):
    SECBRAIN_MCP_API_KEY=sk_secbrain_... python -m app.mcp.server

See docs/API.md for how to wire an MCP-compatible client.
"""
from __future__ import annotations

import json
import os
import sys

from app.core.security import hash_api_key
from app.db import SessionLocal
from app.mcp.tools import TOOL_DEFS, McpPrincipal, ToolError, call_tool
from app.models.apikey import ApiKey
from app.models.mixins import utcnow
from app.models.organization import User

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "secbrain-mcp", "version": "1.0.0"}


def _resolve_principal(db) -> McpPrincipal:
    raw = os.environ.get("SECBRAIN_MCP_API_KEY", "").strip()
    if not raw:
        raise ToolError("SECBRAIN_MCP_API_KEY is not set")
    from sqlalchemy import select

    key = db.execute(
        select(ApiKey).where(ApiKey.hashed_key == hash_api_key(raw))
    ).scalars().first()
    if key is None or not key.is_active:
        raise ToolError("Invalid or revoked API key")
    if key.expires_at is not None and key.expires_at < utcnow():
        raise ToolError("API key expired")
    user = db.get(User, key.user_id)
    if user is None or not user.is_active:
        raise ToolError("Owning user inactive")
    scoped = json.loads(key.scoped_collection_ids or "[]")
    return McpPrincipal(user=user, scoped_collection_ids=scoped)


def handle_request(message: dict) -> dict | None:
    """Pure request handler (testable). Returns a JSON-RPC response or None for
    notifications."""
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def err(code, msg):
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": msg}}

    if method == "initialize":
        return ok(
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        )
    if method in ("notifications/initialized", "initialized"):
        return None  # notification, no response
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOL_DEFS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        db = SessionLocal()
        try:
            principal = _resolve_principal(db)
            result = call_tool(name, db, principal, args)
            return ok(
                {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                    "isError": False,
                }
            )
        except ToolError as exc:
            return ok(
                {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            )
        except Exception as exc:  # never leak internals
            return err(-32603, f"Internal error: {type(exc).__name__}")
        finally:
            db.close()
    return err(-32601, f"Method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n"
            )
            sys.stdout.flush()
            continue
        response = handle_request(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
