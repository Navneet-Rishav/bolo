"""Language understanding: the ONLY job the language model has in Bolo.

The model turns one patient utterance into structured fields. Code validates every field (phone format,
dates inside the booking window, doctor names against the clinic's list) and decides everything else.
"""

import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Understanding(BaseModel):
    intent: Literal["book", "reschedule", "cancel", "other"] | None = None
    name: str | None = Field(default=None, max_length=80)
    phone: str | None = None
    doctor: str | None = Field(default=None, description="Doctor name or specialty as the patient said it")
    date: str | None = Field(default=None, description="YYYY-MM-DD, resolved from words like kal/tomorrow/Monday")
    time_pref: str | None = Field(default=None, description="morning | afternoon | evening | HH:MM (24h)")
    choice: int | None = Field(default=None, description="1-based number of an offered option, if the patient picked one")
    affirm: Literal["yes", "no"] | None = None
    wants_human: bool = False
    emergency: bool = False
    language: Literal["en", "hi", "hinglish"] = "hinglish"


SYSTEM = """You understand what a patient says to a clinic's phone receptionist in India. They may speak English,
Hindi (Devanagari) or Hinglish (Hindi in Latin letters), often mixed and with speech-to-text errors.
Extract ONLY what this one message says; leave everything else null. Rules:
- intent: book a new appointment, reschedule an existing one, cancel one, or other.
- phone: the 10-digit mobile number if they said one (digits only).
- date: resolve relative words using TODAY in the input (kal = tomorrow, parso = day after tomorrow, weekday names = the next such day, or TODAY itself if today is that weekday). Format YYYY-MM-DD.
- time_pref: "morning"/"afternoon"/"evening" for subah/dopahar/shaam, or "HH:MM" 24h for a specific time (5 baje shaam = 17:00; clinic hours are 9:00-21:00, so "5 baje" means 17:00).
- choice: if OFFERED_OPTIONS are listed and the patient picks one ("pehla wala", "second", "5:30 wala"), its number.
- affirm: "yes" for haan/ji/yes/theek hai/confirm, "no" for nahi/no/mat karo. Only when they answer a yes/no question.
- wants_human: they ask for a person/receptionist/staff.
- emergency: chest pain, breathing trouble, unconsciousness, heavy bleeding, or similar.
- language: the language they used.
Reply with ONLY a JSON object with these keys: intent, name, phone, doctor, date, time_pref, choice, affirm, wants_human, emergency, language."""


def build_user(text: str, today: date, stage: str, doctors: list[dict], offered: list[str]) -> str:
    return json.dumps(
        {
            "TODAY": f"{today.isoformat()} ({today.strftime('%A')})",
            "STAGE": stage,
            "DOCTORS": doctors,
            "OFFERED_OPTIONS": [{"number": i + 1, "slot": s} for i, s in enumerate(offered)],
            "MESSAGE": text,
        },
        ensure_ascii=False,
    )
