"""Appointment slots, computed in code from each doctor's weekly schedule (clinic-local time).

A slot is offered only if it is inside the doctor's hours, not already booked, at least `min_lead` in the
future and within the booking window. The LLM never decides availability.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TIME_BANDS = {
    "morning": (time(0, 0), time(12, 0)),
    "afternoon": (time(12, 0), time(17, 0)),
    "evening": (time(17, 0), time(23, 59)),
}


@dataclass(frozen=True)
class SlotRules:
    tz: ZoneInfo
    min_lead: timedelta
    window_days: int


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def working_on(schedule: dict, day: date) -> bool:
    return bool(schedule.get(DAYS[day.weekday()]))


def day_slots(schedule: dict, slot_minutes: int, day: date, tz: ZoneInfo) -> list[datetime]:
    """All slot start times for one day from the weekly schedule (timezone-aware, clinic time)."""
    out: list[datetime] = []
    for start_s, end_s in schedule.get(DAYS[day.weekday()], []):
        cur = datetime.combine(day, _hm(start_s), tz)
        end = datetime.combine(day, _hm(end_s), tz)
        while cur + timedelta(minutes=slot_minutes) <= end:
            out.append(cur)
            cur += timedelta(minutes=slot_minutes)
    return out


def available_slots(
    schedule: dict, slot_minutes: int, day: date, booked: set[datetime], now: datetime, rules: SlotRules
) -> list[datetime]:
    today = now.astimezone(rules.tz).date()
    if day < today or day > today + timedelta(days=rules.window_days):
        return []
    earliest = now + rules.min_lead
    booked_utc = {b.timestamp() for b in booked}
    return [s for s in day_slots(schedule, slot_minutes, day, rules.tz) if s >= earliest and s.timestamp() not in booked_utc]


def filter_by_preference(slots: list[datetime], pref: str | None) -> list[datetime]:
    """'morning' / 'afternoon' / 'evening' keep that band; 'HH:MM' sorts by closeness to that time."""
    if not pref:
        return slots
    if pref in TIME_BANDS:
        lo, hi = TIME_BANDS[pref]
        return [s for s in slots if lo <= s.timetz().replace(tzinfo=None) < hi]
    try:
        target = _hm(pref)
    except ValueError:
        return slots
    minutes = target.hour * 60 + target.minute
    return sorted(slots, key=lambda s: abs(s.hour * 60 + s.minute - minutes))


def next_working_days(schedule: dict, start: date, count: int, window_end: date) -> list[date]:
    out, d = [], start
    while d <= window_end and len(out) < count:
        if working_on(schedule, d):
            out.append(d)
        d += timedelta(days=1)
    return out
