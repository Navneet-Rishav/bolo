"""Queries the agent and the dashboard share. Every query is scoped to one clinic."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, Doctor, Patient


def doctors(db: Session, clinic_id: str) -> list[Doctor]:
    return list(db.scalars(select(Doctor).where(Doctor.clinic_id == clinic_id).order_by(Doctor.id)))


def booked_starts(db: Session, doctor_id: int, day: date, tz: ZoneInfo) -> set[datetime]:
    start = datetime.combine(day, time(0, 0), tz)
    rows = db.scalars(
        select(Appointment.starts_at).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.booked,
            Appointment.starts_at >= start,
            Appointment.starts_at < start + timedelta(days=1),
        )
    )
    return set(rows)


def upcoming_appointments(db: Session, clinic_id: str, phone: str, now: datetime) -> list[Appointment]:
    return list(
        db.scalars(
            select(Appointment)
            .join(Patient, Patient.id == Appointment.patient_id)
            .where(
                Appointment.clinic_id == clinic_id,
                Patient.phone == phone,
                Appointment.status == AppointmentStatus.booked,
                Appointment.starts_at > now,
            )
            .order_by(Appointment.starts_at)
        )
    )


def upsert_patient(db: Session, clinic_id: str, name: str, phone: str) -> Patient:
    p = db.scalar(select(Patient).where(Patient.clinic_id == clinic_id, Patient.phone == phone))
    if p is None:
        p = Patient(clinic_id=clinic_id, name=name, phone=phone)
        db.add(p)
        db.flush()
    elif name and p.name != name:
        p.name = name
    return p
