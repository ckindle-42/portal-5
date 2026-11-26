# Proposed brief: Trace automatic memory outcomes

## Objective

Make the per-turn trace distinguish an automatic memory hit, miss, error, and completed writeback while preserving metadata-only-by-default privacy.

## Current behavior

- `auto-daily` auto-recall dispatches `recall` directly in `context_inject.py`, inserts any retrieved snippets, and traces only `memory_injected: <count>`; it does not create the ordinary tool requested/completed spans.
- Auto-writeback is scheduled fire-and-forget. A metric labels stored/error, but the turn trace does not show whether the background task completed or which correlation ID it belongs to.
- Existing seeded WFE memory rows grade recall and tool-grounded answers, but do not verify automatic durable storage/injection across two real turns.

## Invariants and constraints

- Never put recalled/stored memory text, tool arguments, or entity values in the trace by default.
- Keep trace record finalization robust if writeback completes after the response; use an explicit lifecycle/late-finalize design rather than losing or misattributing a span.
- Do not change memory selection, extraction, retention, owner scope, or writeback triggers in this task.
- Keep metrics and trace outcome vocabulary consistent and bounded-cardinality.

## Acceptance

- Offline tests cover hit, miss, dispatch error, writeback success, writeback failure, and late completion, asserting metadata only and correlation association.
- A real two-turn Open WebUI check stores a harmless fact in turn one and recalls it in turn two without synthetic `memory_seed`; both traces show the expected automatic outcomes, and the live memory store confirms durability.
- Existing privacy/redaction and `PORTAL_TRACE_BODIES` opt-in behavior remains unchanged.
