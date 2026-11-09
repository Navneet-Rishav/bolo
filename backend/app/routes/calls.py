"""The public patient widget: start a call, then send turns as text or recorded audio.

The clinic is identified by its unguessable slug, and the call by its UUID (a capability token). Calls are
rate-limited per IP and capped at a number of turns, because each turn can cost speech and model credits.
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import get_provider
from app.ai.base import AiError, AiUnavailable
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError, not_found
from app.models import Call, Clinic, Turn
from app.ratelimit import limiter
from app.services import clinic_data
from app.services.conversation import TurnResult, handle_turn, start_call

router = APIRouter(prefix="/api/public", tags=["patient widget"])
Db = Annotated[Session, Depends(get_db)]

MAX_AUDIO_BYTES = 2 * 1024 * 1024
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4"}


def _clinic(db: Session, slug: str) -> Clinic:
    c = db.scalar(select(Clinic).where(Clinic.slug == slug))
    if c is None:
        raise not_found("Clinic")
    return c


@router.get("/clinics/{slug}")
def clinic_info(slug: str, db: Db) -> dict:
    c = _clinic(db, slug)
    p = get_provider()
    return {
        "name": c.name,
        "is_demo": c.is_demo,
        "voice_enabled": p.voice_enabled,
        "demo_mode": p.is_demo,
        "doctors": [
            {"name": d.name, "name_hi": d.name_hi, "specialty": d.specialty, "specialty_hi": d.specialty_hi}
            for d in clinic_data.doctors(db, c.id)
        ],
    }


class StartIn(BaseModel):
    audio: bool = False


@router.post("/clinics/{slug}/calls", status_code=201)
def start(slug: str, body: StartIn, request: Request, db: Db) -> dict:
    ip = request.client.host if request.client else "unknown"
    limiter.hit("call", ip, get_settings().calls_per_hour_per_ip)
    c = _clinic(db, slug)
    call, text, audio, tts_ms = start_call(db, c, want_audio=body.audio)
    return {"call_id": call.id, "reply": text, "audio_b64": audio, "tts_ms": tts_ms, "stage": call.state["stage"]}


def _call(db: Session, call_id: str) -> tuple[Call, Clinic]:
    call = db.get(Call, call_id)
    if call is None:
        raise not_found("Call")
    turns = db.scalar(select(func.count()).select_from(Turn).where(Turn.call_id == call.id)) or 0
    if turns >= get_settings().max_turns_per_call * 2:
        raise ApiError(429, "call_too_long", "This call has reached its length limit. Please start a new call.")
    clinic = db.get(Clinic, call.clinic_id)
    assert clinic is not None
    return call, clinic


def _result(r: TurnResult) -> dict:
    return {
        "transcript": r.transcript,
        "reply": r.reply,
        "stage": r.stage,
        "outcome": r.outcome,
        "done": r.done,
        "latency": {"stt_ms": r.stt_ms, "agent_ms": r.agent_ms, "tts_ms": r.tts_ms},
        "audio_b64": r.audio_b64,
    }


def _run(db: Session, call: Call, clinic: Clinic, text: str, stt_ms: int | None, audio: bool) -> dict:
    try:
        return _result(handle_turn(db, call, clinic, text, stt_ms=stt_ms, want_audio=audio))
    except AiError as e:
        db.rollback()
        raise ApiError(502, "ai_error", "Sorry, I couldn't process that. Please say it again.") from e


class TextTurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    audio: bool = False


@router.post("/calls/{call_id}/turns")
def text_turn(call_id: str, body: TextTurnIn, db: Db) -> dict:
    call, clinic = _call(db, call_id)
    return _run(db, call, clinic, body.text.strip(), None, body.audio)


@router.post("/calls/{call_id}/voice-turns")
async def voice_turn(
    call_id: str, db: Db, audio: Annotated[UploadFile, File()], reply_audio: Annotated[bool, Form()] = True
) -> dict:
    call, clinic = _call(db, call_id)
    ctype = (audio.content_type or "").split(";")[0].strip()
    if ctype not in AUDIO_TYPES:
        raise ApiError(415, "unsupported_type", "Unsupported audio format")
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise ApiError(400, "empty_file", "No audio was recorded")
    if len(data) > MAX_AUDIO_BYTES:
        raise ApiError(413, "file_too_large", "Recordings can be at most about one minute long")
    t0 = time.perf_counter()
    try:
        transcript = get_provider().transcribe(data, audio.filename or "turn.webm", ctype)
    except AiUnavailable as e:
        raise ApiError(503, "voice_unavailable", str(e)) from e
    except AiError as e:
        raise ApiError(502, "ai_error", "Speech recognition failed. Please try again or type.") from e
    stt_ms = int((time.perf_counter() - t0) * 1000)
    if not transcript.text:
        raise ApiError(422, "no_speech", "I couldn't hear anything. Please try again.")
    return _run(db, call, clinic, transcript.text, stt_ms, reply_audio)
