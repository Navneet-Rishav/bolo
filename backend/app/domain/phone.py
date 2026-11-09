"""Indian mobile numbers: parsing (with Devanagari digits and +91/0 prefixes) and masking for logs/UI.

Written fresh for Bolo; same idea as Kaagaz's PII patterns, without Presidio (one pattern does not need it).
"""

import re

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
# Optional +91 / 91 / 0, then 10 digits starting 6-9, allowing spaces or hyphens between digit groups.
_MOBILE = re.compile(r"(?<![\d+])(?:\+?91[\s-]?|0)?([6-9](?:[\s-]?\d){9})(?![\d])")


def normalize_digits(text: str) -> str:
    return text.translate(_DEVANAGARI_DIGITS)


def extract_mobile(text: str) -> str | None:
    """Returns the first 10-digit Indian mobile number in the text, or None."""
    m = _MOBILE.search(normalize_digits(text))
    return re.sub(r"\D", "", m.group(1)) if m else None


def mask_phones(text: str) -> str:
    """Replaces every mobile number with <PHONE> (for stored transcripts and logs)."""
    return _MOBILE.sub("<PHONE>", normalize_digits(text))


def display_phone(phone: str) -> str:
    """Staff see only the last four digits: ******3210."""
    return "******" + phone[-4:] if len(phone) >= 4 else "******"
