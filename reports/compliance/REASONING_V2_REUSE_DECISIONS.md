# REASONING_V2_REUSE_DECISIONS — STATUS: NOT STARTED

This is a placeholder status record, not the P0-R deliverable. Do not treat
its presence as evidence P0-R ran.

## What happened this session

This session's engineering time went to P0 (baseline/regression contract,
see `REASONING_V2_BASELINE.md`) and P1 (the seven dangerous-verdict/selection
corrections — F01, F03-F06, F09, F10, applied in `core/{engine,coverage,
tiers,register_diff,mapping_store}.py` and `tools/compliance_mcp.py`), which
the task explicitly authorizes to proceed independently of P0-R ("P1 safety
corrections can proceed independently"). P0-R's bounded prototypes —

- **R1** (a real `core/oscal_adapter.py` validated against pinned official
  OSCAL 1.2.x JSON schemas, with catalog/component-definition/assessment-
  result export and mapping-collection import/export, reimport-safety proof),
- **R2** (a pinned-commit Utopia adapter spike run against the two-revision/
  two-mapping/proposed-correction fixture described in the design doc,
  compared against a minimal native implementation on the same fixture), and
- **R4-R6** (Docling provenance wiring into a private revision artifact,
  StrictDoc/CISO-Assistant-pattern adaptation, and a PROV-O-aligned
  provenance-export bundle)

were **not attempted** — they were not started, not partially built, and no
fixture exists for them yet. Network access to fetch the pinned OSCAL
schemas and the Utopia repository was verified available in this environment
(`curl` to github.com succeeded), so the blocker is session time, not an
environment constraint. This must not be read as "attempted and blocked."

## Why P1 went first

The task's own reuse contract makes this ordering explicit: P0-R is required
"before freezing backend/interchange choices" for P2's canonical store, but
P1's corrections (temporal selection, approval bypass, unit-conversion
conflicts, cosmetic-connector erasure, review revocation, stale-citation
matching) are self-contained fixes to existing code that do not depend on
which backend P2 eventually adopts. Given a single session's time budget,
landing verified, tested fixes for seven live dangerous-verdict defects took
priority over an unstarted research spike whose own exit criterion
("executable interoperability fixtures, one backend decision") is a
multi-day artifact in its own right.

## What must happen before P2 starts

P2 ("Introduce the canonical versioned compliance store") **must not begin**
until R1-R6 actually run, per the task's explicit gate: "Before freezing its
backend, run the bounded Utopia/native comparison in task P0-R." Skipping
straight to a SQLite-only P2 implementation without that comparison would
violate the task's own sequencing, not merely skip a nice-to-have.

## Recommended next step (not yet executed)

Time-box P0-R to one session: build the two-fixture R2 comparison first
(cheapest to falsify — either Utopia's adapter clearly reduces work or it
doesn't), decide the backend, then do the OSCAL schema-validation spike (R1)
in parallel since it does not depend on the R2 outcome. Do not reopen R2 as
an open-ended evaluation once the fixture comparison returns a result.
