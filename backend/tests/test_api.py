from datetime import datetime

from sqlalchemy import select

from app.ai import set_provider
from app.ai.base import Transcript
from app.ai.demo import DemoProvider
from app.models import Appointment, AppointmentStatus, Call, Clinic, Turn
from app.services.conversation import handle_turn, start_call
from app.services.demo_data import create_demo_clinic
from evals.conversations import IST, NOW

# ---- auth and isolation -----------------------------------------------------------------------------------


def test_register_creates_a_clinic_and_login_works(client, staff) -> None:
    assert staff["user"]["clinic_name"] == "Test Clinic" and len(staff["user"]["clinic_slug"]) >= 10
    r = client.post("/api/auth/login", json={"email": "asha@example.com", "password": "correct-horse"})
    assert r.status_code == 200 and r.json()["user"]["clinic_id"] == staff["user"]["clinic_id"]
    assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong"}).status_code == 401


def test_healthz_and_meta(client) -> None:
    assert client.get("/healthz").json() == {"status": "ok", "db": "up"}
    m = client.get("/api/meta").json()
    assert m["demo_mode"] is True and m["voice_enabled"] is False and m["timezone"] == "Asia/Kolkata"


def test_dashboard_needs_login(client) -> None:
    for path in ("/api/doctors", "/api/appointments", "/api/calls"):
        assert client.get(path).status_code == 401


def test_demo_clinics_are_isolated(client) -> None:
    a = client.post("/api/auth/demo").json()
    b = client.post("/api/auth/demo").json()
    assert a["user"]["clinic_id"] != b["user"]["clinic_id"]
    ha, hb = ({"Authorization": f"Bearer {x['token']}"} for x in (a, b))
    assert len(client.get("/api/doctors", headers=ha).json()["items"]) == 3
    # a call in clinic A is not visible to clinic B
    call_id = client.post(f"/api/public/clinics/{a['user']['clinic_slug']}/calls", json={}).json()["call_id"]
    assert client.get(f"/api/calls/{call_id}", headers=hb).status_code == 404
    assert client.get(f"/api/calls/{call_id}", headers=ha).status_code == 200


# ---- patient widget ---------------------------------------------------------------------------------------


def test_widget_text_conversation_and_masked_transcript(client) -> None:
    demo = client.post("/api/auth/demo").json()
    slug, h = demo["user"]["clinic_slug"], {"Authorization": f"Bearer {demo['token']}"}
    info = client.get(f"/api/public/clinics/{slug}").json()
    assert info["name"] == "Sehat Demo Clinic" and len(info["doctors"]) == 3 and info["voice_enabled"] is False
    start = client.post(f"/api/public/clinics/{slug}/calls", json={}).json()
    assert "Namaste" in start["reply"] and start["audio_b64"] is None
    cid = start["call_id"]
    r1 = client.post(f"/api/public/calls/{cid}/turns", json={"text": "Mera naam Ravi hai"}).json()
    assert "mobile" in r1["reply"].lower() and r1["latency"]["agent_ms"] >= 0 and r1["done"] is False
    client.post(f"/api/public/calls/{cid}/turns", json={"text": "9876512345"})
    detail = client.get(f"/api/calls/{cid}", headers=h).json()
    texts = [t["text"] for t in detail["turns"]]
    assert "<PHONE>" in texts and "9876512345" not in " ".join(texts)
    calls = client.get("/api/calls", headers=h).json()["items"]
    assert calls[0]["id"] == cid and calls[0]["outcome"] == "in_progress" and calls[0]["turns"] == 2


def test_unknown_clinic_and_call(client) -> None:
    assert client.get("/api/public/clinics/nope").status_code == 404
    assert client.post("/api/public/calls/00000000-0000-0000-0000-000000000000/turns", json={"text": "hi"}).status_code == 404


