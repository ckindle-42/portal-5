# REGISTER_COMPLETENESS_V1 — corrective re-run

**Task:** `TASK_CIP_REGISTER_COMPLETENESS_V1` (PROGRAM_RETRIEVAL_AND_COMPLIANCE_V1,
corrective — follows T3 `5d1536cf`, T4 `53e36216`).
**Built at:** see `nerc_cip_register.json` `built_at` / `extractor_commit` / `source_pdfs`.

The register was materially incomplete and reported itself complete: `n_missing`
was a fidelity round-trip over the extractor's own output (§1.1). Every number
derived from it — coverage, Full-Gap recall, the change diff — was measured
against a denominator the extractor supplied to itself.

---

## What changed in the register

| | before (pre-P1) | after (P1–P4) |
|---|---|---|
| nodes | 152 | 254 |
| Parts | 130 | 232 |
| fidelity-verified | 152 / 152 | 254 / 254 |
| completeness holes (document-derived) | **not measured** — `n_missing` was a fidelity metric | **0** |
| `denominator_source` | (absent) | `document:*` per standard, never `"extractor"` |

**Per-standard Part count, before → after:**

| standard | before | after | new Parts |
|---|---|---|---|
| CIP-002-5.1a | 0 | 28 | R1 1.1–1.3, R2 2.1–2.2, Attachment 1 criteria 1.1–1.4 / 2.1–2.13 / 3.1–3.6 (+ 3 section parents) |
| CIP-003-8 | 15 | 35 | Attachment 1 sections 1–5 + sub-parts |
| CIP-003-9 | 16 | 40 | Attachment 1 sections 1–**6** + sub-parts (Section 6 = vendor electronic remote access) |
| CIP-012-2 | 0 | 5 | R1 1.1–1.5 |
| CIP-013-2 | 0 | 8 | R1 1.1, 1.2, 1.2.1–1.2.6 |
| CIP-014-3 | 0 | 17 | R1 1.1–1.2, R2 2.1–2.4, R4 4.1–4.3, R5 5.1–5.4, R6 6.1–6.4 |
| CIP-004..011 | unchanged | unchanged | table extraction was already correct |

No existing node's verbatim text changed except spliced running-header / page
markers removed by a widened `_norm` (`_RUNHDR_RE` + new `_PAGE_MARK_RE`).
Round-trip fidelity stays at 100%.

---

## 1. Coverage by enumeration — before → after

High-impact scope, all associated types, `2026-09-03`, deterministic proposer.

| | before | after |
|---|---|---|
| cells examined | 116 | 147 |
| substantively resolved | 116 | 147 |
| coverage breakdown | FULL 1 / PARTIAL 1 / NONE 114 | FULL 1 / PARTIAL 1 / NONE 145 |
| full gaps | 114 | 145 |

**All 31 new gaps are newly-*visible*, not new.** Every one was always uncovered
by the planted corpus; the register simply could not name it before. They are, in
full:

- CIP-002-5.1a: R1 1.1–1.3, R2 2.1–2.2, Attachment 1 Section 1 + criteria 1.1–1.4
- CIP-012-2: R1 1.1–1.5
- CIP-013-2: R1 1.1, 1.2, 1.2.1–1.2.6
- CIP-014-3: R1 1.1–1.2, R2 2.1–2.4, R4 4.1–4.3, R5 5.1–5.4, R6 6.1–6.4

**Nine R-level rows vanished** from the gap list — replaced by their Parts:
`CIP-002-5.1a R1/R2`, `CIP-012-2 R1`, `CIP-013-2 R1`, `CIP-014-3 R1/R2/R4/R5/R6`.
An SME reading the matrix sees the same obligations at finer grain, not a
regression.

**Conclusion moved:** the T3 coverage matrix's "114 gaps" was an undercount over
a partial denominator. The real applicable-Part count for this scope is higher;
the matrix now enumerates it.

