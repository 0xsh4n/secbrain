"""Content-only two-way sync to a user's Google Drive knowledge pool."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, require_session
from app.api.documents import _accessible_documents, _backup_source_url, _create_and_queue, _resolve_tags
from app.config import settings
from app.core.slugs import slugify
from app.db import get_db
from app.models.collection import Collection
from app.models.document import Document
from app.models.organization import User

router = APIRouter(prefix="/drive-sync", tags=["drive-sync"])
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"
POOL_NAME = "SecBrain Knowledge Pool"
_SYNC_LOCK = Lock()
_SYNC_DOC_LIMIT = 3
_SYNC_TEXT_LIMIT_BYTES = 16 * 1024 * 1024


def _configured() -> bool:
    return bool(settings.google_drive_client_id and settings.google_drive_client_secret)


def _path(user_id: str) -> Path:
    folder = Path(settings.storage_dir).resolve() / "drive-sync"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (hashlib.sha256(user_id.encode()).hexdigest() + ".enc")


def _fernet() -> Fernet:
    key = hashlib.sha256((settings.secret_key + ":drive-sync-v1").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _read(user_id: str) -> dict | None:
    path = _path(user_id)
    if not path.exists():
        return None
    try:
        return json.loads(_fernet().decrypt(path.read_bytes()))
    except (InvalidToken, json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)
        return None


def _write(user_id: str, value: dict) -> None:
    _path(user_id).write_bytes(_fernet().encrypt(json.dumps(value).encode()))


def _request(method: str, url: str, token: str, **kwargs):
    headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
    try:
        response = httpx.request(method, url, headers=headers, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google Drive request failed; reconnect if authorization expired") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not reach Google Drive") from exc


def _refresh(user_id: str, creds: dict) -> dict:
    try:
        response = httpx.post(TOKEN_URL, data={"client_id": settings.google_drive_client_id, "client_secret": settings.google_drive_client_secret, "refresh_token": creds["refresh_token"], "grant_type": "refresh_token"}, timeout=20)
        response.raise_for_status()
        creds["access_token"] = response.json()["access_token"]
        _write(user_id, creds)
        return creds
    except (httpx.HTTPError, KeyError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Reconnect Google Drive to continue sync") from exc


def _drive(user_id: str, creds: dict, method: str, url: str, **kwargs):
    try:
        return _request(method, url, creds["access_token"], **kwargs)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_502_BAD_GATEWAY or not creds.get("refresh_token"):
            raise
        creds = _refresh(user_id, creds)
        return _request(method, url, creds["access_token"], **kwargs)


@router.get("/status")
def sync_status(principal: Principal = Depends(require_session)):
    creds = _read(principal.user.id)
    return {"configured": _configured(), "connected": bool(creds), "email": creds.get("email", "") if creds else "", "last_sync": creds.get("last_sync", "") if creds else ""}


@router.get("/connect")
def connect(principal: Principal = Depends(require_session)):
    if not _configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Drive OAuth is not configured")
    from datetime import timedelta
    state = jwt.encode({"sub": principal.user.id, "org": principal.user.organization_id, "nonce": secrets.token_urlsafe(16), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, settings.secret_key, algorithm="HS256")
    query = urlencode({"client_id": settings.google_drive_client_id, "redirect_uri": settings.google_drive_redirect_uri, "response_type": "code", "scope": "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/userinfo.email", "access_type": "offline", "prompt": "consent", "state": state})
    return {"authorization_url": f"{AUTH_URL}?{query}"}


@router.get("/callback")
def callback(code: str, state: str):
    try:
        claims = jwt.decode(state, settings.secret_key, algorithms=["HS256"])
        user_id, org_id = claims["sub"], claims["org"]
    except (jwt.PyJWTError, KeyError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Google authorization state") from exc
    if not _configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Drive OAuth is not configured")
    try:
        response = httpx.post(TOKEN_URL, data={"code": code, "client_id": settings.google_drive_client_id, "client_secret": settings.google_drive_client_secret, "redirect_uri": settings.google_drive_redirect_uri, "grant_type": "authorization_code"}, timeout=20)
        response.raise_for_status()
        tokens = response.json()
        profile = httpx.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=20)
        profile.raise_for_status()
    except (httpx.HTTPError, KeyError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google authorization could not be completed") from exc
    _write(user_id, {"organization_id": org_id, "access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token", ""), "email": profile.json().get("email", ""), "folder_id": "", "last_sync": ""})
    return RedirectResponse(settings.google_drive_frontend_url.rstrip("/") + "/settings?drive=connected")


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(principal: Principal = Depends(require_session)):
    _path(principal.user.id).unlink(missing_ok=True)


def _folder(user_id: str, creds: dict) -> str:
    if creds.get("folder_id"):
        return creds["folder_id"]
    query = "name='SecBrain Knowledge Pool' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    found = _drive(user_id, creds, "GET", f"{DRIVE_API}/files", params={"q": query, "fields": "files(id,name)", "pageSize": 100}).get("files", [])
    folder_id = next((f["id"] for f in found if f.get("name") == POOL_NAME), None)
    if not folder_id:
        folder_id = _drive(user_id, creds, "POST", f"{DRIVE_API}/files", json={"name": POOL_NAME, "mimeType": "application/vnd.google-apps.folder"}, params={"fields": "id"})["id"]
    creds["folder_id"] = folder_id
    _write(user_id, creds)
    return folder_id


def _files(user_id: str, creds: dict, folder_id: str) -> list[dict]:
    results, page_token = [], None
    while True:
        params = {"q": f"'{folder_id}' in parents and trashed=false", "fields": "nextPageToken,files(id,name,size)", "pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        page = _drive(user_id, creds, "GET", f"{DRIVE_API}/files", params=params)
        results.extend(page.get("files", []))
        page_token = page.get("nextPageToken")
        if not page_token:
            return results


def _upload(user_id: str, creds: dict, folder_id: str, record: dict) -> None:
    name = f"{record['content_hash']}.json"
    boundary = "secbrain_content_only"
    metadata = json.dumps({"name": name, "mimeType": "application/json", "parents": [folder_id]}).encode()
    content = json.dumps(record, ensure_ascii=False).encode()
    body = b"--" + boundary.encode() + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + metadata + b"\r\n--" + boundary.encode() + b"\r\nContent-Type: application/json\r\n\r\n" + content + b"\r\n--" + boundary.encode() + b"--"
    _drive(user_id, creds, "POST", "https://www.googleapis.com/upload/drive/v3/files", params={"uploadType": "multipart", "fields": "id"}, content=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"})


def _sync_once(background: BackgroundTasks, db: Session, principal: Principal):
    user = principal.user
    creds = _read(user.id)
    if not creds:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect Google Drive before syncing")
    if creds.get("organization_id") != user.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Google Drive account is linked to another workspace")
    folder_id = _folder(user.id, creds)
    remote_files = _files(user.id, creds, folder_id)
    remote_names = {item.get("name") for item in remote_files}
    local_docs = _accessible_documents(db, principal)
    hashes = {hashlib.sha256(d.extracted_text.encode()).hexdigest() for d in local_docs if d.extracted_text}
    hash_names = {f"{digest}.json" for digest in hashes}
    pushed = pulled = skipped = 0
    uploaded_bytes = 0
    uploaded_docs = 0
    for doc in local_docs:
        if doc.status != "indexed" or not doc.extracted_text:
            continue
        digest = hashlib.sha256(doc.extracted_text.encode()).hexdigest()
        if f"{digest}.json" in remote_names:
            continue
        text_bytes = len(doc.extracted_text.encode())
        if text_bytes > _SYNC_TEXT_LIMIT_BYTES:
            skipped += 1
            continue
        if uploaded_docs >= _SYNC_DOC_LIMIT or (uploaded_docs and uploaded_bytes + text_bytes > _SYNC_TEXT_LIMIT_BYTES):
            break
        _upload(user.id, creds, folder_id, {"version": 1, "content_hash": digest, "title": doc.title, "source_type": doc.source_type, "source_url": _backup_source_url(doc.source_url), "author": doc.author, "summary": doc.summary, "tags": [tag.name for tag in doc.tags], "text": doc.extracted_text})
        remote_names.add(f"{digest}.json")
        pushed += 1
        uploaded_docs += 1
        uploaded_bytes += text_bytes

    collection = db.execute(select(Collection).where(Collection.organization_id == user.organization_id, Collection.owner_id == user.id, Collection.slug == slugify(POOL_NAME))).scalars().first()
    if collection is None:
        collection = Collection(organization_id=user.organization_id, owner_id=user.id, name=POOL_NAME, slug=slugify(POOL_NAME), description="Knowledge synced from your Google Drive account.", visibility="private")
        db.add(collection)
        db.commit()
        db.refresh(collection)
    for item in remote_files:
        name = item.get("name", "")
        if not name.endswith(".json") or name in hash_names:
            continue
        try:
            if int(item.get("size") or 0) > _SYNC_TEXT_LIMIT_BYTES:
                skipped += 1
                continue
            record = _drive(user.id, creds, "GET", f"{DRIVE_API}/files/{item['id']}", params={"alt": "media"})
            if not isinstance(record, dict):
                skipped += 1
                continue
            text = record.get("text")
            digest = hashlib.sha256(text.encode()).hexdigest() if isinstance(text, str) else ""
            if record.get("version") != 1 or not text or digest != record.get("content_hash") or name != f"{digest}.json":
                skipped += 1
                continue
            created = _create_and_queue(db, principal, background, title=str(record.get("title") or "Synced knowledge")[:500], source_type="text", source_url=_backup_source_url(str(record.get("source_url") or "")), inline_text=text, collection_ids=[collection.id], byte_size=len(text.encode()))
            created.author = str(record.get("author") or "")[:300]
            created.summary = str(record.get("summary") or "")[:20000]
            created.content_hash = digest
            tags = record.get("tags", [])
            if isinstance(tags, list):
                created.tags = _resolve_tags(db, user.organization_id, [str(t) for t in tags[:100]])
            db.add(created)
            db.commit()
            hashes.add(digest)
            hash_names.add(name)
            pulled += 1
            if pulled >= _SYNC_DOC_LIMIT:
                break
        except HTTPException:
            raise
    creds["last_sync"] = datetime.now(timezone.utc).isoformat()
    _write(user.id, creds)
    return {"pushed": pushed, "pulled": pulled, "skipped": skipped, "last_sync": creds["last_sync"]}


@router.post("/sync")
def sync(background: BackgroundTasks, db: Session = Depends(get_db), principal: Principal = Depends(require_session)):
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"busy": True, "pushed": 0, "pulled": 0, "skipped": 0, "last_sync": ""}
    try:
        return _sync_once(background, db, principal)
    finally:
        _SYNC_LOCK.release()
