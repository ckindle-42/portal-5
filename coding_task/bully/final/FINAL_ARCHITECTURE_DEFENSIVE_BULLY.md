# FINAL ARCHITECTURE — Defensive Bully (implementation level)

The where and how: module boundaries, current Portal integration points, call
paths, state boundaries, Red/B/P boundary, model boundaries, MCP boundaries,
and the knowledge/training/promotion/failure/operator-confirmation flows.
Normative companion to `FINAL_DESIGN_DEFENSIVE_BULLY.md` (which wins on
*what*). Citations to existing code are HEAD `47d3e884`; the implementing
agent re-verifies them at its own HEAD.

---

## 1. Component map and expected locations

All new code lives in one nested package,
`portal/modules/security/core/bully/`, covered by ONE new spine surface entry
(`unit-surface-sec-bully`, glob `portal/modules/security/core/bully/*.py` —
precedent: `unit-surface-siem`, `unit-surface-investigation`;
`config/spine_surfaces.yaml:360-376` shows the existing sec-core globs are
non-recursive, so the entry is deliberate, not assumed).

```text
portal/modules/security/core/bully/
  __init__.py             public application API only
  contracts.py            enums + immutable boundary DTOs (versioned)
  config.py               hunt.yaml/heart.yaml loading + per-hunt snapshot
  store.py                SUB — SQLite WAL authority, migrations, repositories
  events.py               decision-event emission (append-only, hash-chained)
  outbox.py               transactional index outbox + dead-letter remediation
  evidence.py             evidence manifests, content-hash verification,
                          capture-store adapters
  organ.py                ORG — hunt_memory projection, recall receipts,
                          decision impacts (LanceDB + :8917/:8925 clients)
  signatures.py           BehaviorSignature construction from Episodes
  cousin_engine.py        BR-COUSIN — candidate union, distance, two-axis
                          grading, explanation
  drift_engine.py         BR-DRIFT — baselines, attribution order, resets
  orchestrator.py         LOOP — hunt stage pipeline, leases, budgets,
                          checkpoint/resume, admission control
  investigation.py        LOOP's investigation arm — adapter over the
                          blue_orchestrate section runners
  mutation.py             MUT — typed MutationPlan, validation, compilation
                          to scenario overlays, budget enforcement
  promotion.py            BIN — gate validators + promotion state machine
  adversary.py            HEART — falsification seats, objection lifecycle,
                          veto, waiver
  roster.py               ROSTER — eligibility/diversity/reliability records
  targeting.py            TGT — eligibility gates, posteriors, ROI, decisions
  plateau.py              PLT — statistical plateau + resets
  costing.py              typed cost metering + pricing profile
  scoreboard.py           SCORE — catch/trust/discovery axes
  handoff.py              HND — family package, detection-proof legs,
                          proposal lifecycle
  harvest.py              HARV — quarantined pair extraction, dataset builds
  playbooks.py            PLAY — learned playbook lifecycle
  training.py             TRAIN — dataset→train→fuse→convert→create→accept
                          orchestration (subprocess boundaries)
  soc.py                  G3 — notable ship + triage-lane measurement adapter
  notify.py               promotion-queue/BLOCKED/plateau notifications via
                          the existing dispatcher
  observability.py        metrics/audit adapters
  migrations/             ordered SQL migration resources
cli:  portal/modules/security/core/commands/hunt_modes.py  (+ `hunt`
      subcommand registered in __main__.py, following the existing dispatch
      pattern at __main__.py:20-62)
config: config/security/hunt.yaml, config/security/heart.yaml
tests: portal/modules/security/tests/ (existing surface glob) +
       tests/security/bully/ integration lanes
```

**Not created:** new MCP servers, Docker services, ports, OWUI functions,
pipeline routes, vector stores, or a second knowledge authority.

## 2. Module/service boundaries

Boundary rules (enforced by review + import-scan tests):

- Only `orchestrator.py` sequences a hunt iteration. Other modules never call
  Red, Splunk, or models except through their documented interfaces
  (INTERFACES doc).
- Only `store.py` performs SQL I/O; only `organ.py` touches the `hunt_memory`
  projection; only `harvest.py` writes corpus JSONL (under the hunt dir).
