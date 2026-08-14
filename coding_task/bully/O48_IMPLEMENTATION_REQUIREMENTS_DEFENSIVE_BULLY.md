# IMPLEMENTATION_REQUIREMENTS_DEFENSIVE_BULLY

The constraints and requirements the next coding-agent planning session must
satisfy to turn this design into a build program and task files. **This is not a
task list and contains no `TASK_*.md`.** It is the boundary conditions,
contracts, dependencies, ordering, and definition-of-complete the build must
respect. The build program and task files are produced *by the next session*,
which first re-verifies HEAD.

---

## Authoritative sources (read in this order)

1. `DESIGN_DEFENSIVE_BULLY_FINAL.md` — what to build (authoritative on scope).
2. `ARCHITECTURE_DEFENSIVE_BULLY.md` — code homes, call paths, integration.
3. `INTERFACES_DEFENSIVE_BULLY.md` — contracts per boundary.
4. `DATA_MODEL_DEFENSIVE_BULLY.md` — structures, identity, lifecycle.
5. `MIGRATION_DEFENSIVE_BULLY.md` — dispositions + retirement order.
6. `VALIDATION_DEFENSIVE_BULLY.md` — proof bar per capability.
7. `REVIEW_DEFENSIVE_BULLY_CURRENT_STATE.md` — evidence for every claim.
8. Repo at build-session HEAD — **wins over all of the above on any code fact.**

---

## Target architecture (required end state)

The 16 components of `DESIGN` §component-model, wired per `ARCHITECTURE`, with
Red untouched, the Episode as the Red→Bully bridge, and all six feeds
demonstrably closing (not merely storing). The bench path repositioned as the
model-acceptance harness. Everything under `portal/modules/security/` (+ a new
`council_objection.py` beside the platform council), respecting MCP isolation.

## Required components (must all exist and be proven)

SUB, ORG, BR-COUSIN, BR-DRIFT, LOOP, BIN, HEART, MUT, SCORE, TGT, PLT, HND,
HARV, TRAIN, PLAY, ROSTER — each meeting its `INTERFACES` contract and its
`VALIDATION` proof. A component that cannot be proven on real data is
honest-BLOCKED, not marked done.

## Required integrations

Platform council (`aggregate_opinions` + new gate beside), platform agent loop
(`decide`/`rank` via `CapabilityProvider`), ORG MCP (`rag_mcp` :8921, embed
:8917, rerank :8925), MITRE MCP (:8929), Detections MCP (:8932) + `siem/`, model
CLI (`import-gguf`), config (`portal.yaml` → `sync_config`), CLI subcommands off
`core/__main__.py`, validation registry (`scripts/validation/*`).

## Reuse / retrofit / replace / retire (from MIGRATION)

- **REUSE:** `episode.py`, `platform.agent`, `council.py`, `emergent_gaps.py`,
  `recall_attribution.py`, `scoring.py`, `siem/*`, `models.py`, `candidate_eval.py`,
  `multichain.py` (unchanged), `investigation/*` (record engine), `capability_
  graph` entities.
- **RETROFIT:** `loop.py`/`loop_cli.py`, `playbooks.py`, `drift_gate`/`drift_cli`,
  `unknown_defense.py`, `rag_mcp` (new corpus+wrapper), `council_agreement.py`,
  `growth_loop.py` (→ HND proof), `capability_graph` (persist), bench path
  (→ acceptance).
- **REPLACE:** token-overlap-as-decision (→ composite metric); placeholder-True
  proof legs (→ real proofs); vote-only council flattening (→ objection gate);
  cold-rebuild coverage + `:memory:` default (→ persistence).
- **KEEP-SIBLING / do not touch:** Red (`exec_chain`/`lab`), `response_loop.py`,
  benign corpus semantics, `aggregate_opinions` internals, the doc spine.

## Data contracts (must hold)

The Episode is the sole Red→Bully contract; scenario dicts are the sole
Bully→Red contract. All persistent writes append-only + superseding, with
provenance and idempotent keys (`DATA_MODEL`). Technique IDs are coverage tags,
not join keys; `cell_key` = (technique × log-source × detection).

## Persistence requirements

SUB is durable (file-backed, not `:memory:`); ORG corpus is the hunt-memory
corpus (distinct from docs); the investigation store is pinned to a durable path;
nothing is deleted (supersede only); decay is ranking/weight, never removal.

## Configuration requirements

All tunables via `config/portal.yaml` (fleet/workspace-scoped) + `config/
security/` (component params): cousin-axis weights + band thresholds, mutation
budget, ORG recall depth + index policy, council roster/quorum/objection policy,
TGT weights, plateau floor/window, cost model, training cadence + acceptance
thresholds, `PROMOTE_POLICY=confirm`. **No hardcoded model names, ports, counts,
or paths** — discover at runtime and re-verify against `ollama show`/`git log`.

## Model / runtime / training dependencies

- Inference: Ollama sole chat backend (:11434); MLX embed (:8917) + rerank
  (:8925) for ORG only.
- Training tools **present** (`mlx-lm>=0.31`): `mlx_lm.lora`, `mlx_lm.fuse`.
- Redeploy **present**: `models.py import-gguf` → `ollama create`.
- Acceptance **present**: `candidate_eval` + `model-canary`.
- **The one new tool:** llama.cpp `convert_hf_to_gguf` + quantize (fused HF →
  GGUF). Confirm availability at build time; if absent, TRAIN is honest-BLOCKED.
