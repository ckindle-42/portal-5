# FINAL BUILD PROGRAM — Defensive Bully

**The complete build plan**, consumed by the later coding-agent planning/
implementation session. This is THE design — all parts in the initial build;
phases are implementation ordering only, never scope deferrals. The target is
the complete accepted system per `FINAL_DESIGN_DEFENSIVE_BULLY.md`.

Authority: `FINAL_DESIGN_` (what) → `FINAL_ARCHITECTURE_` / `FINAL_INTERFACES_`
/ `FINAL_DATA_MODEL_` (contracts) → `FINAL_MIGRATION_` (transition) →
`FINAL_VALIDATION_` (proof) → this file (sequence). Rationale:
`FINAL_DECISION_LEDGER_`; evidence: `FINAL_COMPARATIVE_REVIEW_`.

Grounding contract for the build session: re-verify HEAD and every cited
anchor (`git log --oneline -3` after a fresh clone); drift is a finding —
adjust the implementation, never the invariants, without operator review. The
working tree currently carries another agent's bench work — never touch it;
build tasks branch from the then-current HEAD.

---

## 1. Final target architecture

Sixteen components in four planes inside one new package
`portal/modules/security/core/bully/` (plus CLI + config + one spine surface
entry), per FINAL_DESIGN §6:

- **Knowledge plane:** SUB (SQLite WAL authority, outbox, decision log,
  leases) · ORG (LanceDB `hunt_memory` projection on :8917/:8925 infra,
  recall receipts, decision impacts).
- **Brain:** LOOP (hunt orchestrator + investigation arm) · BR-COUSIN
  (two-axis grading) · BR-DRIFT (baseline drift + cause attribution) · MUT
  (typed mutation plans) · TGT (eligibility + posterior ROI) · PLT
  (statistical plateau) · SCORE (catch/trust/discovery axes).
- **Promotion plane:** BIN (G-1→G0→G1a→G1b→G2→HEART→G3→G5 state machine) ·
  HEART (falsification council, durable objections, veto, waiver) · HND
  (family-generalizing exit with real proof legs).
- **Flywheel:** HARV (leakage-safe role-tagged corpus) · PLAY (learned
  playbook lifecycle) · TRAIN (LoRA flywheel with frozen five-arm acceptance)
  · ROSTER (eligibility/reliability governance).

Red is directed via compiled MutationPlans and never modified; the Episode is
the sole Red→bully contract; the bench harness is repositioned as the
model-acceptance gate; production serving stays Ollama.

## 2. Existing assets to leave alone

- `exec_chain.py`, `lab.py`, attack image, sandbox :8914 / proxmox :8927
  MCPs (Red execution — directed, never edited).
- `episode.py` (truth plane), `siem/*` telemetry plane, `capture_store`.
- `multichain.py` (verified escalate-by-default, `consolidate:110-218`).
- `council_agreement.py` (legacy bench lane; HEART does not route through it).
- `response_loop.py` (KEEP-SIBLING: response IR + reverse-gen + intake).
- `loop.py`/`loop_cli.py` (red-side engagement runner), `playbooks.py` +
  `playbooks/security/*.yaml` (static red-side playbooks).
