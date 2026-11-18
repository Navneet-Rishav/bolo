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
    import argparse
    import json

    from app.config import get_settings

    ap = argparse.ArgumentParser(description="Run the scripted conversations against the configured provider.")
    ap.add_argument("--json", metavar="PATH", help="also write the summary and every transcript to PATH")
    ap.add_argument("--allow-remote-db", action="store_true", help="allow a hosted database (Neon/Render); off by default")
    args = ap.parse_args()
    url = get_settings().database_url
    if not args.allow_remote_db and ("neon.tech" in url or "render.com" in url):
        # Each script creates a demo clinic and leaves it behind, so never point this at production.
        print(
            "Refusing to run the eval against a hosted database. Point DATABASE_URL at a local Postgres, or pass --allow-remote-db."
        )
        return 2

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
    if args.json:
        summary = {
            "provider": f"{provider.name}/{provider.model}",
            "is_demo": provider.is_demo,
            "booking_correct": sum(r.passed for _, r in bookings),
            "bookings": len(bookings),
            "handoff_correct": sum(r.passed for _, r in handoffs),
            "handoffs": len(handoffs),
            "no_write_without_confirmation": sum(r.passed for _, r in safety),
            "safety_scripts": len(safety),
            "passed": sum(r.passed for _, r in results),
            "scripts": len(results),
            "agent_ms_p50": statistics.median(lat) if lat else None,
            "agent_ms_p95": (statistics.quantiles(lat, n=20)[18] if len(lat) > 1 else (lat[0] if lat else None)),
            "turns": len(lat),
        }
        records = [
            {
                "id": s.id,
                "language": s.language,
                "expected_outcome": s.outcome,
                "outcome": r.outcome,
                "passed": r.passed,
                "problems": r.problems,
                "transcript": [{"speaker": who, "text": text} for who, text in r.transcript],
                "agent_ms": r.agent_ms,
            }
            for s, r in results
        ]
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "records": records}, f, ensure_ascii=False, indent=2)
    return 0 if all(r.passed for _, r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
