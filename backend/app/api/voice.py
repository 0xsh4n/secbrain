from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import get_principal
from app.services import tts

router = APIRouter(prefix="/voice", tags=["voice"])


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


@router.get("/status")
def voice_status(_principal=Depends(get_principal)) -> dict:
    return tts.status()


@router.post("/tts")
def synthesize(payload: TtsRequest, _principal=Depends(get_principal)):
    try:
        audio = tts.synthesize_wav(payload.text)
    except tts.TtsUnavailable as exc:
        # 503 -> frontend falls back to browser speech synthesis.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )
