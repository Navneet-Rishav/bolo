"""Code-side double-checks on the language model's reading of a patient message.

The model does the understanding, but a real-model eval showed it sometimes drops a field it clearly
understood ("first" not returned as option 1, a plain "haan" with no yes/no, romanized Hinglish labelled as
Hindi). These small, conservative rules only fill a field the model left empty, and only for short
messages where the meaning is unambiguous. They never override a value the model did return.
"""

import re

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")

_ORDINALS = {
    1: ("first", "1st", "pehla", "pehle", "pehli", "pahla", "pahle", "पहला", "पहले", "पहली"),
    2: ("second", "2nd", "doosra", "dusra", "doosre", "dusre", "doosri", "dusri", "दूसरा", "दूसरे", "दूसरी"),
    3: ("third", "3rd", "teesra", "tisra", "teesre", "teesri", "तीसरा", "तीसरे", "तीसरी"),
}
# "ji" / "जी" are neutral politeness words ("ji haan" = yes, "ji nahi" = no), so they are in neither list.
_YES = (
    "yes",
    "yeah",
    "yep",
    "haan",
    "han",
    "haa",
    "ha",
    "haanji",
    "hanji",
    "ok",
    "okay",
    "theek",
    "thik",
    "sure",
    "done",
    "हाँ",
    "हां",
    "ठीक",
)
_NO = ("no", "nope", "nahi", "nahin", "nai", "na", "mat", "नहीं", "ना", "मत")
_MAX_WORDS = 4  # longer messages are left entirely to the model


def _words(text: str) -> list[str]:
    return re.findall(r"[\wऀ-ॿ]+", text.lower())


def choice_from_text(text: str, offered: int) -> int | None:
    """ "first" / "option 2" / "2" / "dusra" → option number, if that many options were offered."""
    words = _words(text)
    if not offered or not words or len(words) > _MAX_WORDS:
        return None
    for n, names in _ORDINALS.items():
        if n <= offered and any(w in names for w in words):
            return n
    digits = [w for w in words if w.isdigit()]
    if len(digits) == 1 and len(digits[0]) == 1 and 1 <= int(digits[0]) <= offered:
        return int(digits[0])
    return None


def affirm_from_text(text: str) -> str | None:
    """A short, unambiguous yes or no ("haan ji", "nahi", "ok"); anything mixed or longer → None."""
    words = _words(text)
    if not words or len(words) > _MAX_WORDS:
        return None
    yes = any(w in _YES for w in words)
    no = any(w in _NO for w in words)
    if yes == no:  # neither, or both ("haan nahi")
        return None
    return "yes" if yes else "no"


def language_from_text(text: str, model_language: str) -> str:
    """Devanagari means Hindi; romanized text the model called Hindi is Hinglish (so replies stay romanized)."""
    if _DEVANAGARI.search(text):
        return "hi"
    if model_language == "hi" and _LATIN.search(text):
        return "hinglish"
    return model_language