- `cousin_engine.py`, `targeting.py`, `plateau.py`, `scoreboard.py`,
  `costing.py`, `roster.py`, `signatures.py`, `drift_engine.py` are pure
  compute over injected data/read interfaces — unit-testable with `tmp_path`,
  no network (Testing Rules).
- Model calls happen only inside: `investigation.py` (section runners),
  `adversary.py` (seats/rebuttals), `handoff.py`/`playbooks.py` (drafting) —
  always through the existing call helpers (`agentic_blue_eval._call_model`
  pattern: pipeline default, direct-Ollama fallback) with model ids resolved
  from config via the backends registry. **No model name is hardcoded.**
- `training.py` orchestrates host-native subprocesses (mlx_lm, llama.cpp);
  training libraries are never imported by runtime startup paths (zero-setup
  rule; verified by an import-scan test).
- The bully package never imports from MCP modules, and MCP modules never
  import it (Rule 3). The operator surface is CLI + (optionally, later) thin
  read-only methods on the existing security MCP.

## 3. Current Portal integration points

| Existing surface | Integration | Evidence at HEAD |
|---|---|---|
| `exec_chain.py` SCENARIOS / `_prepare_scenario:3071` / `_run_chain_test:3564` | MUT compiles overlays into this machinery; zero edits | scenarios are dicts; `set_scenario` loads overlays |
| `episode.py` Episode/derive_verdict | Red→bully contract, unchanged | `:45-74,:146-183` |
| `siem/spl_backend.py::query_episode:161-205` | investigation-arm retrieval (label-blind, episode-scoped) | verified |
| `blue.py::collect_and_ship_scenario_telemetry:1710-1912` | telemetry plane, unchanged | verified |
| `blue.py::_cite_or_drop:831` / `_discriminator_contradicts:915` | grounding gates inside the investigation arm | verified |
| `blue.py::_build_evasion_feedback:2185` / `_run_evasion_purple:2217` | MUT directive channel seed | verified |
| `blue_orchestrate.py` runners (`:496,662,1098,1263`), `_run_three_section:1970`, `capture_expert_handoff:1779` | investigation arm machinery (extracted from the bench shell) | verified |
| `portal/platform/inference/router/council.py` (`parse_opinion:147`, participation `:190-237`) | HEART mechanics; aggregate untouched | verified |
| `siem/capture_store.py` + `capture_recipes.py` + `scripts/security_capture_recipes.py` | G1a replay + G1b dynamic re-execution + HND regression format | verified |
| `siem/blue_triage.py:38-80` | G3 measurement lane | verified |
| `benign_corpus_bench.py` + `_VERDICT_GROUNDING_POLICY` (`blue_orchestrate.py:91-103`) | G2 instruments | verified |
| `drift_gate.py:35-51` machinery | BR-DRIFT statistics seed (module untouched) | verified |
| `siem/spl_detections.{py,yaml}` (discriminator_tokens, sibling_ids ×11, spl_variants) | grading vetoes/explanation + HND generalization source | verified |
| `emergent_gaps.py:32-80` | MUT off-script supply | verified |
| `response_loop.py` (RESPONSE_PRIMITIVES:53-63, technique map:81-104, reverse-gen, intake) | HND IR seed; MUT reverse-gen seed; KEPT-SIBLING | verified |
| `unknown_defense.py` (grade vocabulary, overlapping_features:60-154) | BR-COUSIN explanation layer + documented lexical baseline | verified |
| `recall_attribution.py` (evidence_presence, attribute_cell) | HARV eval-side labels only (BM) | verified |
| `notify_scoreboard.py:21,32-37` | SCORE catch/trust base | verified |
| `capability_graph.py` (`classify_gap:76-123`) | coverage-cell classifier; SUB-backed loader added | verified |
| `investigation/evidence.py` / `case_notebook.py` | SUB record schema + supersede pattern + seven-kinds doctrine | verified (in-memory today) |
| `cli/models.py::cmd_models_import_gguf:218-259` | TRAIN redeploy leg | verified |
| `candidate_eval.py` + `intake.py:16` + `drift_cli.py` model-canary + PENDING_MODEL_VERDICTS flow | TRAIN acceptance legs | verified |
| `portal/platform/inference/notifications` dispatcher | notify.py (loop.py:232-298 pattern) | verified |
| `portal/platform/wiki/provenance_ledger.py::append_entry:66` | promotion audit trail | verified |
| `perception.py:17,46-53` (LAB_CIDR, assert_in_lab) | MUT scope enforcement | verified |
| MITRE MCP :8929 / detections MCP :8932 | ATT&CK enrichment + SPL library reads | live |
| embed :8917 (`embedding-server.py`, CPU ST harrier) / rerank :8925 (`reranker_mcp.py:30`, MLX Qwen3) | ORG services | verified |
| `loop.py` (caps, checkpoint, notify) + `playbooks.py` (container/validation) | discipline mirrored; container pattern reused; files untouched | verified |

