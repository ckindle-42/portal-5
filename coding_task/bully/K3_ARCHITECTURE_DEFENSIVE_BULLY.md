# ARCHITECTURE — Defensive Bully (implementation level)

The where and how: module boundaries, call paths, state/service/model
boundaries, and flows. Normative companion to `DESIGN_DEFENSIVE_BULLY_FINAL.md`.
Citations to existing code are HEAD `47d3e884`; the implementing agent
re-verifies them at its own HEAD (grounding contract).

---

## 1. Component map and expected locations

All new modules live in `portal/modules/security/core/` (covered by the
`unit-surface-sec-core` spine glob — zero new spine units) except where noted.

| Component | Module (new unless noted) | Reused/extracted from |
|---|---|---|
| SUB | `hunt_state.py` | schema pattern: `investigation/case_notebook.py`; record schema: `investigation/evidence.py` |
| ORG | `hunt_organ.py` | infra: LanceDB + `scripts/embedding-server.py` (:8917) + `reranker_mcp.py` (:8925); fallback patterns from `portal/modules/research/tools/rag_mcp.py` |
| LOOP | `hunt_loop.py` | investigation arm: section runners extracted from `blue_orchestrate.py`; loop discipline mirrored from `loop.py` hard caps |
| BR-COUSIN | `cousin_engine.py` | grading vocabulary + explanation layer from `unknown_defense.py`; discriminators from `siem/spl_detections.py` |
| BR-DRIFT | `drift_engine.py` | rolling-window machinery pattern from `drift_gate.py` |
| BIN | `alert_bin.py` | draft shapes from `growth_loop.py` (DraftDetection/ProofResult/surface_for_confirm); benign corpus: `benign_corpus_bench.py`; triage lane: `siem/blue_triage.py`; replay: `siem/capture_store.py`, `capture_recipes.py` |
| HEART | `heart_council.py` | mechanics: `portal/platform/inference/router/council.py` (isolation, parsing, participation) |
| MUT | `mutation_director.py` | `emergent_gaps.py`; `blue.py::_build_evasion_feedback`; `exec_sequences.json` fallback_techniques; `spl_detections.yaml` sibling_ids |
| SCORE | `hunt_scoreboard.py` | `notify_scoreboard.py` semantics (NOTIFY_VERDICTS, trust ranks, benign typing) |
| TGT | `target_selector.py` | reads SUB/ORG only |
| PLT | `plateau.py` | reads SUB only |
| HND | `handoff.py` | `response_loop.py::RESPONSE_PRIMITIVES` + technique map; `spl_detections.yaml` structure; recipe writer per `capture_recipes.py` |
| HARV | `harvest.py` | `recall_attribution.py` (eval-side labels); corpus lanes per `config/security_corpus.yaml` |
| PLAY | `playbook_memory.py` | container/validation pattern from `playbooks.py`; sources: field_journal reusable patterns, hunt trajectories |
| TRAIN | `train_flywheel.py` | redeploy: `portal/platform/inference/cli/models.py::cmd_models_import_gguf`; acceptance: `candidate_eval.py`, `intake.py`, PENDING_MODEL_VERDICTS flow |
| ROSTER | `roster.py` | roster config in `config/security/heart.yaml`; decision events from SUB |
| CLI | `commands/hunt_modes.py` + registration in `cli.py`/`__main__.py` | command-extraction pattern from `commands/blue_modes.py` |
| Config | `config/security/hunt.yaml`, `config/security/heart.yaml` | config-JSON convention from `3d2aca98`/`65958b7f` |

**Not created:** new MCP servers, new Docker services, new OWUI functions, new
vector stores, new pipeline routes.

## 2. Module/service boundaries

