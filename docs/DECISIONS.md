# Design decisions

## 1. The model understands; code decides

The language model has exactly one job: turn one patient message into structured fields (intent, name, phone, doctor, date, time preference, option number, yes/no, "wants a human", "emergency"). Code then:
- validates every field (10-digit Indian mobile, real ISO date, time format, doctor matched against the clinic's own list);
- computes availability from each doctor's weekly schedule, clinic hours, existing bookings, a 30-minute minimum lead time and a 14-day window;
- writes **only after an explicit yes** to a read-back of exactly what will be booked.

Replies are templates (English, Hinglish, Hindi), not generated text: the receptionist can never promise a slot code has not checked, and replies are short and predictable for text-to-speech.
Alternative considered: letting the model run the conversation with tools. More natural phrasing, but harder to test, slower, and a hallucinated "you're booked" is a real failure for a clinic.

## 2. LangGraph state machine

`understand → guard → identify → intent → search → confirm`, with `closed` after the call ends. One graph run per patient turn. A node can hand over to the next stage within the same turn (a patient who gives name, phone and intent in one sentence goes straight to slot search). The conversation state (stage, name, phone, offered slots, chosen slot, failure counter) is a plain dict stored on the `calls` row between turns, so the API is stateless and a restart loses nothing.

- **Guards first:** emergency words → "call 112" + handoff; "let me talk to a person" → handoff.
- **Three turns without progress** → handoff to staff, instead of looping.
- "No" at confirmation goes back to slot search (booking) or ends without changes (cancel).
- Weekday names resolve to the next such day, or today if it is that weekday (a bug found by a scripted test: "Monday" said on a Monday right after Bolo offered "Monday 16 Nov").
- A message with no words (just a phone number) keeps the conversation's language (found in the end-to-end run: replies flipped to English after a bare number).

## 3. No double booking, enforced by the database

A partial unique index `(doctor_id, starts_at) WHERE status = 'booked'` makes a double booking impossible even if two calls confirm the same slot at the same moment. The booking runs in a savepoint; the losing call gets "that slot was just taken" and fresh options. Tested with two concurrent calls. Rescheduling cancels the old appointment and books the new one in the same savepoint.

## 4. Multi-tenant by clinic, one demo clinic per visitor

Every row has a `clinic_id`; every dashboard query is scoped to the logged-in user's clinic (another clinic's call or appointment is a 404). "Try the demo" creates a fresh fictional clinic (three doctors, schedules, a few bookings), a staff login and a patient-widget link, deleted after 24 hours, so visitors never see each other's patients. The widget URL uses an unguessable slug; each call id is a UUID.

## 5. Privacy

Phone numbers (including Devanagari digits and +91/0 prefixes) are replaced by `<PHONE>` in every stored transcript. Staff see only the last four digits (`******3210`). The patients table keeps the number because it is how a returning patient is found for rescheduling and cancelling.

## 6. Voice loop and latency

Browser mic (MediaRecorder) → Sarvam speech-to-text (`saaras:v4`, `codemix` for Hinglish) → agent → Sarvam text-to-speech (`bulbul:v4-flash`) → playback. Turn-based REST, not streaming: simpler, and enough to measure. Every turn stores STT, agent and TTS milliseconds; the widget and the call log show them. Streaming STT/TTS is the next step for lower latency. `reasoning_effort` defaults to `low` for the extraction call because it is a short structured task (measured on a sister project: lower reasoning cut latency but cost accuracy on harder routing, so evaluate with `python -m evals.run` before relying on it).

## 7. Offline demo provider

Tests, CI and the public demo use a rule-based understanding provider (keywords + regexes for English, Hinglish and Hindi). It is labelled as demo mode everywhere and voice is switched off with an explanation. The 16 scripted conversations pass with it, but they were written alongside its rules, so **they are behaviour tests of the state machine, not a model evaluation**. `python -m evals.run` runs the same scripts against the real model.

## 8. Out of scope (documented future steps)

- Real phone calls (telephony: SIP/Exotel/Twilio) — the widget is web only.
- SMS/WhatsApp confirmations and reminders.
- Streaming speech for lower latency.
- Staff creating or moving appointments from the dashboard (they can view and cancel).

## 9. Secret scanning (gitleaks in CI)

A separate workflow (`.github/workflows/gitleaks.yml`) scans the **full git history** on every push and pull request and fails if it finds a secret.
- Runs the gitleaks binary directly (pinned v8.30.1, SHA-256 checked) rather than a marketplace action: no extra token or permissions, and it's easy to see exactly what runs.
- `.gitleaks.toml` keeps all default rules and allow-lists only known placeholders (local docker/CI database credentials, the local docker JWT secret, test-only secrets), each matched exactly with a comment explaining why it is safe. A real token planted in any allow-listed file is still caught (checked by hand).
- Alternative considered: GitHub's built-in secret scanning push protection. It is useful too, but it can't be run locally or shown in CI, and it doesn't cover generic patterns the same way.

## 10. What the real-model eval found (19 Nov 2026)

Three runs of the 16 scripted conversations on Sarvam `sarvam-105b` before any fix, three after. Results: [`backend/evals/results/`](../backend/evals/results/2026-11-19-sarvam-105b.md).
- **The model sometimes drops a field it clearly understood** (the doctor, "first" as option 1, "haan" as yes), and the same message passes on one run and fails on the next. Code now double-checks short, unambiguous messages after the model ([`app/domain/backstop.py`](../backend/app/domain/backstop.py)) and only fills fields the model left empty. This keeps the rule from §1: the model understands, code decides; code just doesn't trust an empty answer.
- **A real state-machine bug:** in slot search every turn counted as progress until options were offered, so a caller who said "book" and then gave vague replies was never handed off. Now arriving in that step is not a failure, but an empty answer to a question asked there is. The demo provider never reached that state, so only the real model exposed it.
- **Language:** romanized text the model labels Hindi is kept as Hinglish, so replies don't switch to Devanagari mid-call.
- **Result:** scripts passed 8–9 → 11–14 of 16; bookings 3–4 → 5–8 of 10; handoffs 2 → 3 of 3; zero unconfirmed writes in all six runs. Still failing: an early guessed intent isn't overridden by a later "reschedule", "child doctor" isn't mapped to Pediatrician, and the model's date for a closed weekday isn't checked against the weekday the caller named.
- The eval script refuses to run against a hosted database (each script creates a demo clinic) unless `--allow-remote-db` is passed, and `--json` writes every transcript.
