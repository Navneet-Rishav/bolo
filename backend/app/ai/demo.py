"""Offline, rule-based language understanding. NOT a model.

Used by tests, CI and the public demo so nothing calls a paid API. It handles common English, Hinglish and
Hindi phrasings with keyword lists and regular expressions. The UI labels it as demo mode, and no accuracy
numbers are reported from it. Voice (speech-to-text and text-to-speech) needs Sarvam, so it is off here.
"""

import json
import re
from datetime import date, timedelta

from app.ai.base import AiUnavailable, ChatResult, Transcript
from app.domain.phone import extract_mobile, normalize_digits

_DEV = re.compile(r"[ऀ-ॿ]")
_HINGLISH = re.compile(
    r"\b(hai|hain|mera|meri|mujhe|kal|aaj|parso|karna|kar|dena|chahiye|baje|subah|shaam|naam|haan|nahi|ji|wala|wali|ko|ke|ka)\b",
    re.I,
)

_INTENTS = [
    ("cancel", r"cancel|radd|रद्द|nahi aa (?:paunga|paungi|sakta|sakti)|कैंसिल"),
    ("reschedule", r"reschedul|postpone|prepone|change|badal|बदल|shift|dusre din|another (?:day|time)"),
    ("book", r"\bbook|appointment|appoint|milna|dikhana|dikhaana|checkup|check-up|consult|अपॉइंटमेंट|दिखाना|मिलना|बुक"),
]
_EMERGENCY = r"chest pain|seene (?:me|mein) dard|सीने में दर्द|saans|सांस|breath|behosh|बेहोश|unconscious|bleeding|khoon|खून|emergency|इमरजेंसी|seizure|daura|heart attack"
_HUMAN = r"\bhuman\b|insaan|इंसान|receptionist|\bstaff\b|kisi se baat|किसी से बात|real person|asli"
# `\b` does not work after Devanagari vowel signs (e.g. the candrabindu in हाँ), so words end at a space,
# punctuation or the end of the message instead.
_END = r"(?=$|[\s,.!?।])"
_YES = r"^(?:haan|haa|han|ha|ji|ji haan|yes|yeah|yep|sure|ok|okay|theek|thik|confirm|kar do|kardo|bilkul|हाँ|हां|जी|ठीक)" + _END
_NO = r"^(?:nahi|nahin|na|no|nope|mat|don't|dont|नहीं|ना)" + _END
_NAME = [
    r"(?:mera naam|my name is|naam hai|naam)\s+([A-Za-z][A-Za-z .]{1,40}?)(?:\s+(?:hai|h|he)\b|[,.]|$)",
    r"(?:i am|i'm|this is)\s+([A-Za-z][A-Za-z .]{1,40}?)(?:[,.]|$)",
    # Hinglish "main X hoon / bol raha hoon": requires the verb, so "main kal aana chahta hoon" is not a name.
    r"\bmain\s+([A-Za-z][A-Za-z ]{1,40}?)\s+(?:hoon|hu|bol raha|bol rahi)\b",
    r"(?:मेरा नाम|नाम)\s+([ऀ-ॿ ]{2,40}?)\s*(?:है|,|।|$)",
]
# Words that show a "name" match is really a sentence ("main kal aana chahta hoon").
_NOT_NAME = set(
    [
        "kal",
        "aaj",
        "parso",
        "aana",
        "jana",
        "chahta",
        "chahti",
        "chahiye",
        "appointment",
        "book",
        "karna",
        "dikhana",
        "doctor",
        "cancel",
        "reschedule",
        "baat",
        "theek",
        "yahan",
        "wahan",
        "abhi",
        "bimar",
        "beemar",
    ]
)
_WEEKDAYS = [
    ("monday|somvaar|somvar|सोमवार", 0),
    ("tuesday|mangalvaar|mangalvar|मंगलवार", 1),
    ("wednesday|budhvaar|budhvar|बुधवार", 2),
    ("thursday|guruvaar|guruvar|गुरुवार", 3),
    ("friday|shukravaar|shukravar|शुक्रवार", 4),
    ("saturday|shanivaar|shanivar|शनिवार", 5),
    ("sunday|ravivaar|ravivar|रविवार|itvaar", 6),
]
_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _word(alternatives: str) -> str:
    """A whole-word match that also works for Devanagari (where `\\b` fails after vowel signs)."""
    return rf"(?<![\wऀ-ॿ])(?:{alternatives})(?![\wऀ-ॿ])"


_ORDINALS = [
    (_word("pehla|pahla|first|1st|pehle wala|पहला|पहले वाला") + "|^1$", 1),
    (_word("doosra|dusra|second|2nd|दूसरा|दूसरे वाला") + "|^2$", 2),
    (_word("teesra|tisra|third|3rd|तीसरा|तीसरे वाला") + "|^3$", 3),
]
_SPECIALTIES = {
    "dentist": r"daant|dant|दांत|दाँत|teeth|tooth|dentist|dental",
    "pediatrician": r"bachch|bacch|बच्च|child|kid|baby|pediatric|paediatric",
    "general physician": r"general|fever|bukhar|बुखार|cold|khansi|physician|सामान्य",
    "dermatologist": r"skin|twacha|त्वचा|rash|derma|baal|hair",
}


def _language(text: str) -> str:
    if _DEV.search(text):
        return "hi"
    return "hinglish" if _HINGLISH.search(text) else "en"


