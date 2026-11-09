"""The receptionist as a LangGraph state machine.

    understand -> guard -> {identify | intent | search | confirm | closed} -> (next stage, same turn) ... -> END

- `understand` is the only node that calls the language model (structured extraction, validated).
- `guard` routes emergencies and "let me talk to a person" straight to a handoff.
- Stage nodes are plain code: they check slot availability, clinic hours and the booking window, and they
  write to the database ONLY in `confirm`, after an explicit yes, inside a savepoint. A double booking is
  impossible: the partial unique index on (doctor_id, starts_at) rejects it even if two calls race.
- Conversation state (stage, name, phone, offered slots...) is a plain dict stored on the Call row between turns.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import nlu
from app.agent.replies import fmt_day, fmt_options, fmt_when, say
from app.ai.base import AiProvider, complete_json
from app.domain.phone import extract_mobile
from app.domain.slots import SlotRules, available_slots, filter_by_preference, next_working_days
from app.models import Appointment, AppointmentStatus, Clinic, Doctor
from app.services import clinic_data

MAX_FAILURES = 3
MAX_OFFERED = 3


@dataclass
class Deps:
    db: Session
    clinic: Clinic
    provider: AiProvider
    now: datetime
    rules: SlotRules
    call_id: str | None = None


class TurnState(TypedDict, total=False):
    conv: dict[str, Any]  # persisted conversation state
    text: str
    nlu: dict[str, Any]
    replies: list[str]
    next: str  # which stage node runs next in this turn, or "end"
    outcome: str | None
    handoff_reason: str | None
    appointment_id: int | None
    patient_id: int | None


def new_conversation() -> dict[str, Any]:
    return {"stage": "identify", "lang": "hinglish", "failures": 0, "offered": []}


def build_graph(deps: Deps):
    tz = deps.rules.tz
    doctors = clinic_data.doctors(deps.db, deps.clinic.id)

    def doctor_list() -> list[dict]:
        return [{"name": d.name, "name_hi": d.name_hi, "specialty": d.specialty} for d in doctors]

    def doctor_by_id(doc_id: int | None) -> Doctor | None:
        return next((d for d in doctors if d.id == doc_id), None)

    def doctor_label(d: Doctor, lang: str) -> str:
        return f"{d.name_hi} ({d.specialty_hi})" if lang == "hi" else f"{d.name} ({d.specialty})"

    def resolve_doctor(hint: str | None) -> Doctor | None:
        if len(doctors) == 1:
            return doctors[0]
        if not hint:
            return None
        h = hint.lower()
        for d in doctors:
            surname = d.name.split()[-1].lower()
            if surname in h or d.name.lower() in h or d.name_hi in hint or d.name_hi.split()[-1] in hint:
                return d
        for d in doctors:
            if d.specialty.lower() in h or h in d.specialty.lower() or d.specialty_hi in hint:
                return d
        return None

    # ---- nodes ------------------------------------------------------------------------------------------

    def understand(s: TurnState) -> TurnState:
        conv = s["conv"]
        today = deps.now.astimezone(tz).date()
        user = nlu.build_user(s["text"], today, conv["stage"], doctor_list(), conv.get("offered_labels", []))
        u = complete_json(deps.provider, "understand", nlu.SYSTEM, user, nlu.Understanding)
        data = u.model_dump()
        # Code re-validates what the model returned.
        data["phone"] = extract_mobile(data["phone"] or "") or extract_mobile(s["text"])
        if data["date"]:
            try:
                date.fromisoformat(data["date"])
            except ValueError:
                data["date"] = None
        if data["time_pref"] and not re.fullmatch(r"morning|afternoon|evening|\d{2}:\d{2}", data["time_pref"]):
            data["time_pref"] = None
        conv["lang"] = data["language"]
        return {"nlu": data, "replies": []}

    def guard(s: TurnState) -> TurnState:
        u, conv = s["nlu"], s["conv"]
        if u["emergency"]:
            return handoff(s, "emergency", "handoff_emergency")
        if u["wants_human"]:
            return handoff(s, "human_requested", "handoff_human")
        if conv["stage"] in ("done", "handoff"):
            return {"next": "closed"}
        return {"next": conv["stage"]}

    def handoff(s: TurnState, reason: str, msg: str) -> TurnState:
        conv = s["conv"]
        conv["stage"] = "handoff"
        return {
            "replies": s.get("replies", []) + [say(conv["lang"], msg)],
            "next": "end",
            "outcome": "handoff",
            "handoff_reason": reason,
        }

    def progress(conv: dict, made: bool) -> None:
        conv["failures"] = 0 if made else conv.get("failures", 0) + 1

    def identify(s: TurnState) -> TurnState:
        conv, u, lang = s["conv"], s["nlu"], s["conv"]["lang"]
        before = (conv.get("name"), conv.get("phone"), conv.get("intent"))
        if u["name"] and not conv.get("name"):
            conv["name"] = u["name"].strip()[:80]
        if u["phone"]:
            conv["phone"] = u["phone"]
        if u["intent"] in ("book", "reschedule", "cancel"):
            conv["intent"] = u["intent"]
        if u.get("doctor"):
            conv["doctor_hint"] = u["doctor"]
        if u.get("date"):
            conv["date"] = u["date"]
        if u.get("time_pref"):
            conv["time_pref"] = u["time_pref"]
        progress(conv, (conv.get("name"), conv.get("phone"), conv.get("intent")) != before)
        if conv.get("failures", 0) >= MAX_FAILURES:
            return handoff(s, "not_understood", "handoff_confused")
        if not conv.get("name"):
            return reply(s, say(lang, "ask_name"))
        if not conv.get("phone"):
            said_digits = bool(re.search(r"\d", s["text"])) and before[1] is None and before[0] is not None
            return reply(s, say(lang, "bad_phone" if said_digits else "ask_phone", name=conv["name"]))
        conv["stage"] = "intent"
        return {"next": "intent"}

    def intent(s: TurnState) -> TurnState:
        conv, lang = s["conv"], s["conv"]["lang"]
        if s["nlu"]["intent"] in ("book", "reschedule", "cancel"):
            conv["intent"] = s["nlu"]["intent"]
        if not conv.get("intent"):
            # A plain "yes" after "no appointment found, book a new one?" means book.
            if conv.get("offer_book") and s["nlu"]["affirm"] == "yes":
                conv["intent"] = "book"
            else:
                progress(conv, False)
                if conv["failures"] >= MAX_FAILURES:
                    return handoff(s, "not_understood", "handoff_confused")
                return reply(s, say(lang, "ask_intent"))
        if conv["intent"] in ("reschedule", "cancel") and not conv.get("target_id"):
            upcoming = clinic_data.upcoming_appointments(deps.db, deps.clinic.id, conv["phone"], deps.now)
            if not upcoming:
                conv["intent"], conv["offer_book"] = None, True
                return reply(s, say(lang, "no_appointment"))
            target = upcoming[0]  # the next upcoming one; staff can handle unusual cases
            conv["target_id"] = target.id
            conv.setdefault("doctor_id", target.doctor_id)
            conv["target_when"] = target.starts_at.astimezone(tz).isoformat()
            if conv["intent"] == "cancel":
                conv["stage"] = "confirm"
                d = doctor_by_id(target.doctor_id)
                return reply(
                    s,
                    say(
                        lang, "confirm_cancel", doctor=doctor_label(d, lang), when=fmt_when(target.starts_at.astimezone(tz), lang)
                    ),
                )
        conv["stage"] = "search"
        progress(conv, True)
        return {"next": "search"}

    def offer(s: TurnState, doctor: Doctor, day: date, slots: list[datetime], key: str = "offer") -> TurnState:
        conv, lang = s["conv"], s["conv"]["lang"]
        chosen = slots[:MAX_OFFERED]
        conv["offered"] = [x.isoformat() for x in chosen]
        conv["offered_labels"] = [x.strftime("%Y-%m-%d %H:%M") for x in chosen]
        return reply(
            s, say(lang, key, doctor=doctor_label(doctor, lang), day=fmt_day(chosen[0], lang), options=fmt_options(chosen, lang))
        )

    def search(s: TurnState) -> TurnState:
        conv, u, lang = s["conv"], s["nlu"], s["conv"]["lang"]
        made = False
        # 1) the patient picked one of the offered slots
        if u["choice"] and conv.get("offered") and 1 <= u["choice"] <= len(conv["offered"]):
            conv["chosen"] = conv["offered"][u["choice"] - 1]
            conv["stage"] = "confirm"
            return confirm_prompt(s)
        # 2) new information
        for key in ("date", "time_pref"):
            if u.get(key):
                conv[key], made = u[key], True
        if u.get("doctor"):
            conv["doctor_hint"], made = u["doctor"], True
        if not conv.get("doctor_id"):
            d = resolve_doctor(conv.get("doctor_hint"))
            if d:
                conv["doctor_id"], made = d.id, True
        progress(conv, made or not conv.get("offered"))
        if conv["failures"] >= MAX_FAILURES:
            return handoff(s, "not_understood", "handoff_confused")
        doctor = doctor_by_id(conv.get("doctor_id"))
        if doctor is None:
            listing = ", ".join(doctor_label(d, lang) for d in doctors)
            return reply(s, say(lang, "ask_doctor", doctors=listing))
        today = deps.now.astimezone(tz).date()
        window_end = today + timedelta(days=deps.rules.window_days)
        if not conv.get("date") and not conv.get("time_pref"):
            days = next_working_days(doctor.schedule, today, 3, window_end)
            return reply(
                s,
                say(
                    lang,
                    "ask_date",
                    doctor=doctor_label(doctor, lang),
                    days=", ".join(fmt_day(datetime.combine(d, datetime.min.time(), tz), lang) for d in days),
                ),
            )

        def free(day: date) -> list[datetime]:
            booked = clinic_data.booked_starts(deps.db, doctor.id, day, tz)
            return filter_by_preference(
                available_slots(doctor.schedule, doctor.slot_minutes, day, booked, deps.now, deps.rules), conv.get("time_pref")
            )

        start = date.fromisoformat(conv["date"]) if conv.get("date") else today
        slots = free(start)
        pref = conv.get("time_pref") or ""
        if slots and ":" in pref and slots[0].strftime("%H:%M") == pref:
            conv["chosen"] = slots[0].isoformat()  # exactly the time they asked for is free
            conv["stage"] = "confirm"
            return confirm_prompt(s)
        if slots:
            if ":" in pref:
                slots = sorted(slots[:MAX_OFFERED])
            return offer(s, doctor, start, slots)
        d = start + timedelta(days=1)
        while d <= window_end:
            later = free(d)
            if later:
                return offer(s, doctor, d, sorted(later[:MAX_OFFERED]) if ":" in pref else later, key="no_slots_offer_next")
            d += timedelta(days=1)
        conv["stage"] = "handoff"
        return {
            "replies": s.get("replies", []) + [say(lang, "no_slots_at_all", doctor=doctor_label(doctor, lang))],
            "next": "end",
            "outcome": "handoff",
            "handoff_reason": "no_slots",
        }

    def confirm_prompt(s: TurnState) -> TurnState:
        conv, lang = s["conv"], s["conv"]["lang"]
        doctor = doctor_by_id(conv["doctor_id"])
        when = fmt_when(datetime.fromisoformat(conv["chosen"]).astimezone(tz), lang)
        if conv["intent"] == "reschedule":
            old = fmt_when(datetime.fromisoformat(conv["target_when"]), lang)
            return reply(s, say(lang, "confirm_reschedule", doctor=doctor_label(doctor, lang), old=old, when=when))
        return reply(s, say(lang, "confirm_book", doctor=doctor_label(doctor, lang), when=when, name=conv["name"]))

    def confirm(s: TurnState) -> TurnState:
        conv, u, lang = s["conv"], s["nlu"], s["conv"]["lang"]
        if u["affirm"] is None:
            # A new time or date while confirming means "not that one, this one instead".
            if conv["intent"] != "cancel" and (u.get("date") or u.get("time_pref") or u.get("choice")):
                conv["stage"] = "search"
                return {"next": "search"}
            progress(conv, False)
            if conv["failures"] >= MAX_FAILURES:
                return handoff(s, "not_understood", "handoff_confused")
            return reply(s, say(lang, "yes_or_no"))
        if u["affirm"] == "no":
            if conv["intent"] == "cancel":
                conv["stage"] = "done"
                return reply(s, say(lang, "not_changed")) | {"outcome": "ended"}
            conv.update(stage="search", chosen=None, offered=[], offered_labels=[], date=None, time_pref=None, failures=0)
            return {"next": "search"}
        return execute(s)

    def execute(s: TurnState) -> TurnState:
        conv, lang, db = s["conv"], s["conv"]["lang"], deps.db
        if conv["intent"] == "cancel":
            appt = db.get(Appointment, conv["target_id"])
            if appt is None or appt.status != AppointmentStatus.booked:
                conv["stage"] = "done"
                return reply(s, say(lang, "no_appointment")) | {"outcome": "ended"}
            appt.status, appt.cancelled_at = AppointmentStatus.cancelled, deps.now
            db.flush()
            conv["stage"] = "done"
            d = doctor_by_id(appt.doctor_id)
            msg = say(lang, "cancelled", doctor=doctor_label(d, lang), when=fmt_when(appt.starts_at.astimezone(tz), lang))
            return reply(s, msg) | {"outcome": "cancelled", "appointment_id": appt.id, "patient_id": appt.patient_id}

        doctor = doctor_by_id(conv["doctor_id"])
        start = datetime.fromisoformat(conv["chosen"])
        try:
            with db.begin_nested():  # savepoint: a lost race rolls back only this attempt
                patient = clinic_data.upsert_patient(db, deps.clinic.id, conv["name"], conv["phone"])
                if conv["intent"] == "reschedule":
                    old = db.get(Appointment, conv["target_id"])
                    if old is not None and old.status == AppointmentStatus.booked:
                        old.status, old.cancelled_at = AppointmentStatus.cancelled, deps.now
                        db.flush()
                appt = Appointment(
                    clinic_id=deps.clinic.id,
                    doctor_id=doctor.id,
                    patient_id=patient.id,
                    starts_at=start,
                    ends_at=start + timedelta(minutes=doctor.slot_minutes),
                    call_id=deps.call_id,
                )
                db.add(appt)
                db.flush()
        except IntegrityError:
            conv.update(stage="search", chosen=None, offered=[], offered_labels=[])
            out = search({**s, "nlu": {**s["nlu"], "choice": None, "affirm": None}})
            return out | {"replies": [say(lang, "slot_taken") + " ".join(out.get("replies", []))]}
        conv["stage"] = "done"
        when = fmt_when(start.astimezone(tz), lang)
        key = "rescheduled" if conv["intent"] == "reschedule" else "booked"
        outcome = "rescheduled" if key == "rescheduled" else "booked"
        return reply(s, say(lang, key, doctor=doctor_label(doctor, lang), when=when)) | {
            "outcome": outcome,
            "appointment_id": appt.id,
            "patient_id": patient.id,
        }

    def closed(s: TurnState) -> TurnState:
        return reply(s, say(s["conv"]["lang"], "closed"))

    def reply(s: TurnState, text: str) -> TurnState:
        return {"replies": s.get("replies", []) + [text], "next": "end"}

    g = StateGraph(TurnState)
    for name, fn in [
        ("understand", understand),
        ("guard", guard),
        ("identify", identify),
        ("intent", intent),
        ("search", search),
        ("confirm", confirm),
        ("closed", closed),
    ]:
        g.add_node(name, _keep_conv(fn))
    g.add_edge(START, "understand")
    g.add_edge("understand", "guard")
    route = {k: k for k in ("identify", "intent", "search", "confirm", "closed")} | {"end": END}
    for node in ("guard", "identify", "intent", "search", "confirm"):
        g.add_conditional_edges(node, lambda s: s.get("next", "end"), route)
    g.add_edge("closed", END)
    return g.compile()


def _keep_conv(fn):
    """Nodes update the conversation dict in place; returning it makes the update explicit to LangGraph."""

    def node(s: TurnState) -> TurnState:
        out = fn(s)
        return {**out, "conv": s["conv"]}

    node.__name__ = fn.__name__
    return node


def greeting(clinic: Clinic, lang: str = "hinglish") -> str:
    return say(lang, "greet", clinic=clinic.name)


def run_turn(deps: Deps, conv: dict[str, Any], text: str) -> TurnState:
    graph = build_graph(deps)
    return graph.invoke({"conv": conv, "text": text, "replies": []}, {"recursion_limit": 20})


def rules_from(tz_name: str, lead_minutes: int, window_days: int) -> SlotRules:
    return SlotRules(tz=ZoneInfo(tz_name), min_lead=timedelta(minutes=lead_minutes), window_days=window_days)
