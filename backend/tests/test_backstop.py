"""Code-side double-checks on the model's output, and the conversation fixes found by the real-model eval."""

import json

import pytest

from app.ai import set_provider
from app.ai.base import ChatResult
from app.ai.demo import DemoProvider
from app.domain.backstop import affirm_from_text, choice_from_text, language_from_text
from evals.conversations import SCRIPTS, Script
from evals.runner import run_script


@pytest.mark.parametrize(
    ("text", "offered", "expected"),
    [
        ("first", 3, 1),
        ("the second one", 3, 2),
        ("dusra wala", 3, 2),
        ("तीसरा", 3, 3),
        ("option 2", 3, 2),
        ("3", 3, 3),
        ("third", 2, None),  # only two options were offered
        ("5 baje", 3, None),  # a time, not an option
        ("first", 0, None),  # nothing offered
        ("I would like the first slot on Thursday evening please", 3, None),  # long: left to the model
    ],
)
def test_choice_from_text(text, offered, expected) -> None:
    assert choice_from_text(text, offered) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("haan", "yes"),
        ("ji haan", "yes"),
        ("theek hai", "yes"),
        ("हाँ जी", "yes"),
        ("nahi", "no"),
        ("ji nahi", "no"),
        ("नहीं", "no"),
        ("ji", None),  # politeness alone is not an answer
        ("haan nahi", None),  # contradictory
        ("haan but make it Tuesday evening instead please", None),  # long: left to the model
    ],
)
def test_affirm_from_text(text, expected) -> None:
    assert affirm_from_text(text) == expected


def test_language_from_text() -> None:
    assert language_from_text("Mera naam Ravi hai", "hi") == "hinglish"
    assert language_from_text("मेरा नाम रवि है", "hinglish") == "hi"
    assert language_from_text("My name is Ravi", "en") == "en"


class ForgetfulProvider(DemoProvider):
    """The demo provider, but dropping fields the way the real model sometimes did in the eval."""

    def __init__(self, drop_doctor: bool = False) -> None:
        self.drop_doctor = drop_doctor

    def chat(self, task, system, user, schema=None) -> ChatResult:
        data = json.loads(super().chat(task, system, user, schema).text)
        data["choice"] = None
        data["affirm"] = None
        if self.drop_doctor:
            data["doctor"] = None
        if data.get("language") == "hinglish":
            data["language"] = "hi"  # romanized Hinglish mislabelled as Hindi
        return ChatResult(text=json.dumps(data, ensure_ascii=False))


@pytest.fixture
def forgetful():
    def use(**kw):
        set_provider(ForgetfulProvider(**kw))

    yield use
    set_provider(None)


@pytest.mark.parametrize("script_id", ["book_hinglish_confirmed", "book_english_pick_option"])
def test_booking_survives_dropped_fields(db, forgetful, script_id) -> None:
    forgetful(drop_doctor=True)
    script = next(s for s in SCRIPTS if s.id == script_id)
    r = run_script(db, script)
    assert r.passed, "\n".join(r.problems + [f"{who}: {text}" for who, text in r.transcript])
    if script.language == "hinglish":  # replies stay romanized, not Devanagari
        assert not any("ऀ" <= ch <= "ॿ" for who, text in r.transcript if who == "agent" for ch in text)


def test_no_progress_after_choosing_to_book_hands_off(db) -> None:
    """Found by the eval: once the caller said "book", vague replies at "which doctor?" never handed off."""
    script = Script(
        "book_then_confused",
        "hinglish",
        ["Mera naam Vikram hai", "9876512340, appointment book karni hai", "umm", "pata nahi", "kuch bhi"],
        "handoff",
        handoff_reason="not_understood",
        must_not_write=True,
    )
    r = run_script(db, script)
    assert r.passed, "\n".join(r.problems + [f"{who}: {text}" for who, text in r.transcript])