- `field_journal.py` (legacy; read-only PLAY/HARV source).
- `portal/platform/agent/*` (evaluated, rejected as LOOP's base; untouched).
- `portal/platform/inference/router/council.py` (mechanics reused; zero
  edits — `aggregate_opinions` untouched).
- `rag_mcp` :8921 / `memory_mcp` :8920 (independent services; shared infra,
  never tables).
- Wiki spine (`portal_wiki/`), `drift_gate.py`/`drift_cli.py` modules
  (machinery seeded; modules untouched), Open WebUI.
- `investigation/` files (patterns extracted; files untouched).

## 3. Existing assets to reuse (as-is)

- `blue.py::collect_and_ship_scenario_telemetry:1710-1912` (telemetry plane).
- `siem/spl_backend.py::query_episode:161-205` (label-blind episode
  haystack).
- `blue.py::_cite_or_drop:831` / `_discriminator_contradicts:915` (grounding
  gates).
- `blue.py::_build_evasion_feedback:2185` / `_run_evasion_purple:2217` (MUT
  directive channel).
- `capture_recipes.py` + `scripts/security_capture_recipes.py` (G1b engine;
  HND regression format).
- `siem/blue_triage.py` (G3 measurement lane).
- `benign_corpus_bench.py` + `_VERDICT_GROUNDING_POLICY`
  (`blue_orchestrate.py:91-103`) (G2 instruments).
- `siem/spl_detections.{py,yaml}` (discriminator_tokens, sibling_ids,
  spl_variants — vetoes/explanation/HND source).
- `emergent_gaps.py` (MUT off-script supply).
- `recall_attribution.py` (HARV eval-side labeler only; BM boundary).
- `notify_scoreboard.py` semantics (SCORE catch/trust base).
- `cli/models.py::cmd_models_import_gguf:218-259` (TRAIN redeploy leg).
- `candidate_eval.py`, `intake.py` (TPS floor), `drift_cli.py` model-canary,
  PENDING_MODEL_VERDICTS flow (TRAIN acceptance legs).
- `portal/platform/inference/notifications` dispatcher (queue/BLOCKED/plateau
  notifications).
- `portal/platform/wiki/provenance_ledger.py::append_entry:66` (promotion
  audit).
- `perception.py` (LAB_CIDR guard).
- MITRE MCP :8929 / detections MCP :8932 (read-only).
- embed :8917 (CPU sentence-transformers — batch) / rerank :8925 (MLX Qwen3 —
  presentation only).
- `mlx-lm>=0.31` (`pyproject.toml:78`): `mlx_lm.lora` + `mlx_lm.fuse` ship
  with the environment — verified.

## 4. Existing assets to retrofit

- `blue_orchestrate.py` section machinery (`run_tool_model:496`,
  `run_reasoning_model:662`, `run_expert_model:1098`, `run_mentor_model:1263`,
  `_run_three_section:1970`, `capture_expert_handoff:1779`) → LOOP's
  investigation arm via `bully/investigation.py` (live-Episode adapter).
- `unknown_defense.py` → grading vocabulary + feature-overlap explanation
  layer into `bully/cousin_engine.py`; U1 lexical scorer kept as the
  documented baseline + dual-run comparator.
- `capability_graph.py` → SUB-backed loader (readout over persisted cells);
  classifiers (`classify_gap:76-123`) unchanged.
- `drift_gate.py` machinery → `bully/drift_engine.py` statistics pattern
  (module untouched).
- `investigation/` EvidenceRecord schema + CaseNotebook SQLite/supersede
  pattern + seven-kinds doctrine → SUB/ORG memory rules.
- `growth_loop.py` → shapes (DraftDetection/ProofResult,
  `validate_spl_syntax:145-173`, queue shape) into `bully/promotion.py` /
  `bully/handoff.py`; legs made real in HND.
- `playbooks.py` container/validation pattern → `bully/playbooks.py`.

## 5. Existing assets to extract

- `response_loop.py::RESPONSE_PRIMITIVES` (:53-63) + technique map (:81-104)
  → HND IR implications (by import; the module stays).
- `growth_loop.py::validate_spl_syntax` + draft/proof shapes → BIN/HND.
- `evidence.py::EvidenceRecord` schema + `case_notebook.py` supersede idiom →
  SUB store patterns.
- `field_journal` reusable-patterns content → PLAY/HARV input (read-only).

## 6. Existing assets to replace

- The **production grading role** of `unknown_defense.compute_similarity`
  (token containment vs wiki text) → the two-axis cousin engine.
- The **vote-flattening council decision** in the bully's path → HEART's
  objection gate (new code; the platform primitive and the legacy adapter are
  untouched).
- The **placeholder-true proof legs** of `growth_loop.prove_draft` (:209,215,
  221) → real G1a/G1b finding reproduction + real HND detection-proof legs.
- **Cold-rebuild coverage** (`capability_graph` per invocation) → SUB-
  persisted cells with an on-demand readout.
- **Prose-only PROMOTE_POLICY** → machine-enforced `promote_policy: confirm`
  + queue actor checks + separate authenticated operator commands.

## 7. Existing assets to retire

| Asset | When | Replacement proven by |
|---|---|---|
| `growth_loop.py` | after HND live | BIN/HND gate + proof-leg tests; tests ported |
| `continuous_eval.py` | after SCORE/PLT live | readout tests |
| `unknown_defense.py` U1 production-grading role | after BR-COUSIN dual-run adjudicated | calibration + comparison evidence |
| blue/blue_orchestrate **driver role** (as hunting brain) | after LOOP parity | hunt-loop integration + bench parity |
| `capability_graph` cold-rebuild behavior | after SUB persistence authoritative | coverage-persistence check |
| `agentic_blue_eval.Episode` name collision | at LOOP landing | comment/doc reconciliation (no behavior change) |

Every retirement: callers migrated, tests ported, checks green, replacement
live and exercised (bridge rule); honest-BLOCKED where a path has no
replacement yet.

## 8. New components

All inside `portal/modules/security/core/bully/` (module list per
FINAL_ARCHITECTURE §1): contracts, config, store, events, outbox, evidence,
organ, signatures, cousin_engine, drift_engine, orchestrator, investigation,
mutation, promotion, adversary, roster, targeting, plateau, costing,
scoreboard, handoff, harvest, playbooks, training, soc, notify,
observability, migrations/. Plus: `commands/hunt_modes.py` + `hunt`
subcommand registration; `config/security/hunt.yaml` +
`config/security/heart.yaml`; one spine surface entry
(`unit-surface-sec-bully`); the cousin-judgment eval set (fixtures first, SUB
history later); the G3 queue-load corpus wrapper (`bully/soc.py`);
`scripts/defensive_bully_train.py` thin host-native entry point.

## 9. Full dependency graph

```text
contracts + config schema
   └─> store/migrations/events/outbox + evidence manifests
        ├─> organ (projection/recall/impact)            [needs embed/rerank]
        ├─> Episode adapter + shadow ingestion          [needs existing purple]
        ├─> signatures → cousin_engine                  [needs organ + spl_detections]
        ├─> drift_engine                                [needs store baselines]
        ├─> costing → targeting → plateau               [needs store + organ]
        ├─> mutation (validator/compiler)               [needs contracts + perception]
        └─> orchestrator (LOOP)                         [needs all above +
             investigation arm (blue_orchestrate runners)]
              └─> promotion (BIN)                       [needs captures, recipes,
                   │                                       benign corpus, verdict policy]
                   ├─> adversary (HEART)                [needs platform council + roster config]
                   ├─> soc (G3)                         [needs blue_triage lane + queue corpus]
                   └─> handoff (HND)                    [needs BIN+HEART live]
        ├─> harvest (HARV)                              [needs store + HEART + cousin records]
        ├─> playbooks (PLAY)                            [needs LOOP trajectories]
        ├─> training (TRAIN)                            [needs HARV + toolchain + bench]
        └─> roster (ROSTER)                             [needs store + HEART records]
scoreboard (SCORE) reads store; notify/observability cross-cut.
```

## 10. Full implementation sequence

Phase skeleton (ordering only — all scope is in the build):

**P1 — spine (brain substrate).** contracts/config → store + migrations +
events + outbox → evidence manifests → Episode adapter + shadow ingestion
(flagged) → organ + recall receipts → signatures → cousin_engine →
investigation adapter → orchestrator (LOOP) with budgets/admission control.
**Hard gate: nothing lands before LOOP runs a full iteration end-to-end
(synthetic lab) with recall/index enforcement proven.**

**P2 — bin & heart.** promotion machine (G-1→G0→G1a→G1b→G2) → adversary
(HEART objection lifecycle) → soc (G3 lane + queue-load corpus) → promotion
queue + machine-enforced confirm.

**P3 — red as means & second cousin surface.** mutation (typed plans,
validation, compilation, budgets, operator class approval) → drift_engine
(baselines + attribution order + resets).

**P4 — discovery, selection, stopping.** scoreboard (three axes) → costing +
pricing profile → targeting (eligibility + posteriors) → plateau
(statistical rule + resets).

**P5 — the exit.** handoff (11-part package + real proof legs + proposal
lifecycle + regression recipes).

**P6 — the flywheel.** harvest (quarantine, leakage, splits, frozen test) →
playbooks (lifecycle + canary + auto-revert) → training (toolchain install +
verification, train/fuse/convert/create, frozen five-arm acceptance, canary +
atomic alias) → roster (eligibility/reliability).

**P7 — cutovers + final proof.** per-component cutovers per the migration
gates; retirements per §7 conditions; final end-to-end recorded hunt series
(VALIDATION §15).

### Phase dependency rules

- P1 is the hard gate: cousin_engine needs organ; LOOP needs store+organ+
  cousin_engine+mutation validation.
- P2 ordering: gates before HEART before G3 lane wiring; suspect-default is
  inherent to the state machine from the first commit.
- P3: mutation needs cousin_engine (grading targets); drift needs store +
  LOOP.
- P4: scoreboard needs cousin records; targeting needs store+costing;
  plateau needs targeting+costing.
- P5: handoff needs BIN+HEART live.
- P6: harvest needs store+HEART+cousin records; playbooks need LOOP;
  training needs harvest+toolchain+bench; roster needs store+HEART.
- P7: any cutover needs its replacement's validation green + operator
  approval + rollback drill.

## 11. Migration sequence

Per `FINAL_MIGRATION_DEFENSIVE_BULLY.md`: M0 foundation → M1 shadow ingestion
→ M2 organ/outbox shadow → M3 dual-run classification → M4 mutation +
orchestration → M5 promotion/SOC/council → M6 six-feed shadow → authoritative
cutovers → M7 HND/PLAY lifecycles → M8 HARV/TRAIN → M9 component cutovers +
retirements → M10 final proof. Feature flags `off|shadow|authoritative` at
every stage; dual-run disagreements persisted and adjudicated; the repo stays
operational with all gates green at every commit.

## 12. Data-store creation/migration order

1. `PORTAL5_HUNT_DIR` convention + `hunt doctor` integrity command.
2. SQL migrations (ordered package resources): schema_migrations → hunts/
   iterations → decision_events (hash chain) → evidence manifests/items →
   signatures/assessments → candidates/gate_results → council
   packets/opinions/objections/rebuttals → known_state → baselines/drift →
   outbox → recall_receipts/decision_impacts → cost_ledger → plateaus →
   promotion_queue → playbooks → training_examples/dataset_versions/
   trained_models → roster_records → soc_deliveries → detection_proposals →
   validation_results. Constraints per DATA_MODEL §4.8 (synthetic-never-G0,
   PROMOTED-requires-gates, KNOWN_COVERED-requires-deploy+replay, one active
   lease/playbook/alias, outbox source-hash equality, closed enums, no
   cascade delete).
3. LanceDB `hunt_memory` projection schema + projection versioning +
   rebuild-by-replay command.
4. Corpus/playbooks/artifacts directories under the hunt dir.
5. Backfill (idempotent, trust-conservative) only after M1–M3 shadow evidence.

## 13. Interface implementation order

I-3 (hunt command/orchestrator shell) → I-5 (SUB) → I-4 (ORG) → I-2 (Episode
adapter) → I-6 (cousin engine) → I-9 (drift) → I-1 (mutation) → I-7 (BIN +
G3 I-7a) → I-8 (HEART) → I-10/I-11/I-12/I-13 (score/target/plateau/cost) →
I-14 (HND) → I-15 (HARV) → I-16 (PLAY) → I-17/I-18 (TRAIN + acceptance) →
I-19 (ROSTER) → I-20 (budget guard) → I-21 (notifications) → I-22 (shadow/
dual-run) — noting I-22's shadow interfaces ride *alongside* each component
from its first landing (flags are not a phase, they are per-component).

## 14. Integration points

Per FINAL_ARCHITECTURE §3. Load-bearing: Red scenario machinery
(`exec_chain.py::_prepare_scenario:3071`); Episode (`episode.py:45-74,146-
183`); `spl_backend.query_episode:161-205`; telemetry ship
(`blue.py:1710-1912`); grounding gates (`blue.py:831,915`);
blue_orchestrate runners; platform council (`council.py:147-187,190-237`);
capture_store/capture_recipes; blue_triage lane; benign corpus; verdict
policy; spl_detections library; drift_gate statistics; emergent_gaps;
evasion-feedback channel; response_loop primitives; recall_attribution (eval
side); notify_scoreboard semantics; capability_graph classifiers;
models.py import-gguf; candidate_eval/intake/model-canary/PENDING_VERDICTS;
notifications dispatcher; provenance ledger; perception guard; MITRE/detections
MCPs; embed/rerank services.

## 15. Validation gates

Per `FINAL_VALIDATION_DEFENSIVE_BULLY.md`; each phase closes with its mapped
claims:

- P1 exit: C1–C4, I1–I3 + first graded live cousin (synthetic lab).
- P2 exit: C7, C8 + full gate pipeline + council block/pass demonstrated.
- P3 exit: C6, C9, M1–M2.
- P4 exit: C10, R1–R2.
- P5 exit: D1.
- P6 exit: C11, F1–F2 (shadow), L1.
- P7 exit: B1–B3, A1–A3, H1–H2, T1–T2, L2–L3, P1, all regression checks,
  and the final E2E recorded hunt series (VALIDATION §15).
- Standing floor at every commit: `pytest tests/unit -q`, ruff lint+format;
  per phase `bash scripts/ci_local.sh`; pre-push validation suite green;
  BQ/AZ/BM/BL/BN/BR/AW/BS held.

## 16. Operator-confirmation points

Machine-enforced (`promote_policy: confirm` + queue actor checks), each a
separate authenticated command: hunt authorization; scope/mutation-class
widening; resume after safety block; material-objection waiver; finding
promotion; detection-proposal acceptance/deployment ownership; playbook
activation/override; dataset release; model canary/promotion/rollback
override; roster activation; threshold-policy weakening; plateau override.
Also operator-only: hunt start/stop, budget/threshold config, external-intel
ingestion, dataset builds, train runs. One approval never implies another.

## 17. Failure/blocking behavior

Per FINAL_DESIGN §30: honest-BLOCKED on infra failure; INDETERMINATE never
scored as miss/pass; sub-floor council → operator escalation; gate failure →
terminal outcome with rationale; gate-infrastructure failure → retryable
BLOCKED; unindexed required emission → failed iteration; no recall receipt →
no targeting; below-floor corpus → documented non-build; GGUF-convert missing
→ TRAIN blocked, other feeds continue; degraded organ → blocked grading,
never silent lexical fallback; crash → lease expiry + idempotent resume;
training failure → active alias unchanged; cancellation preserves evidence.

## 18. Repository-operability requirements

- `./launch.sh up` unaffected; no new services; no new ports; no new Docker
  images.
- `pytest tests/unit -q`, `ruff check .`, `ruff format --check .` green per
  commit; `bash scripts/ci_local.sh` green per phase; pre-push validation
  suite green.
- No `.env` changes required for the core build beyond documenting
  `PORTAL5_HUNT_DIR` (defaulted; add to `.env.example` as an optional
  override). Live hunts use existing env (SANDBOX_LAB_EXEC, LAB_SPLUNK_*, …).
- One new spine surface entry for the bully package; ≤1 authored design unit
  per phase; two-commit re-pin sequence when BS requires.
- `git checkout -- portal/modules/security/core/field_journal/_index.json`
  discipline after module-tree test runs (existing rule).
- Public import/startup never requires training extras; feature flags default
  off.
- Never touch the other agent's in-flight worktree files; branch from the
  build session's own HEAD.

## 19. Model/toolchain requirements

- Runtime: existing fleet only (Ollama + :8917/:8925). Model references are
  role aliases resolved via the backends registry; never hardcoded.
- TRAIN phase owns: verification that `mlx_lm.lora`/`mlx_lm.fuse` work on the
  host (present via `mlx-lm>=0.31`), and installation + verification of
  llama.cpp GGUF convert/quantize (host-native, Apple Silicon). No
  `torch`/`transformers` in `portal/platform/inference/` (Rule 8); training
  deps are host tooling, isolated from runtime imports, with a verification
  command.
- Base model selection is a config alias with capability requirements —
  rebenchmarked at the build HEAD (fleet churn is continuous; the other
  agent's bench work is actively changing the catalog).

## 20. Training requirements

Per FINAL_DESIGN §24 and VALIDATION §11: role-tagged corpus (four roles;
adversarial + distance pairs; negatives first-class); quarantine → checks →
operator dataset release; immutable dataset versions with family/campaign/
time splits and the test set frozen pre-harvest; exclusive resource lock +
preflight; never concurrent with a live hunt or bench run; 9B-class ceiling
unless capacity is reverified; frozen five-arm acceptance (+5 macro-F1,
95% CI > 0 over base+retrieval+playbook; ≤2pt regressions; 30% replay mix);
intake floors; candidate delta; model-canary; operator confirm via
PENDING_MODEL_VERDICTS; role-alias canary; atomic promotion; rollback =
alias re-point; a no-gain result is a documented non-serve.

## 21. Resource considerations

Per FINAL_DESIGN §34: 64GB single host; council seats serialize under memory
pressure; batched CPU embedding; lab-action budgets; admission control
against bench-supervisor/engagement co-tenancy; training off-hours under an
exclusive lock; projection rebuild rate-limited; hunt iteration cost ≈ one
red chain + one investigation arm + one council review, bounded by hunt
budgets and backend memory budgets.

## 22. Final integrated proof

The recorded hunt series of VALIDATION §15 with cited artifacts, plus: the
six-feed compounding series report (recall receipts + decision impacts +
waste-rate + cost-per-promoted-cousin trend), the frozen five-arm acceptance
report, the operator decision-log excerpts, the rollback drill evidence, and
the green validation-suite output at the final HEAD.

## 23. Definition of complete

All sixteen components built, integrated, and validated per §15; the six
feeds demonstrably change later hunts with recorded decision impacts; the
flywheel has run at least once through operator-confirmed serve (or a
documented, evidence-backed non-serve); every retirement in §7 is either
complete or explicitly retained with replacement-live evidence; all success
criteria in FINAL_DESIGN §38 hold; the final end-to-end proof (VALIDATION
§15) is recorded with artifacts; and the repository is green at the final
HEAD. A prototype, a disconnected library, a mock-only path, a
symbol-presence test, or a deferred training/feed/promotion component is not
complete.

---

## Status checklist (for the build session to fill)

Phase 1 — spine
- [ ] contracts + config schema + hunt.yaml/heart.yaml + spine surface entry
- [ ] store + migrations + events (hash-chained) + outbox
- [ ] evidence manifests + Episode adapter + shadow ingestion (flagged)
- [ ] organ (projection, recall receipts, decision impacts)
- [ ] signatures + cousin engine (two-axis, vetoes, explanation)
- [ ] investigation adapter (live-Episode) + orchestrator (budgets,
      admission, checkpoint/resume, notify)
Phase 2 — bin & heart
- [ ] promotion machine (G-1→G0→G1a→G1b→G2)
- [ ] HEART (objection lifecycle, veto, waiver)
- [ ] G3 SOC lane (blue_triage + queue-load corpus)
- [ ] promotion queue + machine-enforced confirm
Phase 3 — red as means & second cousin surface
- [ ] mutation director (typed plans, validation, budgets, class approval)
- [ ] drift engine (baselines, attribution order, resets)
Phase 4 — discovery, selection, stopping
- [ ] scoreboard (catch/trust/discovery axes)
- [ ] costing + pricing profile
- [ ] targeting (eligibility + posteriors + decision records)
- [ ] plateau (statistical rule + resets)
Phase 5 — exit
- [ ] handoff (package + real proof legs + proposal lifecycle + recipes)
Phase 6 — flywheel
- [ ] harvest (quarantine/leakage/splits/frozen test)
- [ ] playbooks (lifecycle + canary + auto-revert)
- [ ] training (toolchain, five-arm gate, canary, atomic alias)
- [ ] roster (eligibility/reliability)
Phase 7 — cutovers + final proof
- [ ] per-component cutovers + retirements per migration gates
- [ ] final recorded hunt series (VALIDATION §15)

## Beyond the initial build (natural extensions, not deferred scope)

- Persistent hunt daemon (the loop is built to allow it; admission control
  already exists).
- Auto-promotion of cousin-specialist models once the train→serve loop has a
  track record (a tighter-than-confirm gate — requires operator policy
  change).
- External cadence — ATT&CK/KEV/SigmaHQ into ORG so new public techniques
  auto-become cousins-to-chase (`response_loop` intake is the seed).
- Cousin-of-cousin recursion when plateaus show first-order neighborhoods
  exhausting.
- Read-only hunt-status MCP surface (Rule 3 preserved).
- Model-catalog spine re-pin remediation (separate, smaller task).
