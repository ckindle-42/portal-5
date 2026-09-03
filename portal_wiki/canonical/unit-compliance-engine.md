---
id: unit-compliance-engine
kind: mixed
title: "Compliance reasoning engine — bitemporal CIP register"
sources:
- type: code
  path: portal/modules/compliance/core/__init__.py
- type: code
  path: portal/modules/compliance/core/cip_extract.py
- type: code
  path: portal/modules/compliance/core/cip_register.py
- type: code
  path: portal/modules/compliance/core/tiers.py
- type: code
  path: portal/modules/compliance/core/engine.py
- type: code
  path: portal/modules/compliance/core/applicability.py
- type: code
  path: portal/modules/compliance/core/mapping_store.py
- type: code
  path: portal/modules/compliance/core/coverage.py
- type: code
  path: portal/modules/compliance/data/nerc_cip_register.json
- type: code
  path: tests/unit/test_cip_register.py
- type: code
  path: tests/unit/test_compliance_tiers.py
- type: code
  path: tests/unit/test_compliance_engine.py
claims: []
confidence: high
tags:
- compliance
- authored-v1
---

`portal.modules.compliance.core` builds the compliance reasoning engine
(TASK_COMPLIANCE_ENGINE_V1) as a *second composition* of the retrieval stage
library — its own routes, its own `compliance_*` tables, its own pipeline
stages. It changes no shared retrieval behaviour and invalidates no other
consumer's index.

## Not a RAG chatbot

Four properties, none a retrieval parameter: temporal validity filters *before*
ranking; authority tiers have precedence and a cross-tier contradiction is
emitted, never reconciled; gaps come from enumeration over the register, not
from asking; settled `requirement -> document` mappings are human-owned and
double as the evaluation set.

## The bitemporal register (Phase 1)

Nodes are requirement **Parts**. The temporal model is **validity-time** —
`valid_from` / `valid_to` are when a requirement *is enforceable*, true
independent of ingest. `graph_memory`'s observation-time schema (`first_seen` /
`last_seen`) is deliberately NOT reused.

`cip_extract.extract_standard` pulls every `Table R<n>` row verbatim from the
NERC CIP standard PDFs (line breaks reflowed, the PDF bullet glyph normalised —
the words and their order are exactly the source's); `verify_parts` round-trips
every extracted string back against the raw page text so a hole is visible as a
hole. `cip_register.build_register` attaches lifecycle + validity from a
public-record effective-date table and derives `HAS_REQUIREMENT`,
`CROSS_REFERENCES`, `SUPERSEDES` / `SUPERSEDED_BY` edges.

Committed artifact: `data/nerc_cip_register.json` (NERC standards are public
record). Rebuild: `python -m portal.modules.compliance.core.cip_register build`.

### Coverage vs the pre-existing 27-entry map

The old `nerc_cip_map.json` was 27 R-level entries with paraphrased titles and
no requirement text, on the superseded CIP-003-8 / CIP-012-1. The register is
**45 requirements, 99 verbatim Parts** across 8 regular-table standards
(CIP-004/005/006/007/008/009/010/011) plus R-level verbatim for CIP-002 / -003 /
-012 / -013 / -014, whose obligations live in prose or an Attachment — those
Attachment parts are the documented Phase 1 shortfall. Versions are resolved to
the enforceable ones (CIP-003-9, CIP-012-2). `nerc_cip_map.json` is now a
*derived* view of the register.

`nerc_cip_requirement()` keeps its signature and answers at Part granularity
(exact Part, or an R-level rollup of every Part).

## Authority tiers and COMPLIANCE_CONFLICT (Phase 3)

`core/tiers.py` — Tier 0 standard · Tier 1 implementation plans / RSAWs /
compliance guidance / FERC orders · Tier 2 policy · Tier 3 procedure · Tier 4
evidence; an unrecognised document class is Tier 4 so it can never silently
override a standard. `detect_conflicts` compares spans of *different* tiers: a
quantitative disagreement (*15 calendar months* vs *18 months*) or a deontic one
(*shall* vs *should*) emits `COMPLIANCE_CONFLICT` carrying both spans, both
tiers, both citations — **never reconciled, never averaged, lower tier never
wins**. It is a code rule with its own test (`test_compliance_tiers.py`), not a
prompt instruction.

## Temporal filter + routing + coverage (Phases 2, 4-6)

- `core/engine.py` — `effective_parts(reg, date)` is a **predicate**, not a
  score: a node reaches a "today" query only if `EFFECTIVE` and
  `valid_from <= date < valid_to`. `future_effective_parts` is the "what's
  coming" set, visible before its enforcement date. `classify_intent` is **one**
  keyword-scored call (four paths — today / change / gaps / freeform), not an
  agent swarm — 8192 tokens in, ~52 s per search.
- `core/mapping_store.py` — the system `propose()`s `requirement -> document`;
  an SME `approve()`s. Approved rows short-circuit retrieval and win over model
  judgement; a corrected coverage token is recorded as an override, and the
  **SME override rate** is the trust signal. Approved rows accumulate as the
  labelled eval set. The operator's mappings never leave their machine.
- `core/applicability.py` — the `[GATE]`. Dimensions (`impact_present`,
  `associated_present`, `has_erc`, `has_control_center`) are derived from the
  register's `applicable_systems` column. `AssetScope` is **operator input** —
  `coverage_matrix` raises without a declared one. `gate_presentation()` reports
  the schema and what each choice includes/excludes; it never infers a scope.
- `core/coverage.py` — enumerate applicable `EFFECTIVE` Parts; approved mappings
  short-circuit; classify policy / procedure / evidence **separately**. A `FULL`
  needs a locatable span from **both** the policy and procedure side. The
  summary reports **examined** apart from **substantively resolved** (Bully gate
  GP) — `test_compliance_engine.py` fails if they collapse.

## Why

A summarised requirement cannot support the verbatim gap-quoting the persona
contract demands, and every citation built on it is unverifiable — so extraction
is verbatim and round-trip-verified, and a Part that does not verify is reported
missing rather than silently dropped, because a missing Part reads as "no gap",
the most dangerous output this engine can emit. Validity-time rather than
observation-time is the one schema change from `graph_memory`: CIP-007-6 is
enforceable from 2016-07-01 whether or not we have ever looked at it, and a
retired version must not be retrievable for a "what must we do today" question.
The register replaces a 27-entry map that was both paraphrased and pinned to
superseded versions — two disagreeing sources of truth that the persona was
instructed to treat as authoritative.