## 4. Call paths

### 4.1 Hunt iteration (primary path)

```text
python3 -m portal.modules.security.core hunt run --neighborhood auto
  └─ commands/hunt_modes.py::run_hunt
     └─ bully/orchestrator.py::run_hunt(config)
        ├─ store: acquire lease; append HUNT_CREATED (+ outbox)        [TX]
        ├─ store.load_context()                  cells/known-state/plateau/cost
        ├─ organ.recall(context) → RecallReceipt          [MANDATORY]
        ├─ targeting.select(...) → TargetDecision (recorded)
        ├─ mutation.validate_and_compile(plan) → scenario overlay
        │     └─ scope: perception.assert_in_lab; budget checks in code
        ├─ exec_chain._prepare_scenario(overlay) + _run_chain_test(...) [UNCHANGED]
        ├─ blue.collect_and_ship_scenario_telemetry(...)                [UNCHANGED]
        ├─ episode.Episode + save_evidence                              [UNCHANGED]
        ├─ investigation.run_arm(episode)   (section runners over
        │     spl_backend.query_episode; _cite_or_drop grounding)
        ├─ signatures.build(episode) → BehaviorSignature
        ├─ cousin_engine.grade(signature, organ.knn(...), coverage) → verdict
        ├─ drift_engine.update(episode, detections) → flags
        ├─ promotion.process(candidate)
        │     ├─ G-1 authz → G0 evidence → G1a static replay
        │     ├─ G1b dynamic re-exec (capture_recipes | directed red)
        │     ├─ G2 causality/not-benign (benign corpus + controls)
        │     ├─ adversary.review(candidate) → objection gate
        │     └─ G3 soc.measure_visibility(candidate) → triage-lane receipt
        ├─ store.record_* (decision events, cousin, known-state, cost)  [TX]
        ├─ organ.index_emissions(...) via outbox            [UNIVERSAL]
        ├─ harvest.append_pairs(hunt_record)
        ├─ scoreboard.update(...)
        └─ plateau.evaluate(neighborhood) → continue | rotate | stop
```

### 4.2 Promotion + handoff path

```text
operator: portal security hunt queue --confirm <candidate_id>
  └─ promotion.promote(candidate_id, operator_actor, note)   [actor-checked]
     ├─ handoff.build_package(candidate) → 11-part family package
     ├─ detection-proof legs: fires-on-attack (recipe replay) +
     │    quiet-on-benign (benign corpus) + no-regression (BQ/AZ lanes)
     ├─ regression recipe → capture_recipes registration (validated change)
     ├─ detection change → spl_detections.yaml operator commit (pre-push
     │    validation green)
     ├─ provenance_ledger.append_entry(...)                 [EXISTING]
     ├─ deployment receipt + post-deploy replay → cell → KNOWN_COVERED
     └─ store: supersede cousin record; decision events     [TX]
```

### 4.3 Training path

```text
operator: portal security hunt train --role cousin-smeller
  └─ bully/training.py::run(role)
     ├─ harvest.build_dataset(role) → immutable version + splits + manifest
     ├─ size floor → honest non-build if below
     ├─ operator dataset release (separate approval)
     ├─ exclusive resource lock; preflight memory/disk; refuse if a hunt or
     │    the bench supervisor is active
     ├─ mlx_lm.lora (subprocess) → mlx_lm.fuse → llama.cpp convert+quantize
     ├─ models import-gguf equivalent → ollama create <base>-cousin<dv>
     ├─ acceptance: frozen five-arm suite + intake floors + candidate delta
     │    + model-canary
     ├─ PASS → PENDING_MODEL_VERDICTS entry → operator confirm → role-alias
     │    canary → atomic alias promotion (config; sync-config if touched)
     └─ FAIL/non-gain → recorded; active alias unchanged; candidate retained
         for analysis; no serve
```