def test_voice_turn_unavailable_in_demo(client) -> None:
    slug = client.post("/api/auth/demo").json()["user"]["clinic_slug"]
    cid = client.post(f"/api/public/clinics/{slug}/calls", json={}).json()["call_id"]
    r = client.post(f"/api/public/calls/{cid}/voice-turns", files={"audio": ("t.webm", b"\x1a\x45\xdf\xa3", "audio/webm")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "voice_unavailable"


class VoiceProvider(DemoProvider):
    voice_enabled = True
    is_demo = False

    def transcribe(self, audio, filename, content_type):
        return Transcript(text="Mera naam Ravi hai", language="hi-IN")

    def speak(self, text, language):
        return b"RIFF-fake-wav"


def test_voice_turn_with_a_working_provider_reports_latencies(client) -> None:
    set_provider(VoiceProvider())
    try:
        slug = client.post("/api/auth/demo").json()["user"]["clinic_slug"]
        start = client.post(f"/api/public/clinics/{slug}/calls", json={"audio": True}).json()
        assert start["audio_b64"] and start["tts_ms"] is not None
        r = client.post(
            f"/api/public/calls/{start['call_id']}/voice-turns", files={"audio": ("t.webm", b"audio", "audio/webm;codecs=opus")}
        ).json()
        assert r["transcript"] == "Mera naam Ravi hai"
        assert r["latency"]["stt_ms"] is not None and r["latency"]["agent_ms"] is not None and r["latency"]["tts_ms"] is not None
        assert r["audio_b64"]
        bad = client.post(
            f"/api/public/calls/{start['call_id']}/voice-turns", files={"audio": ("x.exe", b"MZ", "application/x-msdownload")}
        )
        assert bad.status_code == 415
    finally:
        set_provider(None)


def test_turn_cap_per_call(client, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_turns_per_call", 2)
    slug = client.post("/api/auth/demo").json()["user"]["clinic_slug"]
    cid = client.post(f"/api/public/clinics/{slug}/calls", json={}).json()["call_id"]
    codes = [client.post(f"/api/public/calls/{cid}/turns", json={"text": "hello"}).status_code for _ in range(3)]
    assert codes[-1] == 429


def test_calls_rate_limited_per_ip(client, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "calls_per_hour_per_ip", 2)
    slug = client.post("/api/auth/demo").json()["user"]["clinic_slug"]
    codes = [client.post(f"/api/public/clinics/{slug}/calls", json={}).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


# ---- dashboard --------------------------------------------------------------------------------------------


def test_appointments_calendar_and_staff_cancel(client, db) -> None:
    demo = client.post("/api/auth/demo").json()
    h = {"Authorization": f"Bearer {demo['token']}"}
    items = client.get("/api/appointments", headers=h, params={"days": 14}).json()["items"]
    assert items and all(i["patient_phone"].startswith("******") for i in items)
    appt_id = items[0]["id"]
    assert client.post(f"/api/appointments/{appt_id}/cancel", headers=h).json()["status"] == "cancelled"
    assert client.post(f"/api/appointments/{appt_id}/cancel", headers=h).status_code == 409
    other = client.post("/api/auth/demo").json()
    assert (
        client.post(f"/api/appointments/{appt_id}/cancel", headers={"Authorization": f"Bearer {other['token']}"}).status_code
        == 404
    )


# ---- the core business rule -------------------------------------------------------------------------------


def _to_confirm(db, clinic, name: str, phone: str) -> Call:
    call, *_ = start_call(db, clinic)
    for text in (f"Mera naam {name} hai", phone, "Kal Dr Sharma ko dikhana hai, shaam 5 baje"):
        r = handle_turn(db, db.get(Call, call.id), clinic, text, now=NOW)
    assert r.stage == "confirm", r.reply
    return call


def test_two_calls_racing_for_one_slot_cannot_double_book(db) -> None:
    staff = create_demo_clinic(db, IST, now=NOW)
    clinic = db.get(Clinic, staff.clinic_id)
    a = _to_confirm(db, clinic, "Ravi", "9876512345")
    b = _to_confirm(db, clinic, "Meena", "9876512399")  # both were offered Tue 17:00
    ra = handle_turn(db, db.get(Call, a.id), clinic, "haan", now=NOW)
    rb = handle_turn(db, db.get(Call, b.id), clinic, "haan", now=NOW)
    assert ra.outcome == "booked"
    assert rb.outcome == "in_progress" and "kisi aur ne le liya" in rb.reply and "1)" in rb.reply  # re-offered
    slot = datetime(2026, 11, 17, 17, 0, tzinfo=IST)
    booked = db.scalars(
        select(Appointment).where(Appointment.starts_at == slot, Appointment.status == AppointmentStatus.booked)
    ).all()
    assert len(booked) == 1
    # the losing call can still finish with another slot
    rb2 = handle_turn(db, db.get(Call, b.id), clinic, "first", now=NOW)
    rb3 = handle_turn(db, db.get(Call, b.id), clinic, "haan", now=NOW)
    assert rb2.stage == "confirm" and rb3.outcome == "booked"


def test_nothing_is_stored_unmasked(db) -> None:
    staff = create_demo_clinic(db, IST, now=NOW)
    clinic = db.get(Clinic, staff.clinic_id)
    call, *_ = start_call(db, clinic)
    handle_turn(db, db.get(Call, call.id), clinic, "Mera naam Ravi hai, number ९८७६५१२३४५", now=NOW)
    texts = " ".join(t.text for t in db.scalars(select(Turn).where(Turn.call_id == call.id)))
    assert "9876512345" not in texts and "९८७६५१२३४५" not in texts and "<PHONE>" in texts


def test_numbers_only_turn_keeps_the_conversation_language(db) -> None:
    staff = create_demo_clinic(db, IST, now=NOW)
    clinic = db.get(Clinic, staff.clinic_id)
    call, *_ = start_call(db, clinic)
    handle_turn(db, db.get(Call, call.id), clinic, "Mera naam Ravi hai", now=NOW)
    r = handle_turn(db, db.get(Call, call.id), clinic, "98765 12345", now=NOW)
    assert "chahenge" in r.reply  # still Hinglish, not switched to English by a bare number