def _date(text: str, today: date) -> str | None:
    t = text.lower()
    if re.search(r"\b(?:parso|parson|day after tomorrow)\b|परसों", t):
        return (today + timedelta(days=2)).isoformat()
    if re.search(r"\b(?:kal|tomorrow)\b|कल", t):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\b(?:aaj|today)\b|आज", t):
        return today.isoformat()
    for pattern, wd in _WEEKDAYS:
        if re.search(pattern, t):
            ahead = (wd - today.weekday()) % 7  # today's weekday name means today (it was likely just offered)
            return (today + timedelta(days=ahead)).isoformat()
    m = re.search(r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", t) or re.search(
        r"\b(\d{1,2})[/-](\d{1,2})\b", t
    )
    if m:
        day = int(m.group(1))
        month = _MONTHS[m.group(2)] if not m.group(2).isdigit() else int(m.group(2))
        try:
            d = date(today.year, month, day)
            return (d if d >= today else date(today.year + 1, month, day)).isoformat()
        except ValueError:
            return None
    return None


def _time(text: str) -> str | None:
    t = text.lower()
    m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|baje|बजे|o'?clock)", t) or re.search(r"\b(\d{1,2})[:.](\d{2})\b", t)
    if m:
        h, mins = int(m.group(1)), int(m.group(2) or 0)
        suffix = m.group(3) if m.lastindex and m.lastindex >= 3 else None
        if suffix == "pm" and h < 12 or suffix != "am" and h < 9:
            h += 12
        if re.search(r"shaam|sham|evening|शाम|raat", t) and h < 12:
            h += 12
        if 0 <= h < 24 and 0 <= mins < 60:
            return f"{h:02d}:{mins:02d}"
    if re.search(r"subah|morning|सुबह", t):
        return "morning"
    if re.search(r"dopahar|afternoon|दोपहर|lunch", t):
        return "afternoon"
    if re.search(r"shaam|sham|evening|शाम|raat", t):
        return "evening"
    return None


def understand(p: dict) -> dict:
    text = normalize_digits(p.get("MESSAGE", "")).strip()
    low = text.lower()
    today = date.fromisoformat(p["TODAY"][:10])
    stage = p.get("STAGE", "")
    out: dict = {
        "language": _language(text),
        "wants_human": bool(re.search(_HUMAN, low)),
        "emergency": bool(re.search(_EMERGENCY, low)),
    }

    for intent, pattern in _INTENTS:
        if re.search(pattern, low):
            out["intent"] = intent
            break
    phone = extract_mobile(text)
    if phone:
        out["phone"] = phone
    for pattern in _NAME:
        m = re.search(pattern, text, re.IGNORECASE)
        if m and not re.search(r"\d", m.group(1)) and not (set(m.group(1).lower().split()) & _NOT_NAME):
            out["name"] = m.group(1).strip().title() if not _DEV.search(m.group(1)) else m.group(1).strip()
            break
    if "name" not in out and stage == "identify" and not phone and not out.get("intent"):
        words = re.findall(r"[A-Za-zऀ-ॿ]+", text)
        if 1 <= len(words) <= 3 and not re.search(_YES + "|" + _NO, low):
            out["name"] = " ".join(w.title() if not _DEV.search(w) else w for w in words)

    for doc in p.get("DOCTORS", []):
        surname = doc["name"].split()[-1].lower()
        if surname in low or doc.get("name_hi", "@@").split()[-1] in text:
            out["doctor"] = doc["name"]
            break
    else:
        for spec, pattern in _SPECIALTIES.items():
            if re.search(pattern, low):
                out["doctor"] = spec
                break

    d = _date(text, today)
    if d:
        out["date"] = d
    tp = _time(text)
    if tp:
        out["time_pref"] = tp

    offered = [o["slot"] for o in p.get("OFFERED_OPTIONS", [])]
    if offered:
        for pattern, n in _ORDINALS:
            if re.search(pattern, low) and n <= len(offered):
                out["choice"] = n
                break
        if "choice" not in out and tp and ":" in tp:
            for i, slot in enumerate(offered):
                if slot.endswith(tp) or tp in slot:
                    out["choice"] = i + 1
                    break
    # Anchored to the start of the message, so "haan, kal 5 baje" is a yes but "kal nahi aa paunga" is not a no.
    if re.search(_YES, low):
        out["affirm"] = "yes"
    elif re.search(_NO, low):
        out["affirm"] = "no"
    return out


class DemoProvider:
    name = "demo"
    model = "rule-based (no AI)"
    is_demo = True
    voice_enabled = False

    def chat(self, task: str, system: str, user: str, schema: dict | None = None) -> ChatResult:
        if task != "understand":
            raise ValueError(f"demo provider has no handler for task {task}")
        payload = json.loads(user.split("\n\nYour previous reply was invalid")[0])
        return ChatResult(text=json.dumps(understand(payload), ensure_ascii=False), latency_ms=0)

    def transcribe(self, audio: bytes, filename: str, content_type: str) -> Transcript:
        raise AiUnavailable("Voice input uses the Sarvam speech API and is turned off in the demo. Please type instead.")

    def speak(self, text: str, language: str) -> bytes:
        raise AiUnavailable("Spoken replies use the Sarvam speech API and are turned off in the demo.")