## 5. State boundaries

```text
OUTSIDE REPO (PORTAL5_HUNT_DIR, default /Volumes/data01/portal5_hunt/):
  hunt_state.db          SUB authority (SQLite WAL, migration-managed)
  corpus/<role>/<dv>.jsonl + manifest.json    HARV datasets
  playbooks/             PLAY learned records (mirrored into SUB)
  artifacts/             handoff packages, training artifacts metadata

EXISTING, UNCHANGED ROLE:
  results/…                       bench artifacts (read-only seed inputs)
  results/captures/               replay source for G1a/G1b
  portal_wiki/canonical/          design facts ONLY (never runtime state)
  LanceDB rag/ + memory tables    untouched; ORG owns ONLY hunt_memory
  field_journal/ (in-git)         legacy; read-only source for PLAY/HARV

SPINE: one new surface entry; ≤1 authored design unit per phase; two-commit
re-pin sequence when BS requires.
```

## 6. Red/B/P boundary

- **Red side** (`exec_chain`, `lab.py`, `capture_recipes`, attack image,
  sandbox/proxmox MCPs): consumed via its existing direction surface —
  scenario dicts are data (`_prepare_scenario`/`set_scenario`); evasion
  context; fallback techniques. Zero edits. MUT emits data, never code
  changes to Red.
- **B/P side:** the bench drivers (`blue.py`/`blue_orchestrate.py` mains)
  remain the bench lane until LOOP proves parity, then stay as the
  repositioned acceptance lane; the section machinery is imported by
  `bully/investigation.py`; `episode.py`, `query_episode`, telemetry
  shipping, grounding gates used unchanged. The two-Episode reconciliation is
  comment-level: truth-plane `episode.py::Episode` is canonical;
  `agentic_blue_eval.py:82-91`'s local dataclass is documented as the capture
  replay DTO.
- **Contract:** the Episode (reason codes + evidence refs) is the sole
  Red→bully interface; the compiled MutationPlan overlay is the sole
  bully→Red interface.

## 7. Model boundaries

- Roles: retriever/hunter/expert (investigation arm), falsifier seats
  (HEART), rebuttal seat, drafting (HND/PLAY), trained specialists
  (cousin-smeller, disprover). All model ids resolve from
  `config/security/hunt.yaml` + `heart.yaml` through the backends registry —
  the same resolution path as `blueteam-council` today
  (`config/portal.yaml:721-747`).
- Role resolution snapshots backend alias + model digest/tag + prompt/
  template version + inference params per invocation record.
- Defaults at design time (operator-editable): the verified bench roster
  families — one seat per family in HEART, ≥2 independent families.
- Label-blind: no production prompt receives ground truth; corpus answer keys
  stay scorer-only (`config/security_corpus.yaml` contract preserved; BM
  import-boundary test covers the bully package).
- Model output is schema-validated and untrusted; parse/validation failures
  retry within budget then abstain/block.

## 8. MCP boundaries

Rule 3 respected: MCP servers stay independent; no MCP imports the bully
package or vice versa. The bully's capabilities are **not** MCP tools in this
build — the operator surface is the CLI (`portal security hunt …`) and the
promotion queue. MITRE (:8929) and detections (:8932) MCPs are read-only
consumables via their public contracts. A future read-only hunt-status MCP
method is a documented extension, not this build.

## 9. Inference interactions

- Investigation arm: multi-round tool-loop over `query_episode` with
  `_cite_or_drop` grounding; budgets per role; stall caps unchanged.
- HEART: isolated single calls per seat (platform council pattern) + one
  rebuttal round when material objections stand; seats serialize when backend
  memory requires.
- Drafting: single-shot with schema validation; failures fall back to
  deterministic templates (no fabricated prose).
- All model calls honor per-turn timeouts and pipeline slot discipline; every
  invocation is recorded (role, alias, digest, params, evidence citations).

## 10. Embedding/reranking interactions

