"""Text-to-speech for the Nyx voice.

Default provider is **Piper** — a local neural TTS that runs on CPU, offline,
with no GPU. The voice model is loaded once and reused. If Piper or its voice
model is unavailable, ``synthesize_wav`` raises ``TtsUnavailable`` and the API
returns 503 so the frontend can fall back to the browser's speech synthesis.
"""
from __future__ import annotations

import io
import os
import re
import threading
import wave

from app.config import settings


class TtsUnavailable(Exception):
    pass


_voice = None
_voice_lock = threading.Lock()


def _clean_for_speech(text: str) -> str:
    """Strip markdown/code so speech is natural (mirrors the frontend cleaner)."""
    text = re.sub(r"```[\s\S]*?```", " Code is shown in the chat. ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"\[E\d+\]", "", text)
    text = re.sub(r"https?://\S+", "link", text)
    text = re.sub(r"[-*]\s+", "", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()


def is_available() -> bool:
    if settings.tts_provider.lower() != "piper":
        return False
    return os.path.exists(settings.piper_voice_path)


def _get_voice():
    global _voice
    if _voice is not None:
        return _voice
    with _voice_lock:
        if _voice is not None:
            return _voice
        if not is_available():
            raise TtsUnavailable(
                f"Piper voice model not found at {settings.piper_voice_path}. "
                "Download it with: python -m app.cli download-voice"
            )
        try:
            from piper import PiperVoice
        except Exception as exc:  # pragma: no cover - import guard
            raise TtsUnavailable(f"piper-tts not installed: {exc}") from exc
        _voice = PiperVoice.load(settings.piper_voice_path)
        return _voice


def synthesize_wav(text: str) -> bytes:
    """Return WAV audio bytes for ``text`` using the configured voice."""
    spoken = _clean_for_speech(text)[: settings.tts_max_chars]
    if not spoken:
        raise TtsUnavailable("No speakable text")
    voice = _get_voice()
    try:
        from piper import SynthesisConfig

        syn = SynthesisConfig(length_scale=settings.tts_length_scale)
    except Exception:
        syn = None
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        if syn is not None:
            voice.synthesize_wav(spoken, wav_file, syn_config=syn)
        else:
            voice.synthesize_wav(spoken, wav_file)
    return buffer.getvalue()


def status() -> dict:
    return {
        "provider": settings.tts_provider,
        "available": is_available(),
        "voice_name": settings.tts_voice_name,
        "model_path": settings.piper_voice_path,
    }
