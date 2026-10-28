"""Storage abstraction for raw document bytes.

Local filesystem implementation for development; the interface is small so an
object-storage backend (S3/MinIO) can be added later without touching callers.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.config import settings


class LocalStorage:
    def __init__(self, base_dir: str | None = None) -> None:
        self.base = Path(base_dir or settings.storage_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Prevent path traversal: keys are flat, sanitized identifiers.
        safe = key.replace("..", "_").lstrip("/")
        return self.base / safe

    def save(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage
