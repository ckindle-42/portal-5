# CHANGE_PIPELINE_V1 — rollup

`TASK_COMPLIANCE_CHANGE_PIPELINE_V1` (program `PROGRAM_RETRIEVAL_AND_COMPLIANCE_V1`
track T4). Built on T3's register, mapping store, and coverage matrix.

> **Superseded in part (2026-09-03):** the `CIP-003-8 → CIP-003-9` diff numbers
> below (Phase 1 / Phase 3) were measured against an incomplete register.
> `TASK_CIP_REGISTER_COMPLETENESS_V1` P4 re-ran the diff on the corrected
> register: **22 rows, 6 substantive, 16 cosmetic**; the "Attachment 1 Section 6
> false negative" is **resolved** (raised as `PART_ADDED`). See
> `reports/compliance/REGISTER_COMPLETENESS_V1.md`. The originals are kept below
> as a correction, not deleted.

**Status:** delivered. `CIP-003-8 → CIP-003-9` produces a typed Part-level diff;
every affected mapping has its validity closed with a `NEEDS_REVIEW` successor
that does not inherit a verdict; prospective analysis is temporally segregated;
the drafting gate is on the operator's desk.

Code: `portal/modules/compliance/core/register_diff.py`,
`portal/modules/compliance/core/change_pipeline.py`.
Tests: `tests/unit/test_compliance_change_pipeline.py` (13, all green).
Wiki: `unit-compliance-change-pipeline`,
`unit-known-limitations-compliance-implicit-change-recall`.

---

## Phase 1 — the `CIP-003-8 → CIP-003-9` diff

19 old nodes → 20 new nodes. **13 diff rows: 2 substantive, 11 cosmetic.**

| # | change_type | sub_type | old → new | substantive | note |
|---|---|---|---|---|---|
| 1 | RENUMBERED | paired (conf 1.00) | R1 1.2.6 → R1 1.2.7 | yes | shift-insert; "Declaring and responding to CIP Exceptional Circumstances" text identical, id moved down one |
| 2 | LANGUAGE_CHANGED | substantive | R1 1.2.6 → R1 1.2.6 | yes | old: *"Declaring and responding to CIP Exceptional Circumstances"* → new: *"Vendor electronic remote access security controls"* — a **new obligation** inserted at this id |
| 3–11 | LANGUAGE_CHANGED | cosmetic | R1 1.1.1 … 1.1.9 | no | U+002D → U+2010 hyphen re-encoding in the topic list; no wording change |
| 12 | LANGUAGE_CHANGED | cosmetic | R1 1.2.5 | no | trailing list conjunction `"; and"` dropped when 1.2.6 was inserted after it — list glue, not an obligation change |
| 13 | LANGUAGE_CHANGED | cosmetic | R2 | no | `CIP-002` → `CIP‐002` hyphen re-encoding (a spliced running header was stripped from the register in this task — see Phase 3) |

The cosmetic rows are **not** raised as obligation changes; they are counted and
reported separately (`diff_summary`), never folded into the substantive count.

## Phase 3 — verification against the implementation plan

The NERC Project 2020-03 implementation plan PDF is not machine-fetchable from
this environment (`403` via WebFetch, `404`/binary via the fetch MCP). Fell back
to the **public record**: FERC Order approving CIP-003-9 (supply-chain risk
management for low-impact BES Cyber Systems), the NERC CIP-003-9 Technical
Rationale, and multiple secondary compliance summaries. Recorded as
*verified-against-public-summary, implementation-plan PDF unverified*.

Ground truth for the transition:

1. **New Part 1.2.6** — "Vendor electronic remote access security controls" added
   to the R1 low-impact policy-topic list. **Diff caught it** (row 2).
2. **Old 1.2.6 → 1.2.7** — "CIP Exceptional Circumstances" shifted down. **Diff
   caught it** (row 1).
3. **New Attachment 1 Section 6** — the actual vendor electronic remote access
   *program* (identify active vendor connections, disable them, detect malicious
   inbound/outbound comms). **Diff missed it — false negative.** Attachment 1
   content is not extracted to register Parts (T3 `T3-COMPLIANCE-REG-001` item 2);
   this is an extraction-surface gap, not a diff-engine defect.
4. Effective date **2024-04-01** for the standard; the vendor-remote-access
   obligations carry a delayed **2026-04-01** enforcement date. The register
   pins the whole standard at 2024-04-01 — the delayed sub-date is not modelled
   (`honest-BLOCKED`, noted below).

**Counts, separate:** diff false negatives vs the ground truth = **1** (Attachment
1 Section 6). Diff rows the ground truth does not mention = **11**, all correctly
typed `cosmetic` and suppressed — **0 spurious substantive rows.**

## Phase 4 — mapping validity and coverage invalidation

With one approved mapping `OT-POL-003 §6.1 → CIP-003-8 R1 Part 1.2.6` (verdict
FULL):

- `expire_mappings(store, rows, "2024-04-01")` → **1 mapping expired**
  (`valid_to` closed), **1 successor** created against `CIP-003-9 R1 Part 1.2.6`
  as `NEEDS_REVIEW`, `confidence 0.0`, `source="successor_of_expired"`. The FULL
  verdict is **not** carried forward.
- The 1.2.5 mapping is untouched — its change was cosmetic (Phase 1 row 12).
- Coverage delta: the 1.2.6 cell moves `FULL → NEEDS_REVIEW` for the transition;
  `coverage_delta_for_transition` reports the move rather than a silent
  recompute.

## Phase 5 — prospective analysis

`prospective_report(reg, scope, as_of="2024-06-01")` → **1 future-effective
requirement**: `CIP-012-2 R1` (`valid_from 2025-07-01`). Every row is
`prospective: True`; enforcement date renders as *"SEE Implementation Plan —
verify, do not infer"* where the register has none. The report's own contract
line states it MUST NOT reach a "what must we do today" answer;
`test_prospective_output_is_marked_and_never_a_today_obligation` enforces it.

## Phase 6 — drafted revisions `[GATE]`

**Reported, not chosen.** `draft_revisions(impact)` runs in the only implemented
mode, **(a) specification-only**: for each work item it emits the policy section,
the motivating Part, the change type, both verbatim spans, and
`drafted_replacement: null`. Modes **(b) draft-as-proposal** and **(c)
draft-into-revision** raise `NotImplementedError`.

- 2 sections flagged for revision on the `CIP-003-8 → -9` transition.
- Recommendation to the operator: (a) adds no new risk surface; a generated
  draft reads as finished work and is accepted more uncritically than a gap
  statement (`granite-4.1-8b` was demoted from this persona for fabricating
  regulatory requirements). If (b)/(c) is wanted, the successor mapping's
  `NEEDS_REVIEW` state is the natural review queue to attach it to.

## Phase 7 — verification suite

`tests/unit/test_compliance_change_pipeline.py`, 13 tests, extends T3's tiers.

**Tier 0 — invariants.** Every diff row carries both verbatim spans; no mapping
inherits a verdict across a `LANGUAGE_CHANGED`; prospective output is marked and
never a "today" obligation.

**Tier 1 — the real transition.** Row-for-row assertions on `CIP-003-8 → -9`
(renumber to 1.2.7, substantive language change on new 1.2.6, ≥5 cosmetic rows
suppressed).

**Tier 2 — planted change controls:**

| control | result |
|---|---|
| explicit change (text edited) | detected, typed `TIMELINE_CHANGED` |
| implicit change (no changelog) | detected — same code path, no changelog input exists |
| modality change (`shall` → `should`) | typed `modality`, not `substantive` |
| timeline change (35d → 15d) | typed `TIMELINE_CHANGED`, `substantive`, both values in `detail` |
| cosmetic change (hyphen + punctuation) | **not** raised as an obligation change |
| renumber (same text, new id) | paired at confidence ≥ 0.9; a low-similarity pair falls back to `PART_ADDED` + `PART_REMOVED`, never silently mispaired |
| inapplicable change (out of scope) | `informational`, `work_items == 0` |
| mapping expiry | `valid_to` closed, successor `NEEDS_REVIEW`, verdict not inherited |
| future-effective change | in the prospective report, absent from "today" |

**Metrics, separate, never averaged:**

- **Change-detection recall (headline):** substantive changes present in the
  register surface — **2 / 2** on the real transition. Against the full ground
  truth including Attachment content — **2 / 3** (the miss is the un-extracted
  Attachment 1 Section 6, `T4-COMPLIANCE-CHANGE-001`).
- **Cosmetic false-positive rate:** 0 / 11 cosmetic rows misclassified as
  substantive.
- **Renumber pairing precision:** 1 / 1 correct (the 1.2.6→1.2.7 shift-insert);
  0 spurious pairs.
- **Mapping-invalidation completeness:** 1 / 1 — the single mapping targeting a
  substantively-changed Part was expired; the cosmetically-changed Part's
  mapping was correctly left alone.

## honest-BLOCKED

- **Implementation-plan PDF not fetchable** from this environment — Phase 3
  verified against the FERC order + technical rationale + secondary summaries
  instead, recorded as such. Not presented as a verified-against-plan diff.
- **Delayed sub-effective date** (2026-04-01 for the vendor-remote-access
  obligations within an otherwise-2024-04-01 standard) is not modelled; the
  register pins the standard at one `valid_from`. A Part-level effective-date
  override is future work.
- **Attachment / prose change detection** — inherited ceiling from T3; stated in
  `KNOWN_LIMITATIONS.md` (`T4-COMPLIANCE-CHANGE-001`) and
  `unit-known-limitations-compliance-implicit-change-recall`.

## Register hygiene fix (in this task)

`cip_extract._norm` now strips a spliced NERC running header
(`CIP-003-9 ‐ Cyber Security — Security Management Controls 5`) that pymupdf had
folded into the `CIP-003-9 R2` requirement string across a page break. One
register node was patched in place (grep-confirmed the only occurrence); future
rebuilds are clean. This also protects T3's verbatim-citation guarantee — the
persona quotes that text directly.