```text
portal/modules/security/core/            (in-process Python; the bully brain)
  ├── hunt_loop.py        orchestrates; the ONLY driver of the iteration
  ├── hunt_state.py       SUB — sole owner of hunt_state.db (no raw SQL elsewhere)
  ├── hunt_organ.py       ORG — sole owner of the hunt_memory LanceDB table
  ├── cousin_engine.py    BR-COUSIN — pure grading + explanation (no I/O except ORG reads)
  ├── drift_engine.py     BR-DRIFT — baselines read/write via SUB
  ├── mutation_director.py MUT — emits MutationSpec + scenario overlay; never touches lab.py
  ├── alert_bin.py        BIN — gate pipeline + suspect state machine
  ├── heart_council.py    HEART — falsification seats + objection gate
  ├── target_selector.py  TGT — pure ranking over SUB/ORG reads
  ├── plateau.py          PLT — pure stopping analysis over SUB reads
  ├── hunt_scoreboard.py  SCORE — pure scoring/reporting
  ├── handoff.py          HND — package generation + operator queue entry
  ├── harvest.py          HARV — corpus append (JSONL) + manifests
  ├── playbook_memory.py  PLAY — learned shapes (SUB records)
  ├── train_flywheel.py   TRAIN — orchestration of train/fuse/convert/create/bench
  └── roster.py           ROSTER — weight computation (SUB reads/writes)
```

Boundary rules:
- Only `hunt_loop.py` sequences an iteration. Other modules never call Red,
  Splunk, or models except through their documented interfaces (INTERFACES doc).
- Only `hunt_state.py` and `hunt_organ.py` perform persistence I/O (plus
  `harvest.py` for the corpus JSONL under the hunt dir).
- `cousin_engine.py`, `target_selector.py`, `plateau.py`, `hunt_scoreboard.py`,
  `roster.py` are pure compute over injected data/read interfaces — unit-testable
  with `tmp_path`, no network (Testing Rules).
- Model calls happen only inside: the investigation arm (section runners),
  HEART seats/rebuttals, HND prose drafting, and PLAY drafting — always through
  the pipeline/Ollama call helpers already used by `blue_orchestrate.py`
  (`agentic_blue_eval._call_model` pattern) with model ids resolved from config
  via the backends registry. **No model name is hardcoded** (Rule: config-driven).

## 3. Call-path expectations

### 3.1 Hunt iteration (primary path)

```text
cli.py  "hunt run --neighborhood auto --budget default"
  └─ commands/hunt_modes.py::run_hunt
       └─ hunt_loop.py::run_hunt(config)                      [loads SUB via hunt_state]
            ├─ hunt_state.load_context()                      cells/known-state/plateau/cost
            ├─ hunt_organ.recall(context, k)  ← MANDATORY     prior cousins/kills/defenses
            ├─ target_selector.rank(cells, known_state, ledger, recall) → target cell
            ├─ mutation_director.plan(known, budget) → MutationSpec
            │     └─ scenario overlay → exec_chain._prepare_scenario-equivalent
            │        (REUSES existing substitution; NO exec_chain edits)
            ├─ exec_chain._run_chain_test(model, cfg, lab_exec=True)   [UNCHANGED CODE]
            ├─ blue.collect_and_ship_scenario_telemetry(...)           [UNCHANGED CODE]
            ├─ episode.Episode + save_evidence                         [UNCHANGED CODE]
            ├─ investigation arm: blue_orchestrate section runners     [EXTRACTED]
            │     over siem/spl_backend.query_episode(episode_id)      [UNCHANGED]
            ├─ cousin_engine.grade(record, organ.knn(...)) → grade+decomposition
            ├─ drift_engine.update_baselines(episode, detections) → drift flags
            ├─ alert_bin.process(candidate)  → G0→G1a→G1b→G2→HEART→G3→PENDING
            │     ├─ G1a: capture_store replay + spl execution
            │     ├─ G1b: capture_recipes re-run OR directed red re-run (via MUT)
            │     ├─ G2: benign_corpus_bench discriminators + verdict contract
            │     ├─ heart_council.review(candidate)  → objection gate
            │     └─ G3: ship notable (hec_ship) → blue_triage lane → SLA check
            ├─ hunt_state.record_* (decision events, cousin, known-state, cost)
            ├─ hunt_organ.index(emissions...)  ← UNIVERSAL
            ├─ harvest.append_pairs(hunt_record)
            ├─ hunt_scoreboard.update(...)
            └─ plateau.evaluate(neighborhood) → continue | rotate | stop
```

### 3.2 Promotion + handoff path

```text
operator: portal security hunt queue --confirm <candidate_id>
  └─ alert_bin.promote(candidate_id, operator_note)
       ├─ handoff.build_package(candidate) → {spl_generalized, sigma,
       │    telemetry_requirements, attack_delta, evidence_pack, recipe,
       │    fp_analysis, limitations, ir_implications, coverage_delta}
       ├─ recipe → capture_recipes registration (code change, validated)
       ├─ detection change → spl_detections.yaml edit (operator commit;
       │    validation BQ/AZ must pass pre-push)
       ├─ provenance_ledger.append_entry(...)            [EXISTING surface]
       └─ hunt_state: cell → COVERED; supersede cousin record
```

### 3.3 Training path

```text
operator: portal security hunt train --role cousin-smeller
  └─ train_flywheel.run(role)
       ├─ harvest.build_dataset(role) → versioned JSONL + manifest + splits
       ├─ size gate → honest non-build if below floor
       ├─ mlx_lm LoRA train (host-native subprocess; toolchain installed
       │    by the TRAIN phase) → fuse → GGUF convert (llama.cpp)
       ├─ models import-gguf equivalent → ollama create <base>-cousin<dv>
       ├─ bench gate: intake floors (TPS/tool-reliability) + candidate delta
       │    vs incumbent + cousin-judgment bench + no general regression
       ├─ comparison arms: base / +retrieval / +playbook / +both / trained
       └─ PASS → PENDING_MODEL_VERDICTS entry → operator confirm → config
            points the role at the specialist (sync-config; no code change)
```

## 4. State boundaries

```text
OUTSIDE REPO (PORTAL5_HUNT_DIR, default /Volumes/data01/portal5_hunt/):
  hunt_state.db        SUB (SQLite WAL) — all durable hunt state
  corpus/<role>/<dv>.jsonl + manifest.json   HARV datasets
  playbooks/           PLAY learned records (also mirrored into SUB)

EXISTING, UNCHANGED ROLE:
  results/…                      bench artifacts (read-only inputs to SUB seeds)
  results/captures/              replay source for G1a/G1b
  portal_wiki/canonical/         design facts ONLY (never runtime hunt state)
  LanceDB rag/ + memory tables   untouched; ORG owns ONLY hunt_memory table

IN-GIT (unchanged behavior): field_journal/ (legacy writes continue; PLAY/HARV
  read it as a source; it is not the bully's store)
```

## 5. Service boundaries

| Service | Relationship |
|---|---|
| Ollama :11434 | fleet inference; trained GGUFs land here via `ollama create` |
| Pipeline :9099 | model calls for investigation/council/drafting use the existing call helpers (pipeline default, direct-Ollama fallback per existing `_call_model` semantics) |
| Embedding :8917 | ORG embeds (batched; CPU service — respect batch sizes) |
| Reranker :8925 | ORG recall presentation rerank only; raw cosine distance is the cousin metric |
| Splunk (lab) | telemetry in (HEC ship) + out (query_episode, notable poll by triage) — existing modules only |
| Sandbox MCP :8914 / Proxmox MCP :8927 | Red execution + VM lifecycle — UNCHANGED, driven only by existing Red code |
| rag_mcp :8921 / memory :8920 / wiki :8931 | untouched; the organ is not exposed as an MCP tool in this build |
| detections :8932 / mitre :8929 | read-only use for SPL library + ATT&CK structure where useful (cousin explanation, HND) |

## 6. Model boundaries

- Roles: retriever / hunter / expert (investigation arm), falsifier seats
  (HEART), rebuttal seat, drafting (HND/PLAY), trained specialists
  (cousin-smeller, disprover). All model ids resolve from
  `config/security/hunt.yaml` + `heart.yaml` through the backends registry —
  same resolution path as `blueteam-council` today.
- Defaults at design time (operator-editable): reuse the verified bench roster
  families (granite4.1 tool/reasoning, mistral-small3.2, qwen3.6,
  Foundation-Sec expert) — one seat per family in HEART.
- Label-blind: no production prompt receives ground truth; corpus answer keys
  stay scorer-only (`config/security_corpus.yaml` contract preserved).

## 7. MCP boundaries

Rule 3 respected: MCP servers stay independent; no MCP imports security-core
modules and vice versa. The bully's new capabilities are **not** MCP tools in
this build — the operator surface is the CLI (`portal security hunt …`) and
the promotion queue. (A future MCP exposure of read-only hunt status is a
natural extension, not this build.)

