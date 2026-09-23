---
id: unit-compliance-prove-then-scale
kind: mixed
title: "PROVE_THEN_SCALE_V1 — the population as text, the mapping sweep, the review surfaces"
sources:
- type: code
  path: portal/modules/compliance/core/reading_material.py
- type: code
  path: portal/modules/compliance/core/sweep.py
- type: code
  path: portal/modules/compliance/core/contradictions.py
---

The PROVE_THEN_SCALE_V1 campaign's product code (report:
`reports/compliance/PROVE_THEN_SCALE_V1.md`).

`reading_material.py` renders a requirement's scope as the material a reading
reads: the standard's fixed body FIRST (byte-identical per revision, sha
recorded — the shared prompt-cache prefix and the cluster shard key), then the
requirement's own anchors, operator edges and notes, every entry labelled with
its side and standing. Operator sections arrive with their document
neighbourhood — parent heading, siblings in reading order, same-document
sections the graph ties to this requirement — capped at
`NEIGHBOURHOOD_MAX_SECTIONS`/`NEIGHBOURHOOD_MAX_CHARS`, the cap stated in the
rendered label.

`sweep.py` is the standard-ordered sweep: `STANDARD_ORDER` records the
dependency order and each placement's reason; `map_read` is the map unit —
one requirement, a deterministic population, one call, a receipt whose closure
carries the determination outcomes; `parse_determinations` reads the answer's
JSON block; `sweep_standard` runs one revision and measures the cache on
`prompt_eval_duration` (never `prompt_eval_count`); `reduce_standard` is the
reduce half — one call over the sweep's ANSWERS, never the populations;
`refs_for_standard` selects exactly one revision's nodes (family matching
double-read sibling revisions — measured, fixed); `sweep_answers` reloads a
standard's retained answers from the receipts.

`contradictions.py` is the operator's review-by-exception:
`scan_contradictions` surfaces cross-reading disagreement (relation conflicts,
determinations against human-rejected edges, disagreements with approved
edges); `drill_down` opens one answer — or one retained run by `run_id` — to
the verbatim text of every cited section on both sides.

Contract tests: `tests/unit/test_compliance_prove_then_scale.py`.
Measured live: `reports/compliance/prove_then_scale/`.

## Why

A reading can only be as good as the material it is handed and the
edges it is allowed to write. These three modules are the campaign's
answer: the population rendered complete and labelled (nothing for the
model to search for), the sweep that turns readings into typed,
provenance-carrying mapping edges under a checker that refuses what it
cannot trace, and the review surfaces that keep the human's queue down
to real questions.

## No reading runs on truncated material

Ollama does not refuse a prompt larger than the window. It truncates it
silently, and the answer comes back looking normal. In the LOAD_AND_CONVERSE
family sweep, CIP-003-8 R1 (155k bytes) and CIP-003-9 R1 (139k bytes) were
each counted at exactly 16,387 tokens against a 32,768 window. Each answered
from its last Part alone ("the material contains a single requirement ...
no operator sections"), with 65 and 67 operator sections sent, and determined
nothing. CIP-003-8 R2 was cut to 31,355 tokens and determined nothing.

`sweep.window_fit` now estimates every prompt before the call, at 3.3 bytes
per token (measured median 3.59, set to err high). A prompt that does not
fit goes to `overflow_model`, the same weights with a larger baked window,
or is recorded as a `context_overflow` error without a call. The route taken
is stamped as `context_fit` in the retained run.