- ORG upsert: canonical record text → batched :8917 embeddings → LanceDB
  projection add (via outbox worker, not inline in a transaction).
- ORG recall: query embedding → vector search (k×5 candidates) → cosine
  distances retained for grading; optional :8925 rerank for presentation
  order only.
- Projection rows carry source hashes; dereference-and-validate before use;
  stale rows rejected.
- Failure: embed service down → recall receipt cannot be satisfied → hunt
  blocks honestly (never silent lexical grading); reranker down →
  presentation degrades only.

## 11. Knowledge flow

```text
emissions (candidates, verdicts, kills, defenses, benigns, plateaus,
           playbook deltas, detection changes, objections/rebuttals)
  → SUB records (typed truth + decision events)        [same transaction]
  → outbox entries (required-for-closure flags)        [same transaction]
  → organ projection upsert (embedded, metadata-rich, hash-referenced)
  → recall at next hunt (receipt) → TGT penalties/priors → BR-COUSIN priors
  → DecisionImpact records (what changed, why)
  → changed target selection / grading / stopping       (the compounding proof)
```

## 12. Training flow

§4.3 above; dataset manifests + model provenance recorded in SUB
(`dataset_versions`, `trained_models`) and the PENDING_MODEL_VERDICTS file;
trainer runs host-native under an exclusive lock; artifacts content-addressed;
production serving remains Ollama.

## 13. Promotion flow

```text
CREATED → G-1 → G0 → G1a → G1b → G2 → HEART → G3 → AWAITING_OPERATOR
   → operator confirm → HND package → detection change (validated)
   → deployment receipt → post-deploy replay → KNOWN_COVERED cell
   → operator reject  → DISPROVED (rationale required) → ORG indexed
```

Every transition is a SUB decision event (actor=system|operator, rationale,
evidence refs, expected versions). Changed evidence creates a new alert
version and invalidates downstream passes.

## 14. Failure flow

```text
infra failure (lab/Splunk/embed) → Episode INDETERMINATE / honest-BLOCKED
   → decision event → iteration stops or rotates; excluded from yield math
model failure (refusal/stall/invalid) → candidate stays CREATED; sub-floor
   council → operator escalation; never auto-pass
gate failure → terminal outcome with gate + rationale → ORG negative record
gate-infrastructure failure → BLOCKED (retryable), distinct from gate failure
index failure → outbox retry → dead letter blocks closure (operator-visible)
crash → lease expiry → resume from last committed event; idempotent re-drive
training failure → active alias unchanged; checkpoint retained
```

## 15. Operator-confirmation flow

Queue records live in SUB (`promotion_queue`), surfaced via CLI
(`hunt queue`), resolvable only by explicit operator confirm/reject with
rationale. `promote_policy: confirm` in `hunt.yaml` is machine-enforced:
`promotion.promote` requires an operator actor token; there is no code path
that promotes without it. Separate authenticated commands per consequential
action (finding promotion, detection acceptance, dataset release, model
promotion, playbook activation, roster activation, objection waiver, policy
weakening, plateau override) — one approval never implies another.
Notifications fire on queue arrivals.

## 16. Concurrency and resource architecture

- Single-box 64GB unified memory; Ollama single-model ~15.5–20GiB. Council
  rosters bounded; reviewer calls serialize under memory pressure.
- **Admission control:** before lab actions, the orchestrator checks the lab
  lock and active bench-supervisor/engagement activity (the nightly bench is
  a real co-tenant); contention → queue or honest wait, never overlap.
- Training holds an exclusive lock; never concurrent with a live hunt or
  bench run; preflight memory/disk; resumable checkpoints.
- Lab actions are serialized by the budget triple (iterations/wall-clock/
  lab-actions) and Proxmox snapshot discipline.
- Projection rebuild/backfill is rate-limited and resumable.

## 17. Boundary summary diagram

```text
        operator                models (fleet)              Red (lab)
           │                         │                         │
           ▼                         ▼                         ▼
   hunt CLI/queue ──▶ orchestrator ──▶ investigation/HEART ──▶ MutationPlan overlay
           ▲              │                                         │
           │              ▼                                         ▼
   readouts/confirm ◀── SUB/ORG ◀── Episode ◀── telemetry ◀── _run_chain_test
                                          (UNCHANGED Red execution)
```