## 2. Planted corpus — Full-Gap recall

| | before | after |
|---|---|---|
| Full-Gap recall (headline) | 0.8¹ | **1.000** |
| false-covered | 0 | 0 |
| false-gap | 0 | 0 |
| citation resolution | 1.000 | 1.000 |

¹ 0.8 is the *pre-fix* number once `OT-POL-012` (deontic) is scored against a
Part id: before P2 that plant targeted the R-level `CIP-012-2 R1`, which the
enumeration skips once R1 carries Parts, so it read `MISSING_FROM_MATRIX`. The
plant is retargeted to `CIP-012-2 R1 Part 1.1` (the obligation it actually
conflicts with). **Denominator of the 1.000: 4 planted holes** (`hole`,
`aspirational`, `lexical`, `deontic` control classes), each on a register Part
that exists. §1.6's caveat stands — the planted corpus can only plant a hole in a
Part that exists, so 1.000 means "we find the holes we planted", not "the
register is complete". The completeness metric (§1.3 signals, document-derived)
is the independent check that it is.

## 3. `CIP-003-8 → CIP-003-9` diff — before → after

| | before | after |
|---|---|---|
| diff rows | 13 | 22 |
| substantive | 2 | 6 |
| cosmetic | 11 | 16 |

**Substantive, after:**

1. `LANGUAGE_CHANGED substantive` R1 1.2.6 — "CIP Exceptional Circumstances" →
   "Vendor electronic remote access security controls" (new obligation at that id)
2. `RENUMBERED paired` R1 1.2.6 → 1.2.7 — shift-insert, text identical
3–6. `PART_ADDED` Attachment 1 **Section 6** + 6.1 + 6.2 + 6.3 — the vendor
   electronic remote access *program*

**The T4 documented false negative is resolved.** `CHANGE_PIPELINE_V1.md` recorded
"New Attachment 1 Section 6 — Diff missed it — false negative" because Attachment
1 content was not in the register. It is now (`_cip003_attachment1`), and the diff
raises it as `PART_ADDED`. Diff-false-negatives vs the T4 ground truth: **1 → 0**.

The extra cosmetic rows (11 → 16) are the Attachment 1 sub-parts picking up the
same U+002D → U+2010 hyphen re-encoding already seen on the R1 topic list — counted
separately, never raised as obligation changes.

## 4. `nerc_cip_map.json`

Derived view — regenerated by `python -m portal.modules.compliance.core.cip_register
build`. 254 entries. `related_800_53` seed unchanged (R-level, advisory).

## 5. Applicability gate (§1.4 / P4.5)

The register's applicability dimension now has an authoritative source:
`applicable_systems` on the CIP-002 Attachment 1 criteria carries the impact tier
("High Impact Rating (H)…"), and CIP-003 Attachment 1 sections 1–6 are register
Parts. `applicability.py` `gate_presentation()` no longer disclaims the `low`
dimension as un-gateable. The `[GATE]` itself is unchanged — asset scope is still
operator input; what changed is that the register can now *express* what a `low`
selection includes.

---

## Remaining, recorded

- **CIP-014-3 R6 6.1–6.4** are extracted, but R6's lead-in ends in a period, so
  the §1.3 colon signal never flagged R6 — they were caught by running the prose
  extractor on every part-less requirement, not by a completeness signal. A
  period-terminated lead-in with a following numbered list is a weaker structural
  signal; no false positives on the current 14 standards.
- **CIP-003 Attachment 1 section-level nodes** carry the section lead-in as
  verbatim text (not the whole section body) to keep the version diff from
  misreading accumulated hyphen re-encodings as substantive. The sub-parts are the
  addressable obligation units.
- **`fetch_pdfs` does not fetch `cip-003-8.pdf`** (it is not a current standard);
  the build picks it up if present in the PDF dir. `_ARCHIVED_STANDARDS` documents
  the dependency.
