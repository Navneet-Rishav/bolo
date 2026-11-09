"""Runs one patient turn end to end and records it: text (or audio → STT) → agent → reply (→ TTS).

Each turn's timings are stored (speech-to-text, agent, text-to-speech) so the widget and the dashboard can show
where the time goes. Phone numbers are masked in everything that is stored.
"""

import base64
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.graph import Deps, greeting, new_conversation, rules_from, run_turn
from app.ai import get_provider
from app.ai.base import AiError, AiUnavailable
from app.config import get_settings
from app.domain.phone import mask_phones
from app.models import Call, CallOutcome, Clinic, Turn

TTS_LANG = {"hi": "hi-IN", "hinglish": "hi-IN", "en": "en-IN"}


@dataclass
class TurnResult:
    transcript: str
    reply: str
    stage: str
    outcome: str
    done: bool
    stt_ms: int | None
    agent_ms: int
    tts_ms: int | None
    audio_b64: str | None


def _deps(db: Session, clinic: Clinic, call_id: str | None, now: datetime | None = None) -> Deps:
    s = get_settings()
    return Deps(
        db=db,
        clinic=clinic,
        provider=get_provider(),
        now=now or datetime.now(UTC),
        rules=rules_from(s.timezone, s.min_lead_minutes, s.booking_window_days),
        call_id=call_id,
    )


def _speak(text: str, lang: str, want_audio: bool) -> tuple[str | None, int | None]:
    provider = get_provider()
    if not (want_audio and provider.voice_enabled):
        return None, None
    t0 = time.perf_counter()
    try:
        audio = provider.speak(text, TTS_LANG.get(lang, "hi-IN"))
    except (AiError, AiUnavailable):
        return None, None  # the text reply still works without audio
    return base64.b64encode(audio).decode(), int((time.perf_counter() - t0) * 1000)


def start_call(db: Session, clinic: Clinic, want_audio: bool = False) -> tuple[Call, str, str | None, int | None]:
    conv = new_conversation()
    call = Call(clinic_id=clinic.id, state=conv, provider=get_provider().name)
    db.add(call)
    db.flush()
    text = greeting(clinic, conv["lang"])
    audio, tts_ms = _speak(text, conv["lang"], want_audio)
    db.add(Turn(call_id=call.id, idx=0, role="agent", text=text, stage="greet", tts_ms=tts_ms))
    db.commit()
    return call, text, audio, tts_ms


def handle_turn(
    db: Session,
    call: Call,
    clinic: Clinic,
    text: str,
    stt_ms: int | None = None,
    want_audio: bool = False,
    now: datetime | None = None,
) -> TurnResult:
    conv = dict(call.state or new_conversation())
    t0 = time.perf_counter()
    out = run_turn(_deps(db, clinic, call.id, now), conv, text)
    agent_ms = int((time.perf_counter() - t0) * 1000)
    reply = " ".join(out.get("replies", [])) or "…"
    conv = out["conv"]

    idx = db.scalar(select(func.count()).select_from(Turn).where(Turn.call_id == call.id)) or 0
    db.add(Turn(call_id=call.id, idx=idx, role="patient", text=mask_phones(text), stage=conv["stage"], stt_ms=stt_ms))
    audio, tts_ms = _speak(reply, conv["lang"], want_audio)
    db.add(
        Turn(
            call_id=call.id,
            idx=idx + 1,
            role="agent",
            text=mask_phones(reply),
            stage=conv["stage"],
            agent_ms=agent_ms,
            tts_ms=tts_ms,
        )
    )

    call.state = conv
    call.language = conv["lang"]
    if out.get("outcome"):
        call.outcome = CallOutcome(out["outcome"])
        call.handoff_reason = out.get("handoff_reason")
        call.ended_at = datetime.now(UTC)
    if out.get("appointment_id"):
        call.appointment_id = out["appointment_id"]
    if out.get("patient_id"):
        call.patient_id = out["patient_id"]
    db.commit()
    return TurnResult(
        transcript=text,
        reply=reply,
        stage=conv["stage"],
        outcome=call.outcome.value,
        done=conv["stage"] in ("done", "handoff"),
        stt_ms=stt_ms,
        agent_ms=agent_ms,
        tts_ms=tts_ms,
        audio_b64=audio,
    )
