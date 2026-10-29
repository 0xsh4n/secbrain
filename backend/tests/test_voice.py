from __future__ import annotations

import io
import wave

from app.services import tts


def test_tts_status_fields(client, auth_headers):
    r = client.get("/api/v1/voice/status", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["voice_name"]
    assert "available" in body


def test_clean_for_speech_strips_markup():
    out = tts._clean_for_speech("# Title\n**bold** and `code` and [E1] see https://x.y")
    assert "**" not in out and "`" not in out
    assert "[E1]" not in out
    assert "https://" not in out


def test_tts_endpoint_synthesizes_or_falls_back(client, auth_headers):
    r = client.post("/api/v1/voice/tts", headers=auth_headers, json={"text": "Hello from Nyx."})
    # Either the Piper voice is installed (200 + WAV) or it is not (503 so the
    # frontend falls back to browser speech). Both are acceptable.
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert r.headers["content-type"].startswith("audio/")
        w = wave.open(io.BytesIO(r.content), "rb")
        assert w.getnframes() > 0
