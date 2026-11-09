from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.phone import display_phone, extract_mobile, mask_phones
from app.domain.slots import SlotRules, available_slots, day_slots, filter_by_preference, next_working_days

IST = ZoneInfo("Asia/Kolkata")
SCHED = {"mon": [["10:00", "11:00"], ["17:00", "18:00"]], "tue": [["10:00", "11:00"]], "sun": []}
RULES = SlotRules(tz=IST, min_lead=timedelta(minutes=30), window_days=14)
MON = date(2026, 11, 16)  # a Monday


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mera number 9876543210 hai", "9876543210"),
        ("+91 98765 43210", "9876543210"),
        ("091-98765-43210", "9876543210"),  # old 0+91 prefix style
        ("0 9876543210", "9876543210"),
        ("मेरा नंबर ९८७६५४३२१० है", "9876543210"),
        ("98765-43210", "9876543210"),
        ("5876543210", None),  # Indian mobiles start with 6-9
        ("98765432", None),
        ("order 198765432101", None),
    ],
)
def test_extract_mobile(text: str, expected: str | None) -> None:
    assert extract_mobile(text) == expected


def test_mask_phones_in_transcripts() -> None:
    assert mask_phones("Ravi, 98765 43210, kal 5 baje") == "Ravi, <PHONE>, kal 5 baje"
    assert mask_phones("नंबर ९८७६५४३२१० है") == "नंबर <PHONE> है"
    assert mask_phones("slot 10:30 on 16/11/2026") == "slot 10:30 on 16/11/2026"
    assert display_phone("9876543210") == "******3210"


def test_day_slots_follow_the_schedule() -> None:
    slots = day_slots(SCHED, 15, MON, IST)
    assert [s.strftime("%H:%M") for s in slots] == ["10:00", "10:15", "10:30", "10:45", "17:00", "17:15", "17:30", "17:45"]
    assert day_slots(SCHED, 15, MON + timedelta(days=6), IST) == []  # Sunday: closed


def test_available_slots_skip_booked_past_and_lead_time() -> None:
    now = datetime(2026, 11, 16, 10, 5, tzinfo=IST)  # Monday 10:05
    booked = {datetime(2026, 11, 16, 17, 0, tzinfo=IST)}
    slots = available_slots(SCHED, 15, MON, booked, now, RULES)
    # 10:00-10:30 are too soon (30 min lead), 17:00 is booked
    assert [s.strftime("%H:%M") for s in slots] == ["10:45", "17:15", "17:30", "17:45"]


def test_booked_slot_matches_across_timezones() -> None:
    now = datetime(2026, 11, 15, 9, 0, tzinfo=IST)
    booked_utc = {datetime(2026, 11, 16, 4, 30, tzinfo=ZoneInfo("UTC"))}  # = 10:00 IST
    slots = available_slots(SCHED, 15, MON, booked_utc, now, RULES)
    assert "10:00" not in [s.strftime("%H:%M") for s in slots]


def test_no_slots_outside_booking_window_or_in_the_past() -> None:
    now = datetime(2026, 11, 16, 9, 0, tzinfo=IST)
    assert available_slots(SCHED, 15, MON - timedelta(days=7), set(), now, RULES) == []
    assert available_slots(SCHED, 15, MON + timedelta(days=21), set(), now, RULES) == []


def test_preference_filters() -> None:
    slots = day_slots(SCHED, 15, MON, IST)
    assert [s.strftime("%H:%M") for s in filter_by_preference(slots, "evening")] == ["17:00", "17:15", "17:30", "17:45"]
    assert filter_by_preference(slots, "17:20")[0].strftime("%H:%M") == "17:15"
    assert filter_by_preference(slots, None) == slots


def test_next_working_days() -> None:
    days = next_working_days(SCHED, MON - timedelta(days=1), 3, MON + timedelta(days=14))
    assert days == [MON, MON + timedelta(days=1), MON + timedelta(days=7)]
