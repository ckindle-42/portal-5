# Compliance judgment probe — TASK_COMPLIANCE_REASONING_V6 D0

`judgment_probe_v6.jsonl` — 30 authored cases measuring whether a candidate
seat model can carry the *judgment* step of the compliance gate: given a
pre-analyzed governing compliance unit (CU) and a candidate internal
implementation, render the determination a human reviewer would.

**Authored 2026-09-06, before any D0-M model pull** (check Y26). Three labels
(P6J-05, P6J-17, P6J-18) were revised **after** the 12-seat sweep — an
11-seat consensus and review agreed a packet-only reviewer reads those as a
violation, not a partial match; each revised row carries a `label_revised`
field. Re-scored offline with `--rescore` (no model re-run). The probe hands
the seat *raw* governing text, so two-conjunct decomposition (P6J-14) and
role-alias resolution (P6J-19) — which the deployed gate does deterministically
before the council sees the packet — are harder here than in the real
pipeline; those labels are kept as-is with that caveat.

Governing text is verbatim public NERC CIP standard text drawn from
`portal/modules/compliance/data/nerc_cip_register.json` (itself extracted
from the published PDFs). Candidate implementation snippets are authored for
this probe — they are *not* drawn from the LSPG-CIP private corpus, so this
file carries no confidential material and is committed to the repo.

## Schema (one JSON object per line)

| field | meaning |
| --- | --- |
| `id` | stable case id `P6J-NN` |
| `category` | `SUPPORTED` `GAP` `CONTRADICTION` `PARTIAL` `OUTDATED` `ABSTAIN` |
| `governing_ref` | register node id — the citation the judge must return |
| `governing_text` | verbatim NERC CIP text of that Part |
| `premises` | defined terms / scope facts the judge is given (the gate's job) |
| `candidate_text` | authored internal implementation snippet, or `null` when none exists |
| `packet_complete` | `true` unless the packet is deliberately insufficient |
| `gold_label` | `SUPPORTED` `PARTIAL` `CONTRADICTED` `ABSENT` `ABSTAIN` |
| `gold_finding_type` | `null` \| `GAP` \| `CONTRADICTION` \| `OUTDATED_LANGUAGE` \| `WEAK_MAPPING` |
| `gold_citation` | list of register refs the answer must cite |
| `must_not_flag` | `true` for stricter-than-required cases that must stay `SUPPORTED` |
| `rationale` | why the label is what it is |

## Scoring (P8 uses the same definitions)

- **F2 primary** (recall ×2): a missed violation (`gold` in
  {`PARTIAL`,`CONTRADICTED`,`ABSENT`} scored `SUPPORTED`) is the costly error.
- **violation-class accuracy** (`vca`): did the seat get the met / unmet /
  abstain *class* right, ignoring which unmet flavour? This is what a
  human-in-the-loop gate needs and it is robust to `PARTIAL`-vs-`CONTRADICTED`
  label ambiguity. Reported alongside F2; **`exact_accuracy` is not a headline**.
- **abstention honesty**: on `category == ABSTAIN`, anything other than an
  abstain/unresolved return is a hard miss; a spurious abstain on a
  `packet_complete` case is a soft miss.
- **citation discipline**: a determination whose cited refs are not a superset
  of `gold_citation`, or that cites a ref outside the packet, is a miss
  regardless of label.
- **schema validity**: non-parseable JSON output is a miss.
- **must-not-flag**: flagging a `must_not_flag` case as a violation is scored
  as a false positive *and* recorded separately (the "stricter is not a
  violation" property from Q08).

## Runner

`bench_judgment_probe_v6.py` (added in D0-M) runs every candidate seat and
emits `tests/benchmarks/results/judgment_probe_v6_<UTC>.json`.
