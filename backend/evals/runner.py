"""Runs scripted conversations through the real conversation service and checks the result."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, Call, Clinic, User
from app.services.conversation import handle_turn, start_call
from app.services.demo_data import create_demo_clinic
from evals.conversations import IST, NOW, Script


@dataclass
class Result:
    id: str
    passed: bool
    outcome: str
    problems: list[str] = field(default_factory=list)
    transcript: list[tuple[str, str]] = field(default_factory=list)
    agent_ms: list[int] = field(default_factory=list)


def run_script(db: Session, script: Script) -> Result:
    staff: User = create_demo_clinic(db, IST, now=NOW)
    clinic = db.get(Clinic, staff.clinic_id)
    before = {a.id: a.status for a in db.scalars(select(Appointment).where(Appointment.clinic_id == clinic.id))}
    call, greeting, _, _ = start_call(db, clinic)
    transcript = [("agent", greeting)]
    timings = []
    for text in script.turns:
        r = handle_turn(db, db.get(Call, call.id), clinic, text, now=NOW)
        transcript += [("patient", text), ("agent", r.reply)]
        timings.append(r.agent_ms)
        if r.done:
            break
    call = db.get(Call, call.id)
    db.refresh(call)
    problems: list[str] = []
    if call.outcome.value != script.outcome:
        problems.append(f"outcome {call.outcome.value} != {script.outcome}")
    if script.handoff_reason and call.handoff_reason != script.handoff_reason:
        problems.append(f"handoff_reason {call.handoff_reason} != {script.handoff_reason}")
    after = {a.id: a for a in db.scalars(select(Appointment).where(Appointment.clinic_id == clinic.id))}
    changed = [a for i, a in after.items() if before.get(i) != a.status]
    if script.must_not_write and changed:
        problems.append(f"wrote {len(changed)} appointment change(s) without confirmation")
    if script.starts_at:
        target = next((a for a in changed if a.starts_at.astimezone(IST).strftime("%Y-%m-%d %H:%M") == script.starts_at), None)
        if target is None:
            got = [a.starts_at.astimezone(IST).strftime("%Y-%m-%d %H:%M") + f" {a.status.value}" for a in changed]
            problems.append(f"expected a change at {script.starts_at}, got {got}")
        else:
            want_status = AppointmentStatus.cancelled if script.outcome == "cancelled" else AppointmentStatus.booked
            if target.status != want_status:
                problems.append(f"appointment at {script.starts_at} is {target.status.value}, expected {want_status.value}")
            if script.doctor and target.doctor.name != script.doctor:
                problems.append(f"doctor {target.doctor.name} != {script.doctor}")
    if script.outcome == "rescheduled" and not any(a.status == AppointmentStatus.cancelled for a in changed):
        problems.append("reschedule did not cancel the old appointment")
    return Result(script.id, not problems, call.outcome.value, problems, transcript, timings)
