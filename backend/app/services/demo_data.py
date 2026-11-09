"""Demo clinics. Each "Try the demo" click creates its own fictional clinic (three doctors, weekly schedules and a
few bookings), a staff login and a patient-widget link, so visitors never see each other's patients.
Demo clinics are deleted after 24 hours."""

import secrets
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Appointment, Clinic, Doctor, Patient, User
from app.security import hash_password

DEMO_TTL = timedelta(hours=24)

WEEKDAYS_AM_PM = [["10:00", "13:00"], ["17:00", "20:00"]]
DOCTORS = [
    {
        "name": "Dr. Meera Sharma",
        "name_hi": "डॉ. मीरा शर्मा",
        "specialty": "General physician",
        "specialty_hi": "सामान्य चिकित्सक",
        "slot_minutes": 15,
        "schedule": {d: WEEKDAYS_AM_PM for d in ("mon", "tue", "wed", "thu", "fri")} | {"sat": [["10:00", "14:00"]], "sun": []},
    },
    {
        "name": "Dr. Arjun Rao",
        "name_hi": "डॉ. अर्जुन राव",
        "specialty": "Pediatrician",
        "specialty_hi": "बाल रोग विशेषज्ञ",
        "slot_minutes": 20,
        "schedule": {d: [["11:00", "14:00"]] for d in ("mon", "wed", "fri", "sat")} | {"tue": [], "thu": [], "sun": []},
    },
    {
        "name": "Dr. Kavya Iyer",
        "name_hi": "डॉ. काव्या अय्यर",
        "specialty": "Dentist",
        "specialty_hi": "दंत चिकित्सक",
        "slot_minutes": 30,
        "schedule": {d: [["16:00", "20:00"]] for d in ("tue", "thu", "sat")} | {"mon": [], "wed": [], "fri": [], "sun": []},
    },
]
# Fictional patients; numbers are well-known dummies.
PATIENTS = [("Asha Verma", "9876543210"), ("Rohit Gupta", "9123456789"), ("Sana Khan", "9988776655")]


def create_demo_clinic(db: Session, tz: ZoneInfo, now: datetime | None = None) -> User:
    now = now or datetime.now(UTC)
    clinic = Clinic(name="Sehat Demo Clinic", is_demo=True)
    db.add(clinic)
    db.flush()
    docs = [Doctor(clinic_id=clinic.id, **d) for d in DOCTORS]
    db.add_all(docs)
    pats = [Patient(clinic_id=clinic.id, name=n, phone=p) for n, p in PATIENTS]
    db.add_all(pats)
    db.flush()
    # A few existing bookings in the next days so the calendar is not empty and some slots are taken.
    local = now.astimezone(tz)
    seeds = [(0, 1, 10, 30), (1, 1, 17, 0), (2, 2, 16, 30), (0, 2, 11, 0)]
    for doc_i, days_ahead, h, m in seeds:
        day = local.date() + timedelta(days=days_ahead)
        doc = docs[doc_i]
        start = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
        if not doc.schedule.get(["mon", "tue", "wed", "thu", "fri", "sat", "sun"][day.weekday()]):
            continue
        db.add(
            Appointment(
                clinic_id=clinic.id,
                doctor_id=doc.id,
                patient_id=pats[(doc_i + days_ahead) % len(pats)].id,
                starts_at=start,
                ends_at=start + timedelta(minutes=doc.slot_minutes),
                source="seed",
            )
        )
    user = User(
        clinic_id=clinic.id,
        email=f"demo-{secrets.token_hex(6)}@bolo.demo",
        name="Demo Receptionist",
        is_demo=True,
        password_hash=hash_password(secrets.token_urlsafe(24)),
    )
    db.add(user)
    db.commit()
    return user


def purge_expired_demo_clinics(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    res = db.execute(delete(Clinic).where(Clinic.is_demo.is_(True), Clinic.created_at < now - DEMO_TTL))
    db.commit()
    return res.rowcount or 0
