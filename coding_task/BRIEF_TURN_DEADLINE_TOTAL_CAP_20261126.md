# Brief — the 300 s whole-turn deadline kills healthy long turns (defect seen, not safely fixable from a worker lane)

Filed by `lane/agy-baseline-diff` (2026-11-26) per
`BRIEF_AGY_BASELINE_DIFF_ESCALATION_20261126.md` §"For a defect you can see but not safely fix,
write its brief". Evidence: `docs/findings/AGY_BASELINE_DIFF_20261126.md` §2/§5.

## The defect

`7dbefe845` ("Bound inference turn and model-load waits", merged via `lane/cold-start-stream`,
follow-ups `3ccc0a75c`, `19136b564`, `501373979`) applies `defaults.request_timeout`
(`config/backends.yaml:1055`, 300 s) as a **wall-clock cap on the entire streamed turn**
(`portal/platform/inference/router/handlers.py::_turn_timeout_s` →
`_stream_with_request_deadline(source, start_time, timeout_s)`; the deadline is
`start_time + timeout_s` and does not reset on activity). Before this commit the value bounded
only non-streaming engine requests; streaming turns were unbounded by design
(`portal/platform/inference/streaming_client.py` module docstring).

Consequences observed live (QAT `cfe67a16e`, 2026-11-26):

1. `s2-p2-auto-research` — baseline PASS at 269.8 s with a 12,063-char answer (OWUI chat
   `fc3d8d9e-9de3-4fb8-a1d8-020db0a008e8`); now killed at exactly 300.0046 s with the entire
   assistant content replaced by `[Pipeline stream error — the reply ended early: turn deadline
   exceeded after 300s]` (chat `f8ce0b3c-0b76-4e0d-8ddf-aa0e3ee46ec7`, 84 chars). Reproduced in
   both current runs (WARN 302.2 s then FAIL 301.6 s).
2. The killed turn left the Ollama runner busy/resident at the next inter-phase gate; the gate's
   60 s evict budget expired and **180 of 236 rows were BLOCKED** (timeline in the findings doc §2B).
3. Baseline also passed rows at 353.9 s (`s3-canonical-auto-security-purpleteam-deep`), 336.3 s
   (`s4-auto-vision-tools`) and 296.0 s (`s4-auto-compliance-core`) — any single-turn stream over
   300 s is now dead on arrival, so the release gate can never reproduce the baseline.

## Why no revert was committed

The commit fixes a real defect (unbounded cold-start/model-load waits; the same lane added
load-guard bound tests in `tests/unit/test_load_guard.py`), three later commits build on the
`_closing_frames`/terminal-frame machinery, and a revert would resurrect the hang it was written
for. This is "real defect behind it" territory — the brief's revert criterion does not apply.

## Proposed fix (design, needs live proof)

Make the cap **stall-based, not total**: reset the deadline on every received chunk (or on tool-hop
progress), e.g. `asyncio.timeout` per `__anext__` with an idle bound (suggest 90–120 s idle, which
still catches the cold-start hang: nothing streams while the engine churns), plus optionally a
generous absolute ceiling (e.g. 900 s) for runaway loops. Alternatively keep a total cap but derive
it per workspace (`turn_budget_s` in `config/portal.yaml` per workspace, default
`max(request_timeout, observed p99 turn)`); research/council seats need ≥ 600 s.

Acceptance:

- `s2-p2-auto-research` completes with its full answer (no `stream error — the reply ended early`
  marker in the OWUI chat) at its natural ~270–350 s duration.
- A deliberately stalled stream (kill the engine mid-generation) still terminates with the
  `request_timeout` notice within the idle bound — keep/extend
  `tests/unit/test_stream_pipeline_errors.py::test_turn_deadline_closes_stalled_stream_and_records_reason`.
- A full QAT run passes the post-research gate (no BLOCKED cascade).
- Streaming change → `./scripts/smoke_stream.sh` against the live stack is mandatory.

## Related, already fixed on this branch

- QAT graded a deadline-killed turn as "chat turn completed" (WARN). Fixed: the router's
  `[Pipeline stream error — …]` / `[Backend stream error — …]` notices now FAIL the row as
  `INFRA_ENV_GAP` (`tests/qat/runner.py::_stream_error_notice`).
- The gate block that followed was unrecorded. Fixed: blocked rows carry the failing check detail
  and `gate_blocked_<phase>.json` is written to the run dir.
