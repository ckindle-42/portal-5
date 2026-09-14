# READING_IS_PRODUCT_V1 — D0 Discovery

**Task:** `coding_task/TASK_COMPLIANCE_READING_IS_THE_PRODUCT_V1.md`
**Derived at:** 2026-09-14
**HEAD:** `2b666477` (`docs(known-limitations): log the CI-only test_draft_revisions_is_proposal_by_default flake`)
**Working tree at entry:** clean. No concurrent work, no stash to preserve, nothing untracked.

Everything below was re-derived from the live tree. Where a line number in the
task file has moved, HEAD wins and the new location is recorded.

---

## 0.1 — The seven defect sites

All seven exist at HEAD, at the shape the task describes. Line drift is minor.

| # | Site | Stated | At HEAD | Verbatim at HEAD |
|---|---|---|---|---|
| — | council seat suppression | `council.py:186-201` | `council.py:199` | `"think": False,` with `"options": {"temperature": 0.0, "num_predict": 900}` |
| — | alignment seat suppression | `obligation_alignment.py:766-792` | `obligation_alignment.py:783` | `"think": False,` with `"num_predict": output_budget` |
| — | reporter | `assessment_report.py:87-92` | unchanged | falls through to `council._ollama_seat` |
| D1 | UNKNOWN veto | `assessment.py:455-456` | `assessment.py:455-456` | `unknown_links = [r for r in alignment.records if r.relation == "UNKNOWN"]` / `if not alignment.valid or unknown_links:` |
| D2 | fabricated operand voids vote | `obligation_alignment.py:292-301` | `obligation_alignment.py:300` | `valid, reason = False, f"seat {seat_id}: invalid numeric binding"` |
| D3 | bad binding downgrades quorate SAME | `obligation_alignment.py:471-472` | `obligation_alignment.py:472` | `raise ValueError(f"seat {seat_id}: invalid numeric binding for {link_id}")` |
| D4 | bindings validated only on SAME | `obligation_alignment.py:292` | same | `if valid and record["relation"] == "SAME":` |
| D5 | whitespace-only quantity match | `obligation_alignment.py:566-568` | `obligation_alignment.py:566-567` | `pattern = rf"(?<![\d.]){value}(?![\d.])\)?\s+(?:(calendar\|business)\s+)?{re.escape(unit)}s?\b"` |
| D6 | substring cite-or-drop | `council.py:161-163` | `council.py:161-163` | `return any(r == a.lower() or r in a.lower() or a.lower() in r for a in allowlist)` |
| D7 | FULL has one check | `assessment_report.py:414` | `assessment_report.py:415` | `return f"FULL requires a SUPPORTED decision, got {decision!r}"` |
| — | packet docstring | `gate.py:94-95` | `gate.py:94-95` | `"""The structured-JSON packet the council seat receives — a` / `pre-analyzed problem, never raw text (P5)."""` |
| — | Part verbatim in packet | `gate.py:457` | `gate.py:457` | `"verbatim_text": part_text,` — present, as the task says |

`gate._substantive` is at **`gate.py:503`**, not `:506` as stated. It is
module-private and called once internally (`gate.py:377`). Phase 6 promotes it to
`is_substantive` with a private alias, as the task directs.

---

## 0.2 — Intent coverage census

`Register.load()` at HEAD:

```
nodes                254
with measure_text     99
with source_pages     99
standards             14
```

Per standard:

| standard | nodes | with source_pages | with measure_text |
|---|---:|---:|---:|
| CIP-002-5.1a | 33 | 0 | 0 |
| CIP-003-8 | 39 | 0 | 0 |
| CIP-003-9 | 44 | 0 | 0 |
| CIP-004-7 | 19 | 19 | 19 |
| CIP-005-7 | 12 | 12 | 12 |
| CIP-006-6 | 14 | 13 | 13 |
| CIP-007-6 | 20 | 20 | 20 |
| CIP-008-6 | 11 | 10 | 10 |
| CIP-009-6 | 10 | 10 | 10 |
| CIP-010-4 | 12 | 11 | 11 |
| CIP-011-3 | 4 | 4 | 4 |
| CIP-012-2 | 6 | 0 | 0 |
| CIP-013-2 | 11 | 0 | 0 |
| CIP-014-3 | 19 | 0 | 0 |

**Correction to the task file (Phase 9).** The task says *"six standards recording
no `source_pages` at all (CIP-005/008/009/010/011)"*. That is wrong on both counts
at HEAD: it is **six standards** — CIP-002-5.1a, CIP-003-8, CIP-003-9, CIP-012-2,
CIP-013-2, CIP-014-3 — and the five it names (CIP-005/008/009/010/011) are among
the **best**-covered, at 10/11 to 20/20. `source_pages` and `measure_text` coverage
are identical per node (99/254 each), which is consistent: both come from the same
table extraction, and the six uncovered standards were ingested by a path that
produced neither. Phase 9 targets the six standards actually recording none.

**(e) confirmed.** `grep -rn measure_text portal/ --include='*.py'` returns
consumers in `cip_extract`, `cip_register`, `policy_graph` (`evidence_guidance`)
and `register_diff`. **No assessment consumer.** `resolve_governing_bundle` does
not read it. 155 of 254 nodes carry no Measures text at all.

