"""Database models. Every row belongs to a clinic, so clinics (and demo visitors) are isolated from each other."""

import enum
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class AppointmentStatus(enum.StrEnum):
    booked = "booked"
    cancelled = "cancelled"


class CallOutcome(enum.StrEnum):
    in_progress = "in_progress"
    booked = "booked"
    rescheduled = "rescheduled"
    cancelled = "cancelled"
    handoff = "handoff"
    ended = "ended"  # finished without a change (e.g. patient said no)


class Clinic(Base):
    __tablename__ = "clinics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    # Public, unguessable id used in the patient widget URL.
    slug: Mapped[str] = mapped_column(String(32), unique=True, default=lambda: secrets.token_urlsafe(9))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    """Clinic staff (dashboard users)."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(100))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Doctor(Base):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_hi: Mapped[str] = mapped_column(String(80))
    specialty: Mapped[str] = mapped_column(String(60))
    specialty_hi: Mapped[str] = mapped_column(String(60))
    slot_minutes: Mapped[int] = mapped_column(Integer, default=15)
    # {"mon": [["10:00", "13:00"], ["17:00", "20:00"]], ..., "sun": []} in clinic local time
    schedule: Mapped[dict] = mapped_column(JsonType, default=dict)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("clinic_id", "phone", name="uq_patient_phone"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(10))  # 10-digit Indian mobile; masked everywhere it is shown or logged
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        # The database itself refuses a double booking, even if two calls confirm the same slot at once.
        Index(
            "uq_doctor_slot_booked",
            "doctor_id",
            "starts_at",
            unique=True,
            postgresql_where=text("status = 'booked'"),
        ),
        Index("ix_appt_clinic_time", "clinic_id", "starts_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status"), default=AppointmentStatus.booked
    )
    source: Mapped[str] = mapped_column(String(20), default="voice")  # voice | staff | seed
    call_id: Mapped[str | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    doctor: Mapped[Doctor] = relationship()
    patient: Mapped[Patient] = relationship()


class Call(Base):
    """One conversation with the voice widget. `state` holds the conversation state between turns."""

    __tablename__ = "calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id", ondelete="CASCADE"), index=True)
    state: Mapped[dict] = mapped_column(JsonType, default=dict)
    outcome: Mapped[CallOutcome] = mapped_column(Enum(CallOutcome, name="call_outcome"), default=CallOutcome.in_progress)
    handoff_reason: Mapped[str | None] = mapped_column(String(40))
    language: Mapped[str | None] = mapped_column(String(10))
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"))
    appointment_id: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(20), default="demo")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    turns: Mapped[list["Turn"]] = relationship(back_populates="call", cascade="all, delete-orphan", order_by="Turn.idx")


class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))  # patient | agent
    text: Mapped[str] = mapped_column(Text)  # phone numbers masked before storing
    stage: Mapped[str | None] = mapped_column(String(20))
    stt_ms: Mapped[int | None] = mapped_column(Integer)
    agent_ms: Mapped[int | None] = mapped_column(Integer)
    tts_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    call: Mapped[Call] = relationship(back_populates="turns")
