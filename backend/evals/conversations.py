"""Scripted patient conversations with the expected result, used both as tests (demo provider) and as the eval
set for a real model (`python -m evals.run`).

Clock: Monday 16 Nov 2026, 09:00 IST, against the demo clinic (see services/demo_data.py):
  Dr. Meera Sharma (general, Mon-Fri 10-13 & 17-20, Sat 10-14, 15 min) - booked Tue 17 10:30 (Rohit), Wed 18 11:00 (Sana)
  Dr. Arjun Rao (pediatric, Mon/Wed/Fri/Sat 11-14, 20 min)
  Dr. Kavya Iyer (dentist, Tue/Thu/Sat 16-20, 30 min)
"""

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=IST)


@dataclass
class Script:
    id: str
    language: str
    turns: list[str]
    outcome: str  # booked | rescheduled | cancelled | handoff | ended | in_progress
    doctor: str | None = None
    starts_at: str | None = None  # "YYYY-MM-DD HH:MM" IST
    handoff_reason: str | None = None
    notes: str = ""
    must_not_write: bool = False
    tags: list[str] = field(default_factory=list)


SCRIPTS: list[Script] = [
    Script(
        "book_hinglish_exact_time",
        "hinglish",
        ["Mera naam Ravi Kumar hai", "98765 12345", "Kal Dr Sharma ko dikhana hai, shaam 5 baje"],
        "in_progress",
        notes="exact free time → straight to confirmation; nothing is written before yes",
        must_not_write=True,
    ),
    Script(
        "book_hinglish_confirmed",
        "hinglish",
        ["Mera naam Ravi Kumar hai", "98765 12345", "Kal Dr Sharma ko dikhana hai, shaam 5 baje", "haan"],
        "booked",
        doctor="Dr. Meera Sharma",
        starts_at="2026-11-17 17:00",
    ),
    Script(
        "book_english_pick_option",
        "en",
        [
            "Hi, I want to book an appointment",
            "My name is Priya Singh",
            "+91 91234 00000",
            "A dentist please",
            "Thursday evening",
            "the second one",
            "yes",
        ],
        "booked",
        doctor="Dr. Kavya Iyer",
        starts_at="2026-11-19 17:30",
    ),
    Script(
        "book_hindi_devanagari",
        "hi",
        ["नमस्ते, मेरा नाम सुनीता है", "मेरा नंबर ९८११२२३३४४ है", "मुझे कल सुबह डॉक्टर शर्मा को दिखाना है", "पहला", "हाँ"],
        "booked",
        doctor="Dr. Meera Sharma",
        starts_at="2026-11-17 10:00",
        notes="Devanagari digits in the phone; 10:30 is already booked so it is not offered",
    ),
    Script(
        "reschedule_by_time",
        "hinglish",
        [
            "Namaste, main Rohit Gupta bol raha hoon",
            "9123456789",
            "appointment reschedule karna hai",
            "Wednesday shaam",
            "17:15 wala",
            "ji haan",
        ],
        "rescheduled",
        doctor="Dr. Meera Sharma",
        starts_at="2026-11-18 17:15",
    ),
    Script(
        "cancel_all_in_one",
        "hinglish",
        ["Mera naam Sana Khan hai, number 9988776655, appointment cancel karna hai", "haan"],
        "cancelled",
        doctor="Dr. Meera Sharma",
        starts_at="2026-11-18 11:00",
    ),
    Script(
        "cancel_declined",
        "hinglish",
        ["Mera naam Sana Khan hai, number 9988776655, appointment cancel karna hai", "nahi"],
        "ended",
        must_not_write=True,
    ),
    Script(
        "emergency",
        "hinglish",
        ["Mere papa ko seene mein dard ho raha hai"],
        "handoff",
        handoff_reason="emergency",
        must_not_write=True,
    ),
    Script(
        "wants_human",
        "hinglish",
        ["Mera naam Anil hai", "mujhe kisi se baat karni hai"],
        "handoff",
        handoff_reason="human_requested",
        must_not_write=True,
    ),
    Script(
        "invalid_phone_then_valid",
        "en",
        ["I'm Neha Jain", "12345", "9876501234", "book appointment with the child doctor", "Monday 11:20", "yes"],
        "booked",
        doctor="Dr. Arjun Rao",
        starts_at="2026-11-16 11:20",
    ),
    Script(
        "confused_three_times",
        "hinglish",
        ["Mera naam Vikram hai", "9876512340", "umm", "pata nahi", "kuch bhi"],
        "handoff",
        handoff_reason="not_understood",
        must_not_write=True,
    ),
    Script(
        "reschedule_without_booking_then_book",
        "hinglish",
        ["Mera naam Kiran hai", "9811111111", "reschedule karna hai", "haan", "dentist", "Saturday 4 baje", "haan"],
        "booked",
        doctor="Dr. Kavya Iyer",
        starts_at="2026-11-21 16:00",
        notes="no booking on this number → offered a new booking",
    ),
    Script(
        "confirm_needs_clear_yes",
        "en",
        ["My name is Tara Das", "9812345670", "book Dr Sharma tomorrow at 6 pm", "hmm"],
        "in_progress",
        must_not_write=True,
        notes="an unclear answer at confirmation never writes",
    ),
    Script(
        "no_at_confirm_then_other_time",
        "en",
        ["My name is Tara Das", "9812345670", "book Dr Sharma tomorrow at 6 pm", "no", "tomorrow morning", "first", "yes"],
        "booked",
        doctor="Dr. Meera Sharma",
        starts_at="2026-11-17 10:00",
    ),
    Script(
        "closed_on_sunday",
        "en",
        ["My name is Omar Ali", "9800000001", "book general physician on Sunday", "first", "yes"],
        "booked",
        doctor="Dr. Meera Sharma",
        starts_at="2026-11-23 10:00",
        notes="Sunday is closed → next working day (Monday 23) is offered",
    ),
    Script(
        "messy_typos",
        "hinglish",
        ["mera naam Raju h", "mob no 9 8 7 6 5 0 0 0 0 1", "kal bachcho wale doctor ko dikhana", "first", "haan ji"],
        "booked",
        doctor="Dr. Arjun Rao",
        starts_at="2026-11-18 11:00",
        notes="spaced digits; Tuesday is the pediatrician's day off so Wednesday is offered",
    ),
]