---

## 0.3 / 0.4 / Phase 1 — The CI failure, and the real cause

`uv run pytest tests/unit/test_compliance_change_pipeline.py::test_draft_revisions_is_proposal_by_default -q` → **1 passed** on this machine.

```
STORE_PATH = portal/modules/compliance/data/compliance_store.db
exists = True   size = 10,997,760 bytes   rows = 1067
```

So the mac/CI split reproduces exactly as `P5-CI-DRAFT-REVISIONS-FLAKE-001`
describes, and the task's diagnosis — the assertion depends on an ambient
`MappingStore` — is **correct in direction**.

### The task's stated fix does not work, and the numbers in it are wrong

The task asserts *"`impact_report(..., store=...)` already has an injection seam"*
and that an empty store yields `examined 6, resolved 0, specs 0`. Measured on
this checkout with a genuinely empty store passed as `store=`:

```
EMPTY  examined 6  resolved 6  specs 18     <- not 0/0
SEEDED examined 6  resolved 1  specs  1
```

The empty store produced **more** specifications than the seeded one. Root cause,
traced to the line:

```python
# change_pipeline.py:63
store = store or MappingStore()
```

`MappingStore` defines `__len__` (`mapping_store.py:247`). An empty store is
therefore **falsy**, and `store or MappingStore()` silently discards the injected
store and constructs the ambient one at `STORE_PATH`:

```
len(empty) = 0   bool(empty) = False
(empty or MappingStore()).path -> portal/modules/compliance/data/compliance_store.db
```

Directly probed, the injected store is genuinely empty — `all_for("CIP-003-8 R1 Part 1.2.6")`
returns `[]` — yet `impact_report` reported 3 mapped sections per row, because it
was never using it.

**The injection seam is broken.** Passing `store=` only works when the store is
non-empty; the one case the regression guard needs — an empty store — is exactly
the case the fallback swallows. Writing the Phase 1 fixture against this seam
would have produced a test that passes for the wrong reason on a clean checkout
and asserts nothing at all.

The same defect exists at a second site: `coverage.py:503`, `store = store or MappingStore()`.

Phase 1 therefore fixes the seam (`store if store is not None else MappingStore()`
at both sites) before repairing the fixture. Per the standing rule *root-cause,
not workaround*: this is a production bug — any caller injecting an empty or
newly-created store is silently reading 1067 ambient rows — not merely a test
concern.

---

## 0.5 — Configured seats and their thinking capability

`config/compliance/council.yaml` exists (tracked, `a0ee8280`) and its roster is
identical to `runtime_config._DEFAULT_SEATS`. Quorum `0.66` → 2 of 3.

Probed live against `http://localhost:11434/api/chat` with `"think": true`:

| seat id | model | `think:true` | evidence |
|---|---|---|---|
| `qwen38` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | **supported** | 200, `message.thinking` = 72 chars, 28.3 s cold |
| `granite41` | `granite4.1:30b-ctx16k` | **not supported** | `HTTP 400 {"error":"\"granite4.1:30b-ctx16k\" does not support thinking"}` |
| `mistral` | `mistral-small3.2:24b-instruct-2506-q4_K_M` | **not supported** | `HTTP 400 {"error":"\"mistral-small3.2:24b-instruct-2506-q4_K_M\" does not support thinking"}` |

**This bounds Phases 2 and 3 and must not be papered over.** Restoring reasoning
reaches **one of three council seats** on the current roster. The other two
downgrade to a non-reasoning call — which the Phase 3 transport records
explicitly rather than presenting as a reasoning answer. Under
`PROMOTE_POLICY: confirm` this task does not swap either seat for a thinking
model; the ceiling is recorded here and carried into the Phase 2 report and the
Phase 10 qualification.

The alignment seat and the reporter are separate call sites and are not bound by
the council roster; their reasoning restoration is unaffected by this ceiling.

Also confirmed: `message.thinking` comes back as its own field, separate from
`message.content` — the premise Phase 3 rests on (that `/api/chat` does not need
`think:false` to keep strict JSON clean) holds on this Ollama build.

---

## 0.6 — The boundary change, recorded

> The implementation brief's council-change boundary (§9: no council prompt,
> roster, quorum, override or arithmetic change) was written to stop an agent
> tweaking the judge until the suite went green. It is superseded **only** for
> the prompt/transport/packet changes in Phases 3–5, on the operator's 2026-09-14
> instruction, and under these conditions: no gold label moves, no case
> expectation is edited, the identical 26-case suite is re-run, and every
> before/after delta is recorded per case. Quorum, roster and arithmetic are
> untouched by this task.

---

## Other HEAD corrections carried forward

- **Acceptance fixture key.** `tests/data/compliance_reading_acceptance.json` is a
  dict with `cases`, 26 entries, ids `01`–`26`. Each case's expectation field is
  **`expected`**, not `expect` as the Phase 2 script draft assumes. The Phase 2
  script uses `expected`.
- **`_SCOPE` must be declared.** `impact_report` raises on an undeclared
  `AssetScope`; the Phase 1 fixture reuses the module's existing declared `_SCOPE`.
- **`MappingStore` is already imported** by `tests/unit/test_compliance_change_pipeline.py`,
  so the Phase 1 fixture needs no new import.