- MITRE MCP for the ATT&CK lattice; Proxmox MCP for lab lifecycle.

## Resource constraints

Single M4 Pro Mac Mini, 64 GB unified memory; Ollama single-model ~15.5–20 GiB.
Bound council roster + serialize reviewer calls under a memory cap. Training runs
offline/off-hours, never concurrent with a live hunt (the `train` path checks for
an active engagement). Loop hard caps (50 iters / 7200 s / 200 actions) stand.

## Dependency graph (build prerequisites, not a schedule)

```
SUB (persistence) ─┬─> TGT ──> LOOP ──> BIN ──> HEART ──> SCORE ──> HND
ORG (hunt memory) ─┘           │           ▲
        │                      ├─> MUT ─> RED(untouched) ─> Episode ─> BR-COUSIN/BR-DRIFT
        └─> BR-COUSIN <────────┘                                   │
HARV ──> TRAIN(+GGUF tool) ──> ACCEPT ──> SERVE                    PLT <── cost ledger(SUB)
PLAY, ROSTER refine LOOP/HEART over time
```
SUB + ORG are prerequisites for everything (they carry the compounding state).
BR depends on ORG + Episode. BIN depends on lab (G1) + benign corpus (G2) + siem
(G3). HEART depends on the council + BIN. TRAIN depends on HARV + the GGUF tool +
acceptance. HND depends on HEART + siem + the growth-loop proof.

## Ordering constraints (hard)

1. Additive first (SUB persistence, ORG wrappers, BR engines) before any
   retirement.
2. No component with live callers is retired before its replacement consumes
   those callers.
3. The composite cousin metric must be proven (B1/CU1) before token-overlap-as-
   decision is retired.
4. Real BIN gates must be proven (B2/BI1) before findings can promote.
5. The objection gate must be proven beside the council (I3/B3) before
   `council_agreement` flattening is retired.
6. The full flywheel (TR1) must close on real data before TRAIN is claimed; if
   the GGUF tool is unavailable it is honest-BLOCKED and the other feeds proceed.
7. Every step ends with `validate_system.py` green (AW/BR/AZ/BL/BM/BN/BQ).

## Migration constraints

Red continuity is preserved throughout; the Episode bridge stays stable; the
bench path is repositioned, not deleted; doc spine sees new `security/core/*`
files at zero new-unit cost (BR); `P5-SEC-BENIGN-CORPUS-001` stays RESOLVED.

## Validation gates (must be green at every step)

AW (wiki facts current), BR (spine coverage ratchet), AZ (recall vs emergent
corpus), BL (council participation floor), BM (label-blind boundary), BN
(scoreboard semantics — ANOMALOUS not below CONFIRMED), BQ (benign alert-
fatigue). Plus the **[NEW CHECK]s** from `VALIDATION`: coverage-persistence,
recall-enforced, universal-index, cousin-metric, drift-cause, plateau, objection-
gate, and the compounding proofs (CP1–CP3) as behavioral checks.

## Operator-confirm points (PROMOTE_POLICY=confirm)

Finding promotion, detection deployment, trained-model serve, roster change,
playbook promotion, and any known-benign classification that suppresses future
hunting. No autonomous consequential promotion.

## Failure semantics (required behavior)

Honest-BLOCKED everywhere: no evidence → G0 fail; replay fails → G1
INDETERMINATE; quorum short → ESCALATE; unrebutted material objection → BLOCK;
corpus too small → documented non-build; GGUF tool absent → TRAIN halts, feeds
continue; lab/telemetry failure → INDETERMINATE (never PROVEN/DISMISS). Notify
carries a resume command. Never faked-green.

## Repo operability (must remain true)

Fresh clone builds and validates; all existing CLI subcommands keep working;
`validate_system.py` runs from repo root; no new top-level entrypoint (subcommands
only); CI parity (bench imports without PYTHONPATH) preserved.

## Definition of complete

`DESIGN` §complete-success-criteria (1–6) all demonstrated on real data;
`VALIDATION` B1–B6, CP1–CP3, TR1–TR3, E2E1–E2E2 pass or are honest-BLOCKED with a
recorded reason; all standing gates green; every promotion operator-confirmable;
Red untouched; six feeds demonstrably closing.

## Final proof (the one demonstration that settles it)

A second hunt, using state and (optionally) a model produced by a first hunt,
finds a NEW cousin the first hunt's tooling would have scored ≈0 — cheaper per
cousin than the first — and exits it as a family-generalizing, operator-confirmed
detection that fires on the attack, stays quiet on benign, and breaks nothing.
That single end-to-end demonstration proves discovery, adversarial verification,
compounding (technical + economic), and the exit simultaneously.

## What to re-verify at HEAD before building

- HEAD SHA + `git log --oneline -5`; diff the RBP surface vs. this design's
  reference (`ee9272ee`) — if any `portal/modules/security/**` or `router/*`
  `.py` changed, re-verify the affected `path::symbol` claims here.
- `ollama show` for any model the build assumes; `mlx-lm` version; llama.cpp
  convert availability.
- Fleet MCP ports + `config/portal.yaml` workspace/MCP counts (they drift).
- The seven validation checks named above still exist with the same letters
  (letters can be reassigned).
- The investigation store default path and `capability_graph` persistence status
  (the two things this design changes) are still as described.
