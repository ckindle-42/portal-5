# PENDING MODEL VERDICTS — RETIRED 2026-09-07

The pending-models category is retired. Every model identity now carries exactly one
terminal disposition in the authoritative closeout register:

- **Register:** [`docs/MODEL_FLEET_CLOSEOUT_20260906.CLOSEOUT.md`](../docs/MODEL_FLEET_CLOSEOUT_20260906.CLOSEOUT.md)
- **Machine-readable state:** [`docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json`](../docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json)
  (final counts: 78 INTEGRATED / 5 RETAINED_FOR_PURPOSE / 105 REMOVED_CLOSED over the
  188-identity worklist plus dependency-review extras)

The former 62-entry ledger (30 keep-open / 20 investigate / 12 investigate-refresh —
none of which were terminal decisions) was superseded by executed tests on 2026-09-07:
two research probes, refusal/vision/CUA probes, a 10-model + native-arm judgment sweep,
a 3-arm gpt-oss instrument diagnostic, and a 4-arm 280-sample repair-loop coding exam.
Every pre-registered stop rule was evaluated on recorded data.

`scripts/model_cleanup_audit.py` now reads the closeout register and reports final
dispositions plus true cleanup exceptions; it no longer regenerates a pending ledger.

**Future model intake:** bounded task, named owner, one bounded question with a
specific test and a stop rule — no indefinite "pending" state.