## 8. Red/B/P boundary

- Red side (`exec_chain`, `lab.py`, `capture_recipes`, attack image): consumed
  via its existing direction surface (scenario dicts, red_prompt templating,
  evasion context, fallback techniques). Zero edits. MUT emits data (overlay),
  never code changes to Red.
- B/P side: the bench driver shells retire per MIGRATION; the extracted
  section machinery is imported by `hunt_loop.py`; `episode.py`,
  `spl_backend.query_episode`, telemetry shipping, grounding gates are used
  unchanged.
- Contract: the Episode (reason codes + evidence refs) is the sole Red→bully
  interface; the MutationSpec overlay is the sole bully→Red interface.

## 9. Inference interactions

- Investigation arm: multi-round tool-loop over `query_episode` with the
  existing `_cite_or_drop` grounding; budgets per role (existing BH/BK
  semantics); stall caps unchanged.
- HEART: isolated single calls per seat (platform council pattern), one
  rebuttal round when objections are material.
- Drafting: single-shot with schema validation; failures fall back to
  deterministic templates (no fabricated prose).
- All model calls honor per-turn timeouts and the pipeline slot discipline;
  council seats may be serialized when backend memory requires (documented in
  hunt config).

## 10. Embedding/reranking interactions

- ORG upsert: canonical record text → batched :8917 embeddings → LanceDB add.
- ORG recall: query embedding → LanceDB vector search (k×5 candidates) →
  cosine distances retained for grading; optional :8925 rerank for
  presentation ordering only.
- Failure: embed service down → iteration honest-BLOCKED (no silent lexical
  grading); reranker down → presentation degrades, grading unaffected
  (distance never comes from the reranker).

## 11. Knowledge flow

```text
emissions (candidates, verdicts, kills, defenses, benigns, plateaus,
           playbook deltas, detection changes)
   → ORG.upsert (provenance-classed, embedded, metadata-rich)
   → SUB.records (structured truth + decision events)
   → recall at next hunt (LOOP-enforced) + TGT penalties + BR-COUSIN priors
   → changed target selection / grading / stopping  (the compounding proof)
```

## 12. Training flow

§3.3 above; dataset manifests + model provenance recorded in SUB
(`dataset_versions`, `trained_models` tables) and the verdict file.

## 13. Promotion flow

```text
SUSPECT → gates → HEART → G3 → PENDING_OPERATOR
   → operator confirm → HND package → detection change (validated) → PROMOTED
   → operator reject  → KILLED (rationale required) → ORG indexed
```

Every transition is a SUB decision event (actor=system|operator, rationale,
evidence refs).

## 14. Failure flow

```text
infra failure (lab/Splunk/embed) → Episode INDETERMINATE / honest-BLOCKED
   → decision event recorded → iteration stops or rotates; never scored
model failure (refusal/stall/invalid) → candidate stays SUSPECT; sub-floor
   council → operator escalation; never auto-pass
gate failure → KILLED with gate + rationale → ORG negative record
crash → idempotent re-drive; SUB natural keys prevent double-record
```

## 15. Operator-confirmation flow

Queue records live in SUB (`promotion_queue`), surfaced via CLI
(`hunt queue`), resolvable only by explicit operator confirm/reject with
rationale. `promote_policy: confirm` in `hunt.yaml` is machine-enforced:
`alert_bin.promote` requires an operator actor token; there is no code path
that promotes without it. The same queue carries detection changes, model
serving, playbook activations, roster weight activations.

## 16. Diagrams

Component planes: DESIGN §6. Runtime iteration: §3.1. Data flow: DESIGN §8.
State ownership: §4. Training: §3.3/§12. Promotion: §13. Failure: §14.

```text
BOUNDARY SUMMARY

        operator                models (fleet)              Red (lab)
           │                         │                         │
           ▼                         ▼                         ▼
   hunt CLI/queue ──▶ hunt_loop ──▶ investigation/HEART ──▶ MutationSpec overlay
           ▲              │                                         │
           │              ▼                                         ▼
   readouts/confirm ◀── SUB/ORG ◀── Episode ◀── telemetry ◀── _run_chain_test
                                          (UNCHANGED Red execution)
```
