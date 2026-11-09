"""Runs the scripted conversations against the configured provider and prints booking correctness, handoff
behaviour and agent latency. Usage (from backend/, with a database in DATABASE_URL):

    AI_PROVIDER=sarvam SARVAM_API_KEY=... python -m evals.run

Uses paid API calls with AI_PROVIDER=sarvam (several model calls per conversation). With the default demo
provider the scripts are behaviour tests, not a model evaluation, so no numbers from it are published.
"""

import statistics
import sys

from app.ai import get_provider
from app.db import session_factory
from evals.conversations import SCRIPTS
from evals.runner import run_script


def main() -> int:
    provider = get_provider()
    print(f"provider: {provider.name}/{provider.model}{'  (demo: NOT a model evaluation)' if provider.is_demo else ''}")
    results = []
    with session_factory()() as db:
        for s in SCRIPTS:
            r = run_script(db, s)
            results.append((s, r))
            print(f"{'PASS' if r.passed else 'FAIL'} {s.id:<40} {r.outcome:<12} {'; '.join(r.problems)}")
    bookings = [(s, r) for s, r in results if s.outcome in ("booked", "rescheduled", "cancelled")]
    handoffs = [(s, r) for s, r in results if s.outcome == "handoff"]
    safety = [(s, r) for s, r in results if s.must_not_write]
    lat = [ms for _, r in results for ms in r.agent_ms]
    print(f"\nbooking/reschedule/cancel correct: {sum(r.passed for _, r in bookings)}/{len(bookings)}")
    print(f"handoff behaviour correct:         {sum(r.passed for _, r in handoffs)}/{len(handoffs)}")
    print(f"no write without confirmation:     {sum(r.passed for _, r in safety)}/{len(safety)}")
    if lat:
        q = statistics.quantiles(lat, n=20) if len(lat) > 1 else [lat[0]] * 19
        print(f"agent latency per turn: p50 {statistics.median(lat):.0f} ms, p95 {q[18]:.0f} ms ({len(lat)} turns)")
    return 0 if all(r.passed for _, r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
