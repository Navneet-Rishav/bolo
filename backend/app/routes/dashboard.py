"""Staff dashboard API. Everything is scoped to the logged-in user's clinic."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.domain.phone import display_phone
from app.errors import ApiError, not_found
from app.models import Appointment, AppointmentStatus, Call, Doctor, Patient
from app.security import CurrentUser
from app.services import clinic_data

router = APIRouter(prefix="/api", tags=["dashboard"])
Db = Annotated[Session, Depends(get_db)]


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


@router.get("/doctors")
def doctors(user: CurrentUser, db: Db) -> dict:
    return {
        "items": [
            {
                "id": d.id,
                "name": d.name,
                "name_hi": d.name_hi,
                "specialty": d.specialty,
                "specialty_hi": d.specialty_hi,
                "slot_minutes": d.slot_minutes,
                "schedule": d.schedule,
            }
            for d in clinic_data.doctors(db, user.clinic_id)
        ]
    }


def _appt(a: Appointment, tz: ZoneInfo) -> dict:
    return {
        "id": a.id,
        "doctor_id": a.doctor_id,
        "doctor_name": a.doctor.name,
        "patient_name": a.patient.name,
        "patient_phone": display_phone(a.patient.phone),
        "starts_at": a.starts_at.astimezone(tz).isoformat(),
        "ends_at": a.ends_at.astimezone(tz).isoformat(),
        "status": a.status.value,
        "source": a.source,
        "call_id": a.call_id,
    }


@router.get("/appointments")
def appointments(
    user: CurrentUser,
    db: Db,
    start: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=31)] = 7,
    include_cancelled: bool = False,
) -> dict:
    tz = _tz()
    start = start or datetime.now(UTC).astimezone(tz).date()
    lo = datetime.combine(start, time(0, 0), tz)
    q = (
        select(Appointment)
        .options(selectinload(Appointment.doctor), selectinload(Appointment.patient))
        .where(
            Appointment.clinic_id == user.clinic_id,
            Appointment.starts_at >= lo,
            Appointment.starts_at < lo + timedelta(days=days),
        )
        .order_by(Appointment.starts_at)
    )
    if not include_cancelled:
        q = q.where(Appointment.status == AppointmentStatus.booked)
    return {"from": start.isoformat(), "days": days, "items": [_appt(a, tz) for a in db.scalars(q)]}


@router.post("/appointments/{appt_id}/cancel")
def cancel_appointment(appt_id: int, user: CurrentUser, db: Db) -> dict:
    a = db.get(Appointment, appt_id)
    if a is None or a.clinic_id != user.clinic_id:
        raise not_found("Appointment")
    if a.status != AppointmentStatus.booked:
        raise ApiError(409, "not_booked", "This appointment is already cancelled")
    a.status, a.cancelled_at = AppointmentStatus.cancelled, datetime.now(UTC)
    db.commit()
    return _appt(a, _tz())


@router.get("/calls")
def calls(user: CurrentUser, db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 50) -> dict:
    tz = _tz()
    rows = db.scalars(
        select(Call)
        .options(selectinload(Call.turns))
        .where(Call.clinic_id == user.clinic_id)
        .order_by(Call.created_at.desc())
        .limit(limit)
    ).all()
    out = []
    for c in rows:
        patient = db.get(Patient, c.patient_id) if c.patient_id else None
        agent_ms = [t.agent_ms for t in c.turns if t.agent_ms is not None]
        out.append(
            {
                "id": c.id,
                "created_at": c.created_at.astimezone(tz).isoformat(),
                "outcome": c.outcome.value,
                "handoff_reason": c.handoff_reason,
                "language": c.language,
                "provider": c.provider,
                "turns": sum(1 for t in c.turns if t.role == "patient"),
                "patient_name": patient.name if patient else (c.state or {}).get("name"),
                "avg_agent_ms": int(sum(agent_ms) / len(agent_ms)) if agent_ms else None,
            }
        )
    return {"items": out}


@router.get("/calls/{call_id}")
def call_detail(call_id: str, user: CurrentUser, db: Db) -> dict:
    c = db.get(Call, call_id)
    if c is None or c.clinic_id != user.clinic_id:
        raise not_found("Call")
    tz = _tz()
    appt = db.get(Appointment, c.appointment_id) if c.appointment_id else None
    doctor = db.get(Doctor, appt.doctor_id) if appt else None
    return {
        "id": c.id,
        "created_at": c.created_at.astimezone(tz).isoformat(),
        "outcome": c.outcome.value,
        "handoff_reason": c.handoff_reason,
        "language": c.language,
        "provider": c.provider,
        "appointment": {
            "doctor": doctor.name if doctor else None,
            "starts_at": appt.starts_at.astimezone(tz).isoformat(),
            "status": appt.status.value,
        }
        if appt
        else None,
        "turns": [
            {"role": t.role, "text": t.text, "stage": t.stage, "stt_ms": t.stt_ms, "agent_ms": t.agent_ms, "tts_ms": t.tts_ms}
            for t in c.turns
        ],
    }
