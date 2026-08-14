# REVIEW_DEFENSIVE_BULLY_CURRENT_STATE

Evidence and rationale behind the final Defensive Bully design. This document
records what was read, what was traced, what was verified against current HEAD,
and why each design decision follows. It is the supporting evidence for
`DESIGN_DEFENSIVE_BULLY_FINAL.md`; where the two ever disagree, the DESIGN doc
is authoritative for *what to build* and this doc is authoritative for *why*.

Evidence markers used throughout:
- **VERIFIED FACT** — read in code at HEAD `47d3e884`, caller/callee traced.
- **INFERENCE** — reasoned from verified facts, not directly observed.
- **DESIGN DECISION** — a choice this review makes.

Runtime-role tags: `PRODUCTION_WIRED`, `CONFIG_GATED`, `BENCH_ONLY`, `LIBRARY_ONLY`, `PARTIALLY_WIRED`, `LEGACY`, `DEAD`.

---

## Executive verdict

**DESIGN REQUIRES REFINEMENT.**

The Defensive Bully thesis is sound and is the right system to build on Portal:
hunt the *cousins* of what we already know — the near-neighbor attack one
mutation from a covered one that our detection misses — grade it by distance
from known, bully the finding with the fleet before promoting it, exit as a
family-generalizing detection, and compound through six feeds including
fleet-local training. `ANOMALOUS_UNCLASSIFIED` as the primary product, not an
edge case, is the correct orientation and Portal already scores it as a catch.

The refinement is substantial but it is *refinement, not replacement*. The
review found that the existing design and its handoff systematically
**under-credit what Portal already has**, in ways that change dispositions,
reduce build risk, and in three places change what should be built at all:

1. **Several components the design calls "NEW" already exist and are wired.**
   The autonomous hunt loop (`loop.py`, CLI-dispatched), the playbook memory
   (`playbooks.py`, wired into that loop), the drift/canary machinery
   (`drift_gate.py` + `drift-check`/`model-canary` CLI), the learn-recall
   organ (`field_journal`, wired into the loop), a platform agent loop
   (`portal/platform/agent/` decide+rank), and a model-acceptance gate
   (`candidate_eval.py`) are all present. Their disposition moves from NEW to
   RETROFIT/REUSE, which materially lowers the build.
2. **The "miss = finding" primitive already exists deterministically.**
   `episode.py::derive_verdict` computes `FAILED = red landed but detection
   missed`, with synthetic-never-PROVEN enforced in code. The work is to
   *reorient* this from a capability score into a hunt finding graded for
   cousin-novelty — not to build the primitive.
3. **The training-toolchain gap is much narrower than stated.** `mlx-lm>=0.31`
   is already a dependency, so the LoRA trainer (`mlx_lm.lora`) and adapter
   fusion (`mlx_lm.fuse`) ship with the environment. Only GGUF conversion
   (llama.cpp) is genuinely absent tooling. Redeploy (`ollama create`) and
   acceptance (`candidate_eval` + `model-canary`) already exist.
4. **Two component dispositions in the current design are wrong.**
   `growth_loop.prove_draft` is the *detection-exit* proof harness
   (fires-on-attack / quiet-on-benign / no-regression), not the finding-bin;
   and `response_loop.py` carries distinct, keepable value (response IR
   playbooks, reverse red-scenario generation, threat intake) and should not be
   replaced by the detection handoff — HND is a new sibling.

Three handoff claims were found imprecise at HEAD and are corrected below
(`multichain` is not naively clear-by-default; `notify_scoreboard` does not
score ANOMALOUS equal to CONFIRMED; the RBP arm is not "only a bench harness").

None of this weakens the thesis. It makes the build cheaper, the boundaries
cleaner, and the compounding claims more credible because more of the substrate
is already load-bearing.

---

## Current HEAD / repository state

**VERIFIED FACT.**
- Repo: `github.com/ckindle-42/portal-5`, branch `main`, clean working tree.
- **HEAD = `47d3e884c8f0415ed26dbf77f5e817a22ce613ac`** (2026-08-13, "chore(spine): re-pin units after lane-closeout + Ollama-docs commit").
- The design/handoff reference commit `ee9272ee` is present in history; HEAD is 5 commits ahead.
- **Zero `.py` files in the RBP surface changed between `ee9272ee` and HEAD** (`git diff --name-only ee9272ee..HEAD -- 'portal/modules/security/**/*.py' 'portal/platform/inference/router/*.py'` → 0). The 5 intervening commits touched wiki fact-units, eval/bench tests, and the 62-model `PENDING_VERDICTS` reports.

**INFERENCE.** The design's and handoff's code claims are structurally trustworthy at my HEAD because the code they reference is byte-identical to their reference commit. Every claim was nonetheless re-verified directly per the task's "current HEAD wins" rule.

---

## Required reading completed

All three primary sources read completely (not skimmed):
- `BULLY_CONCEPT_SOURCE.md` — the offensive concept (Andy Gill's autonomous 0-day hunter).
- `BUILD_PROGRAM_DEFENSIVE_BULLY.md` — the current intended design (treated as hypotheses).
- `HANDOFF_DEFENSIVE_BULLY_CONTEXT.md` — the historical reasoning (respected; implementation claims re-verified).

Repository documentation read: root `CLAUDE.md` (canonical, hand-authored); `docs/AGENT_LOOP.md`, `docs/generated/ARCHITECTURE_MAP.md` (located), `docs/reconciliation/SECURITY_ARM_RECONCILE_20260716T022931Z.md` (operational reconciliation). Config anchors: `config/portal.yaml` (single source of truth for workspaces + MCP fleet), `config/backends.yaml`, `config/spine_surfaces.yaml`, `.mcp.json`. Validation registry: `scripts/validate_system.py` + `scripts/validation/*.py`.

---

## Current Portal architecture (reconstructed from code)

**VERIFIED FACT.** Portal 5 v8.0.0 is an Open WebUI enhancement layer:
`OWUI → Portal Pipeline (:9099) → Ollama (:11434) → GGUF models`. Ollama is the
sole chat-inference backend. MLX serves only embeddings (:8917), reranking
(:8925), speech (:8918), transcription (:8924) — not chat.

Platform (`portal/platform/`):
- `inference/router/` — the pipeline: `routing.py`, `streaming.py`, `handlers.py`, `non_streaming.py`, `context_inject.py` (RAG injection), and **`council.py`** (the multi-model review primitive). Rule: MCP modules and `portal.platform.inference` never import each other.
- `agent/` — a promoted platform agent loop: `decide` (goal-grounded decide-turn) and `rank` (`ToolCandidate`/`select_tools`/`select_parameters`), consumed via `CapabilityProvider`/`Executor` contracts (dependency inversion).
- `mcp_host/`, `memory/`, `storage/`, `wiki/`, `cli/` (incl. `cli/models.py`, the model redeploy leg).

MCP fleet (from `SECURITY_ARM_RECONCILE`, CLAUDE.md ports): 20 services up, incl. `portal-security` (:8919), `portal-rag` (:8921), `portal-reranker` (:8925), embedding (:8917), `portal-mitre` (:8929), `portal-detections` (:8932), `portal-proxmox`, `portal-wiki` (:8931), `portal-memory` (:8920).

Security module (`portal/modules/security/`): ~60k LOC incl. tests. The core is `core/` with Red execution, Blue/Purple analysis, the SIEM adapters (`core/siem/`), the investigation store (`core/investigation/`), and the security MCP tools (`tools/`).

Resource envelope: single M4 Pro Mac Mini, 64 GB unified memory; ~157 Ollama models available; historical single-model cap ~15.5–20 GiB (`OLLAMA_GPU_OVERHEAD`). Lab: Proxmox + Splunk SIEM + AD, subnet `10.10.11.0/24`, 4 active vulhub targets.

---

## Current Red architecture (Section D)

**VERIFIED FACT** — Red is `PRODUCTION_WIRED`.

- **Scenario grammar.** `exec_chain.py::SCENARIOS` (a dict spanning ~L221–L1200) defines each attack: `{name, target_host, target_port, vulhub_env, red_order (ordered lab-tool calls), red_prompt (instructs the red model), detect_ground_truth ([ATT&CK IDs blue must catch]), persistence_technique}`. Example: `kerberoast_to_da` → `red_order = [start_lab_target, run_nmap_scan, check_cve, exploit_service, establish_persistence, lateral_move, exfiltrate_data, revert_lab_target]`, `detect_ground_truth = [T1558.003, T1003.006, T1053.005]`.
- **Executor.** `exec_chain.py::_run_exec_chain` (L3157) and `_run_model_turn` (L2627) drive the red model turn-by-turn through `red_order`.
- **Lab.** `lab.py::dispatch_lab_tool` (L450) / `lab_dispatch` (L1010) execute lab tools; `snapshot_lab_vms`/`restore_lab_vms` (L146/L177) manage clean-snapshot lifecycle via the Proxmox MCP; `query_stealth_events` (L251) pulls stealth telemetry.
- **Trajectory (agentic) layer.** `trajectory_score.py` composes a trajectory verdict from per-landed-step episodes + an objective oracle, with the never-PROVEN invariant lifted to trajectory level; `emergent_gaps.py` turns off-script landed-but-undetected steps into gaps.

**DESIGN DECISION.** The existing boundary — *"Red is the means; the bully directs which attack Red runs but never rewrites Red execution"* — is correct and cleanly realizable. **The `SCENARIOS` catalog is the attack grammar**; directing Red means supplying/perturbing scenario definitions (`red_order` / params / prompt / ground-truth), while `_run_exec_chain` and `lab.py` are untouched. One constraint: `SCENARIOS` is a hardcoded dict inside `exec_chain.py`, so mutated scenarios must enter as **data** (a scenario-provider the executor already accepts — `candidate_eval.py` imports `SCENARIOS` + `_prepare_scenario`, confirming scenarios are consumed as dicts). The mutation director produces scenario dicts; it does not edit the executor.

---

## Current Blue/Purple architecture (Section E)

The historical conclusion — "current B/P is largely a benchmark/evaluation architecture" — is **half right and now stale**. Re-derived at HEAD:

**VERIFIED FACT — two production CLI surfaces exist**, dispatched by `core/__main__.py`:
1. **Bench harness** (fallthrough `main()`): `run_bench` (`commands/run.py:651`, `benign_corpus_bench.py:137`), `run_blue_chain_tests` (`blue.py:1342`), `run_blue_orchestration` (`blue_orchestrate.py:1537`), `run_benchmark` (`bench_investigation.py:315`); central object `BenchConfig` (`_config.py`). This is the dominant, most-developed path and is `BENCH_ONLY` in character (scored JSON per invocation).
2. **Autonomous engagement loop** (`loop` subcommand → `loop_cli.py::loop_main` → `loop.py::run_engagement`/`resume_engagement`): a real `PRODUCTION_WIRED` perceive→decide→act→verify→learn controller — Perceive (`accumulate_observations`), Decide (`playbooks.resolve_phases`), Act (multi-model chain via `lab_dispatch`), Verify (named `oracles`), Learn (`field_journal` recall + write-back). Hard caps (50 iters / 7200 s / 200 lab actions), checkpoint+resume, notify on `ENGAGEMENT_ESCALATED/STUCK/COMPLETE` with `resume_cmd` embedded in the alert.

Plus `PRODUCTION_WIRED` subcommands: `goal`, `drift-check`, `model-canary`, `capability`, `candidate-eval`, `self-index`, `stage2-propose`, `compliance-report`.

- **Correlation substrate.** `episode.py::Episode` (immutable, deterministic, one per purple run) + `DetectionCorrelation` (per-technique: `has_detection_rule`, `has_spl_hit`, `within_window`, `target_match`, `source ∈ {live, synthetic-fallback, synthetic}`). `derive_verdict` → `PROVEN` (red landed AND detection confirmed, real + in-window + right-target) / **`FAILED` (red landed but detection missed)** / `INDETERMINATE` / `UNAVAILABLE`. **Synthetic telemetry never yields PROVEN — enforced in code (L156), not prompt.** Episode is constructed by `blue.py` (L1601/L2122), `agentic_blue_eval.py` (L167), and the corpus/benign benches — i.e. the purple correlation path.
- **Consolidation.** `multichain.py::consolidate` (L110) cools N independent analyst chains into one decision (`AUTO_CONFIRM`/`CONFIRM_AND_ESCALATE`/`ESCALATE`/`DISMISS`), separating a KNOWN-BAD channel (technique ≥ quorum of chains) from an UNKNOWN channel (below-quorum votes + SIMILAR neighbours). Top-line verdict `CONFIRMED` if a known-bad landed else `ANOMALOUS_UNCLASSIFIED`.

**INFERENCE.** The bench path is where the effort has gone, but the *organism shape* (loop, playbooks, learn, drift, goal, candidate-eval) is present and wired — it simply hunts **known playbook phases**, not **cousins by distance**, and treats a detection miss as a **capability score**, not a **hunt finding**. That is the reorientation the Defensive Bully needs, and it is much less than a rebuild.

---

## Runtime wiring and call paths (Section C classifications)

| Surface | Symbol | Runtime role | Evidence |
|---|---|---|---|
| Red executor | `exec_chain._run_exec_chain` | PRODUCTION_WIRED | called by bench + loop act-step |
| Lab dispatch | `lab.lab_dispatch` / `dispatch_lab_tool` | PRODUCTION_WIRED | Proxmox MCP |
| Episode/verdict | `episode.derive_verdict` | PRODUCTION_WIRED | built by blue/purple path |
| Engagement loop | `loop.run_engagement` | PRODUCTION_WIRED | `core loop run` |
| Playbooks | `playbooks.resolve_phases` | PRODUCTION_WIRED | consumed by loop |
| Field journal | `field_journal.record_engagement` | PRODUCTION_WIRED | loop learn-leg + blue_modes |
| Drift/canary | `drift_gate` / `drift_cli` | PRODUCTION_WIRED | `core drift-check` / `model-canary` |
| Platform agent | `platform.agent.decide`/`rank` | PRODUCTION_WIRED | `goal_decide`/`decision_engine` shims |
| Candidate eval | `candidate_eval` | PRODUCTION_WIRED | `core candidate-eval` |
| Council | `platform...council.aggregate_opinions` | PRODUCTION_WIRED | council workspaces + `council_agreement` |
| Scoreboard | `notify_scoreboard.score_arm` | CONFIG_GATED / BENCH | scoring of hunt-and-notify runs |
| Cousin embryo | `unknown_defense.compute_similarity` | PARTIALLY_WIRED | reachable, but weak scorer (see below) |
| Alert-bin embryo | `growth_loop.prove_draft` | LIBRARY_ONLY | no `run_growth_loop` CLI wrapper |
| ORG infra | `research/tools/rag_mcp` (kb_ingest/search) | PRODUCTION_WIRED | MCP :8921, but doc corpus |
| SUB seed | `investigation.EvidenceStore`/`CaseNotebook` | PARTIALLY_WIRED | case-scoped, `:memory:` default |
| Coverage | `capability_graph.update_graph_from_episode` | PARTIALLY_WIRED | in-memory, no persist |
| Redeploy | `platform...cli/models.import-gguf` | PRODUCTION_WIRED | GGUF→Modelfile→`ollama create` |
| Response/intake | `response_loop` | LIBRARY_ONLY | no loop wrapper found |

---

## Original Bully principles (Section F — mechanism, not features)

For each offensive primitive: *why it works* → *general principle* → *defensive analogue* → *does the current design preserve it*.

- **Hallucination bin (suspect-until-proven).** Works because LLM analysis is confidently wrong; making a finding *earn* promotion through executable gates drives false positives to near-zero. Principle: **proof gates code-enforced, not model-asserted.** Defensive analogue: a landed cousin is a SUSPECT until it replays and is analyst-visible. Current design preserves the *shape* (BIN G0–G3) but the existing gates (`growth_loop`) are placeholder-`True` — the principle is not yet embodied.
- **Grammar fuzzing (structural validity + adversarial values).** Works because random bytes get "invalid format"; a *valid* structure with a hostile field reaches the parser. Principle: **stay inside the grammar, perturb the payload.** Defensive analogue: valid TTP chains (`red_order` grammar) with perturbed params/timing/sub-technique/artifacts. Preserved as MUT; deliberate mutation is the missing half.
- **Low-privilege validation.** Works because a finding reachable only as SYSTEM is worthless. Principle: **validate in the consumer's real context.** Defensive analogue: a detection visible only to the eval harness's god-view is worthless — it must be visible to the SOC analyst under real queue load. Preserved as BIN G3; not yet a real gate.
- **Known-defence DB (multiplicative deprioritisation).** Works because recording dead ends stops repeat waste. Principle: **negative results steer future work.** Defensive analogue: known-benign / known-covered / dead-cell DB deprioritises cells. Preserved as SUB feed 2; no persisted steering DB exists yet.
- **ROI target selection (pessimistic payout / hours).** Principle: **spend the next hour where expected value is highest.** Defensive analogue: risk-reduction-per-cost over the biggest blind spot. Preserved as TGT; genuinely absent today.
- **Knowledge loop (query priors before, record outcome after, everything indexed).** Works because the twentieth hunt inherits nineteen hunts of context. Principle: **mandatory recall + universal indexing, tool-enforced.** Defensive analogue: ORG. Infra present (`rag_mcp`); enforcement + universal indexing absent.
- **Self-bullying → fleet council.** Principle: **independent falsification before belief.** Preserved and *exceeded* by the fleet council; the objection is not yet a gate.
- **Local fine-tune.** Principle: **turn your own hunt history into a sharper specialist.** Preserved as HARV+TRAIN; wiring absent, tooling mostly present.
- **Human-confirmed consequential actions.** Principle: **operator owns noise-producing promotions.** Preserved: `PROMOTE_POLICY=confirm` is pervasive.
- **Thin MCP / thick logic; persistent tooling; campaign orchestration.** Principle: **testable business logic behind stable tool surfaces.** Portal matches this structurally (MCP servers are thin; `core/` is thick).

---

## 15-point translation review (Section G)

Fidelity: `STRONG` / `STRONG_WITH_REFINEMENT` / `PARTIAL` / `SURFACE_ONLY` / `MIS-TRANSLATED` / `MISSING` / `SUPERSEDED`.

| # | Offensive primitive | Underlying principle | Portal capability at HEAD (evidence) | Fidelity | Final recommended translation |
|---|---|---|---|---|---|
| 1 | Hunt a binary for a bug | Spend effort where a gap is likely | `capability_graph` coverage cells (in-memory, no persist); `loop` hunts playbook phases not cells | PARTIAL | Persist coverage cells in SUB; loop hunts a cousin-neighborhood chosen by TGT |
| 2 | Finding = working PoC | A finding is landed reality nothing caught | `episode.derive_verdict` FAILED = red-landed-blue-missed, code-computed | STRONG | Consume Episode FAILED/detection-miss as the suspect finding seed; **reorient, don't rebuild** |
| 3 | Hallucination bin gates | Proof gates code-enforced | `growth_loop.prove_draft` legs are placeholder-`True` | PARTIAL | Build real G0–G3 (see O). Note `growth_loop`'s 3 legs are the HND detection proof, not the finding bin |
| 4 | Known-defence DB | Negative results steer | benign corpus (`benign_corpus_bench`) + `spl_detections` exist; no persisted multiplicative steering DB | PARTIAL | SUB known-benign/known-covered/dead-cell DB with multiplicative deprioritisation |
| 5 | ROI = payout / hours | Expected value per cost | none (`goal`/`capability` are substrate only) | MISSING | TGT: risk-reduction-value / test-cost over cells |
| 6 | Low-priv gate | Validate in consumer context | not a gate today | MISSING | BIN G3 analyst-visible, measured through Splunk/console (see O) |
| 7 | Reporting = bounty submission | Ship the fix that generalizes | `response_loop` does response IR + reverse-gen + intake, NOT detection generalization | PARTIAL | HND = new sibling (generalized Sigma/correlation/log-source). **Keep `response_loop`.** |
| 8 | Grammar fuzzing | Valid structure, hostile value | `SCENARIOS` grammar + `emergent_gaps` (accidental off-script) | PARTIAL | MUT: deliberate structurally-valid scenario perturbation + reuse `emergent_gaps` |
| 9 | Personal FAISS | Query priors; distance = relevance | `rag_mcp` (MLX embed + LanceDB + reranker) indexes a **doc** corpus; `unknown_defense` uses token-overlap not embeddings | PARTIAL | ORG = retrofit `rag_mcp` to hunt memory; distance = cousin metric; embedding finds, feature-overlap explains |
| 10 | One model self-bully | Independent falsification | `council.py` fleet review with isolated seats, `strongest_objection` carried but **not gating** | STRONG_WITH_REFINEMENT | HEART: add objection gate beside `aggregate_opinions`; keep `council_agreement` translation + disagreement-as-novelty |
| 11 | Fine-tune Qwen | Train a specialist on your hunts | `mlx-lm` present (lora+fuse tools); redeploy + `candidate_eval` accept present; wiring + GGUF-convert absent | PARTIAL | HARV→TRAIN: build wiring; add llama.cpp GGUF convert only |
| 12 | Variant analysis | Chase the neighborhood | `unknown_defense` (spatial embryo, weak); `drift_gate` (a **different** drift — bench-metric rot) | PARTIAL | BR-COUSIN (spatial, on ORG) + BR-DRIFT (temporal, on `drift_gate` baseline engine retargeted to per-detection firing) |
| 13 | Knowledge loop enforced | Mandatory recall + universal index | `rag_mcp` not enforced pre-hunt; no universal indexing | MISSING | ORG invariant: pre-hunt recall + post-hunt index enforced **in the tool** |
| 14 | Coverage plateau | Stop when signal stops | none | MISSING | PLT: plateau on gap-classification deltas + cost-per-cousin meter |
| 15 | Per-campaign CLAUDE.md | Learned per-class instructions | `playbooks.py` YAML methodology exists, wired to loop, but **hand-authored** | PARTIAL | PLAY: reuse machinery + add the learning leg (accumulate/refine from outcomes) |

**Net:** 1 STRONG, 1 STRONG_WITH_REFINEMENT, 8 PARTIAL, 4 MISSING, 0 mis-translated/superseded. Every row has a named home in existing code; none requires inventing an unprecedented abstraction. The four MISSING rows (ROI targeting, analyst-visible gate, plateau, universal-index enforcement) are the genuinely new deterministic work.

---

## Current reusable asset inventory (Section K)

Discovered by search + confirmed by reading (search finds candidates; reading determines relevance):

- **Council** `platform/inference/router/council.py` — isolated multi-seat review, roster-denominator quorum, ESCALATE/ABSTAIN first-class, code-decides/model-explains enforced. `CouncilOpinion.strongest_objection` produced by every seat.
- **Episode** `episode.py` — deterministic correlation substrate; FAILED miss-verdict; synthetic-never-PROVEN in code.
- **ORG engine** `research/tools/rag_mcp.py` — MLX mxbai embed (:8917) → LanceDB vector + tantivy FTS (hybrid) → Qwen3 reranker (:8925) top-K, graceful dense fallback.
- **SUB seed** `investigation/evidence.py` + `case_notebook.py` — immutable append-only EvidenceStore, `SourceAuthority` provenance hierarchy, supports/contradicts links, `supersede`; a documented **seven-memory-kinds taxonomy** (see below).
- **Loop** `loop.py` + `loop_cli.py` — perceive/decide/act/verify/learn, checkpoint/resume, notify, hard caps.
- **Platform agent** `platform/agent/decide.py`+`rank.py` — goal-grounded decide + tool/param ranking via `CapabilityProvider`.
- **Playbooks** `playbooks.py` — versioned YAML methodology (phases/scope/budget/stop/escalate).
- **Drift/canary** `drift_gate.py` + `drift_cli.py` — rolling-baseline delta (trailing window, noise floor 0.03, scipy z-score, min-baseline 3, window 7) + model behavior canary.
- **Coverage** `capability_graph.py` — Procedure/Detection/Gap entities, deterministic gap classifier, ATT&CK Navigator + heatmap artifacts.
- **Cousin embryo** `unknown_defense.py` — EXACT/SIMILAR/NONE + overlapping-features citation + matched-unit id.
- **Scoreboard** `notify_scoreboard.py` — CONFIRMED + ANOMALOUS_UNCLASSIFIED both notifications; ordinal trustworthiness rank.
- **Honest-miss oracle** `recall_attribution.py` — label-blind presence oracle (check BM), World A/B split.
- **Mutation feed** `emergent_gaps.py` + `trajectory_score.py` — off-script landed-but-undetected → Gap; never-synthetic.
- **Response/intake** `response_loop.py` — response IR playbooks, reverse red-scenario generation, CVE/report intake.
- **Redeploy** `platform/inference/cli/models.py` — GGUF import → Modelfile → `ollama create`.
- **Acceptance** `candidate_eval.py` — single-slot, delta-vs-incumbent, isolated results, confirm-only.
- **Detection state** `siem/spl_detections.py` — technique→SPL + expected-signal library.
- **SIEM adapters** `core/siem/` — collect, capture-store/enrichment, HEC ship, index-wait, spl backend/detections, blue triage.

---

## Cousin-model analysis (Section H)

**DESIGN DECISION — cousin distance is multi-dimensional, computed by code, explained by features. Embedding similarity alone is insufficient** (and `unknown_defense`'s own comments prove a pure lexical/embedding score misleads: a real variant scored 0.09 because unrelated tokens diluted the overlap).

A finding is compared to the nearest known reference across five weighted axes, each contributing measurable, separable value:

1. **Behavioral-sequence distance** — edit distance over the ordered technique/tool sequence of the landed chain vs. the reference chain (`red_order` shape + observed technique order from the Episode). *Why it earns its place:* two attacks with identical embeddings but reordered kill-chains are different cousins; sequence catches that.
2. **ATT&CK-graph distance** — shortest-path/relationship distance over the technique/sub-technique/tactic lattice (parent, sibling sub-technique, shared tactic), sourced from the MITRE MCP (:8929) and `capability_graph` technique tags. *Value:* encodes domain structure embeddings don't (T1558.003 ↔ T1558.004 are siblings; that is a near cousin regardless of text).
3. **Telemetry-shape distance** — distance over the `DetectionCorrelation` signature: which log sources/event codes fired, row-count band, within-window, field-set overlap. *Value:* the detection engineer's axis — two behaviorally similar attacks that surface in different telemetry are different remediation problems.
4. **Detection-response distance** — how the existing detection responded: fired-and-attributed / fired-unattributed / partial-rule / silent. *Value:* this is the axis that defines a *gap* — a cousin that flips a detection from fire to silent is the product.
5. **Semantic distance** — ORG embedding distance (MLX mxbai) over the natural-language description, reranked. *Value:* the catch-all for novelty the structured axes miss; used to *find* candidates, then the structured axes *grade* them.

Composite distance `D = Σ wᵢ·dᵢ` with per-axis weights in config (`config/security/...`); the **classification bands are code-deterministic**, not model-chosen:

- **SAME** — `D ≈ 0` on behavioral + ATT&CK + telemetry (same technique, same shape, caught the same way).
- **SIMILAR** — near on ATT&CK/behavioral, small telemetry delta, detection still fires (a covered cousin).
- **NEW** — near on ATT&CK/behavioral **and** detection-response distance is large (fires weaker/differently/silent) — *a cousin our detection misses*. **This is the product.**
- **DIFFERENT** — far on ATT&CK + behavioral + semantic (unrelated).
- **ANOMALOUS_UNCLASSIFIED** — landed reality with signal that resists all-axis classification (I8 unease): full success, valued by distance, never dropped.

**How it is explained to a human:** embedding + ORG *find* the nearest neighbors; the structured axes and `unknown_defense`'s feature-overlap layer *cite* the specific overlapping features and the exact axis that made it NEW (e.g., "sibling of T1558.003 on the ATT&CK axis; identical process lineage; **detection T1558.003-SPL went silent** — telemetry shows the Kerberos ticket request moved to an event code the rule doesn't cover"). Meaningful novelty vs. arbitrary semantic distance is distinguished by requiring the **detection-response axis** to move: a large semantic distance with no change in whether/how we catch it is DIFFERENT, not NEW.

---

## Spatial-cousin analysis (Section I)

**DESIGN DECISION.** Spatial cousin = near-neighbor in ORG on the composite metric above, where detection-response distance is large — structurally related to a known attack but escaping coverage. Built as **BR-COUSIN**, retrofitting `unknown_defense`'s grade space (EXACT/SIMILAR/NONE → SAME/SIMILAR/NEW) onto ORG's embedding+rerank, keeping feature-overlap as the *explanation* layer. Representation: the finding's Episode + `DetectionCorrelation` embedded into ORG; measurement: composite `D` vs. the k nearest known references.

---

## Temporal-cousin analysis (Section I)

**DESIGN DECISION.** Temporal cousin = a detection drifting from *its own* firing baseline — a technique that evolved into a cousin of its prior self. Built as **BR-DRIFT**, retrofitting the **existing `drift_gate` rolling-baseline engine** (trailing window, per-metric delta, noise floor, scipy z-score, min-baseline, INSUFFICIENT-BASELINE handling) — but **retargeted**: the tracked series changes from `(scenario, blue_model) → bench metric` to `(technique, detection) → firing signature` (confidence, detection latency, event-population count, sequence length, partial-rule-satisfaction fraction, telemetry-source presence).

Signals separated (a required disambiguation the current drift gate does not make):
- **Attacker evolution** — firing weaker/later/partial while telemetry sources are intact and baseline population is stable ⇒ true temporal cousin.
- **Telemetry failure** — an expected log source dropped to zero ⇒ ingestion problem, not an attacker (route to ops, not the bin).
- **Environmental change** — baseline distribution shift across all detections ⇒ recalibrate baseline.
- **Detection degradation** — rule edit/version changed the query ⇒ detection lineage event.

`model-canary` is reused unchanged to hold the *model* constant while measuring detection drift (so a quant/template shift is not misread as attacker evolution).

---

## Alert-bin analysis (Section O)

**DESIGN DECISION.** Keep suspect-until-proven; the four gates are correct but must be *real* (today they are placeholder-`True` in `growth_loop`, which is actually the detection-exit proof, not the finding bin — so the bin gates are built fresh):

- **G0 — has-evidence.** Episode has real `evidence_refs` and the finding cites them; `used_synthetic=False`. (Cheap, code-only.)
- **G1 — replay-reproduces (static + dynamic).** A signature/indicator match alone is G0 at best; G1 requires re-running the cousin scenario against a **clean Proxmox snapshot** and observing the *same* `DetectionCorrelation` shape (behavioral reproduction, not just a string match). Reuses `lab.snapshot/restore` + the Episode correlation.
- **G2 — not-benign.** Evaluated against the benign corpus (the RESOLVED `P5-SEC-BENIGN-CORPUS-001` home, check BQ). The concept-native home for alert-fatigue.
- **G3 — analyst-visible.** Measured through Splunk/console as-seen-by-the-SOC-analyst under queue load (a notable that actually surfaces), not the harness god-view. Reuses `siem/` (notable creation, index-wait) to prove the finding would appear in the real console.

**Correction (from HEAD).** The handoff's "flip `multichain.consolidate` from clear-by-default to suspect-by-default" is imprecise: `consolidate` already only DISMISSes when *every* concluding chain ruled out with zero signal (L164); any signal, unnamed anomaly, or non-conclusion already escalates. Flipping its default would break the legitimate benign path and spike BQ/AZ. **Suspect-by-default belongs at the finding lifecycle vs. ground-truth-of-what-red-landed** (an Episode FAILED where red landed is a suspect finding until G0–G3), not inside the multi-chain consensus step.

---

## Council analysis (Section N)

**VERIFIED FACT.** `council.py::aggregate_opinions` is a majority vote over a roster denominator (non-voters never shrink it), with `required_participation`/`required_votes = ceil(frac·roster)`, ESCALATE when participation is short or no leader reaches quorum, ABSTAIN first-class, dissent preserved, and "code decides, model explains" enforced (the synthesizer may not change the decision; the machine decision is rendered first). Every seat already produces `strongest_objection`, `missing_evidence`, `conditions_to_change` — **and none of those gate the decision.**

**DESIGN DECISION — HEART.** Add a deterministic objection gate *beside* (not inside) `aggregate_opinions`, so the general platform primitive is unchanged and other council workspaces do not regress. A new pure function `evaluate_with_objection_gate(opinions, rebuttals, …)`:
- collects each seat's `strongest_objection`;
- an objection is **material** if it names missing evidence or a condition-to-change that the finding's evidence does not satisfy (code check against `evidence_refs`/correlation, not model opinion);
- **any unrebutted material objection ⇒ BLOCK** (no promotion), regardless of vote counts;
- otherwise the vote/quorum result stands.

`council_agreement.py` is **refactored, not discarded**: keep its detection↔review domain translation and its valuable **disagreement→ANOMALOUS_UNCLASSIFIED (novelty)** mapping; route its per-seat objections into the new gate.

**ROSTER.** Anti-monoculture is partly built (isolated seats, roster-denominator quorum, BL floor). Add retrospective weighting floored so no seat reaches zero, cap correlated-seat dominance (seats sharing a base model share a correlation group; a group cannot exceed a configured share of effective weight), and never let popularity override a *correct* minority dissent — reweighting uses retrospective correctness of *objections that held*, not vote-with-the-majority frequency.

---

## Knowledge / compounding analysis (Section L + "storage is not learning")

**VERIFIED FACT — the compounding chain is broken in three places today:**
1. `capability_graph` rebuilds per invocation and only emits view artifacts (no state reload) ⇒ coverage does not persist.
2. `rag_mcp` indexes a doc corpus, is not queried pre-hunt by enforcement, and hunt emissions are not indexed ⇒ no semantic hunt memory.
3. `investigation` store is case-scoped and defaults to `:memory:` ⇒ cross-hunt state does not survive.

The traceable loop `observation → capture → validation → persistence → retrieval → decision → changed behavior → new observation` is therefore incomplete: capture and persistence exist in pieces, but **retrieval-that-changes-the-next-decision** does not close. SUB + ORG exist precisely to close it, and the design must *demonstrate* a second hunt behaving differently because of the first (success criterion, not assertion).

**Seven-memory-kinds taxonomy (VERIFIED, `case_notebook.py`) is a hard invariant the design must honor:** agent-scratch (discard) · case-notebook · case-evidence (immutable append-only) · Prior-Incident library (long-lived, analyst-confirm-only) · Confirmed org knowledge (operator-approved) · analyst-feedback (growth loop only) · **agent long-term memory NOT PERMITTED at inference**. This last rule is the poisoning-resistance discipline: ORG retrieval feeds the *hunt loop's* context, never an implicit model long-term memory; production cousin-grading stays label-blind (BM).

---

## Six-feed analysis (Section L)

| Feed | Source→…→changed-behavior loop | Status at HEAD | Disposition |
|---|---|---|---|
| 1 Semantic hunt memory (ORG) | hunt emission → embed → index → pre-hunt query → neighborhood pick | infra present (`rag_mcp`), corpus wrong, not enforced, not fed | RETROFIT + enforce |
| 2 Known-benign/covered/dead-cell DB | outcome → SUB → multiplicative deprioritise in TGT | benign corpus + `spl_detections` exist; no steering DB | NEW in SUB |
| 3 ROI/target intelligence | cell stats → risk/cost score → next pick | absent | NEW (TGT) |
| 4 Training-pair harvest | hunt/council/cousin judgments → role-tagged jsonl | `recall_attribution` labeler present; harvest absent | NEW (reuse labeler; label-blind BM) |
| 5 Fleet-local fine-tune | corpus → LoRA → fuse → GGUF → accept → serve → later hunt | ~5.5/7 legs tooled; wiring + GGUF-convert missing | RETROFIT + narrow NEW |
| 6 Per-scenario playbook memory | outcomes → refined instruction set → shapes loop + small model | `playbooks.py` authored + wired; learning leg absent | RETROFIT + add learning |

Provenance/contradiction/decay/poisoning are served by the existing `SourceAuthority` hierarchy + supports/contradicts links; supersession by `case_notebook.supersede`. Aging/decay and dedup are NEW deterministic policies over SUB/ORG.

---

## Training-flywheel analysis (Section M)

**VERIFIED FACT — leg-by-leg at HEAD:** FEED (`rag_mcp kb_ingest`) EXISTS · HARVEST NEW (labeler `recall_attribution` present) · TRAIN tool `mlx_lm.lora` PRESENT (`mlx-lm>=0.31` dep), no wiring · FUSE tool `mlx_lm.fuse` PRESENT, no wiring · **GGUF-CONVERT tool MISSING** (no llama.cpp `convert_hf_to_gguf`/quantize anywhere) · REDEPLOY (`models.import-gguf`→`ollama create`) EXISTS · ACCEPT (`candidate_eval` delta-vs-incumbent + `model-canary`) EXISTS · SERVE confirm-only.

**DESIGN DECISION — the one new tool is llama.cpp GGUF conversion.** Pipeline: `mlx_lm.lora` (train adapter from role-tagged jsonl) → `mlx_lm.fuse` (fused HF-format model) → **llama.cpp `convert_hf_to_gguf` + quantize** → `ollama create` → `candidate_eval` + `model-canary` gate → operator-confirm serve. Compare specialist against: base model / base+ORG-retrieval / base+playbook / base+retrieval+playbook / trained specialist — train survives only where it beats retrieval+playbook by a measurable margin (difficulty is not a reason to cut; lack of measurable gain is). Memory: training competes with inference for unified memory, so it runs offline/off-hours, never concurrent with a live hunt.

---

## Mutation analysis (Section P)

**DESIGN DECISION — MUT = structurally-valid perturbation of the `SCENARIOS` grammar.** The insight is validity, not randomness: a random `red_order` gets dropped by the lab; a *valid-but-perturbed* scenario reaches the detection and exposes the gap. Mutation dimensions, all expressible as scenario-dict edits: parameters, timing/inter-step delay, step ordering, command form, process/parent-child relationship, identity/host, protocol, artifact/encoding, adjacent **sub-technique** (the ATT&CK-sibling move — the highest-yield dimension because it is exactly "same class, different parser"). Governed by an operator **mutation-budget** dial (how many dimensions, how far). MUT produces scenario dicts consumed by the untouched executor; `emergent_gaps` continues to harvest *accidental* off-script cousins; `response_loop`'s reverse red-scenario generator seeds *directed* mutations from an existing detection.

---

## Targeting / ROI analysis (Section Q)

**DESIGN DECISION — TGT ranks cousin-neighborhoods by risk-reduction-value / test-cost**, pessimistic like the concept. Inputs (all available or derivable): asset criticality (lab target metadata), ATT&CK relevance + uncovered-risk (from `capability_graph` gaps), cousin-novelty (BR distance), prior miss-rate (Episode history in SUB), detection-confidence, and test cost (lab wall-clock + Ollama compute + analyst effort). Known-benign/known-covered/dead cells are **multiplicatively deprioritised** from SUB (feed 2), mirroring the concept's AM-PPL penalty.

---

## Plateau / cost analysis (Section Q)

**DESIGN DECISION — PLT stops a neighborhood when useful-discovery rate flattens, not when embeddings stop clustering.** A neighborhood is exhausted when the rate of *new gap-classification transitions* (SIMILAR→NEW, covered→silent) per unit test-cost falls below a floor for a window — measured, like drift, with the rolling-baseline engine. Cost accounting (compute + lab-hours + analyst-effort per cousin found) is tracked in the SUB cost ledger and must be shown *falling* over the program's own runs — the economic-compounding proof, distinct from the technical-compounding proof.

---

## Detection-handoff analysis (Section R)

**DESIGN DECISION — HND is a new sibling to `response_loop`, not its replacement.** A promoted cousin exits as a **family-generalizing** package: a generalized Sigma rule (covers the family, not just the instance), the SPL/correlation change, required log-source onboarding, ATT&CK mapping, evidence package + reproduction steps, false-positive analysis (against benign corpus), known limitations, IR implications, a regression test, and coverage-impact delta. Portal produces the package automatically; **operator confirms** promotion into the live detection set. `growth_loop.prove_draft`'s three legs (fires-on-attack / quiet-on-benign / no-regression) are the natural G-proof for the generalized rule and are reused here — this is their correct home.

---

## Recent architectural drift (Section S)

**VERIFIED FACT.** Since `ee9272ee`: no RBP `.py` changed (classification `UNRELATED` to design at code level). Relevant developments that *precede* the reference and change assumptions vs. the handoff (`PROVIDES_BETTER_PRIMITIVE` / `CHANGES_ASSUMPTION`):
- Platform agent loop promoted to `portal/platform/agent/` (`CHANGES_ASSUMPTION`: LOOP composes an existing loop).
- `loop.py`/`loop_cli.py`, `drift_gate`/`drift_cli`, `candidate_eval`, `goal` all wired (`PROVIDES_BETTER_PRIMITIVE`).
- `mlx-lm>=0.31` dependency (`CHANGES_ASSUMPTION`: trainer present).
- Spine collapsed to manifest surfaces (`config/spine_surfaces.yaml`, check BR): new files under `security/core/*` cost zero new units (`SUPPORTS_DESIGN` — the "spine explosion" fear is false).

---

## Replacement / migration analysis (Section T)

Full table in `MIGRATION_DEFENSIVE_BULLY.md`. Summary: the current arm is **not** one disposable block. Keep and reorient the Episode, council, ORG engine, SUB seed, loop, drift engine, coverage entities, candidate-eval, redeploy, `response_loop`, `emergent_gaps`, `recall_attribution`. Build real gates over the placeholder bin. Add the genuinely new deterministic pieces (TGT, PLT, analyst-visible G3, universal-index enforcement, HND generalization, HARV/TRAIN wiring, GGUF-convert). The dominant **bench path is repositioned** as the model-acceptance harness, not deleted. Red is untouched.

---

## Missing capabilities (Section U — justified only)

Recommended because they strengthen the core product: behavioral + telemetry-shape embeddings (feed the cousin metric); ATT&CK graph distance (MITRE MCP already present); decision-event provenance (SUB decision log — the audit spine); knowledge decay + dedup (poisoning/collapse resistance); detection lineage (disambiguate BR-DRIFT); shadow/canary detection deployment (safe HND rollout — `model-canary` is the analogue); uncertainty as targeting signal (council dissent → TGT). **Not** recommended: new vector DB (LanceDB present); external agent frameworks (banned by CLAUDE.md Rule); a bespoke scheduler now (the daemon is a listed extension; the loop is built to allow it).

---

## Unnecessary complexity (Section V — what should not be built)

- Do **not** build a second knowledge store: ORG is `rag_mcp` retrofitted; the doc spine stays design-facts-only and must not become a knowledge dump.
- Do **not** flip `multichain.consolidate`'s default (breaks the benign path; wrong layer for suspect-by-default).
- Do **not** replace `response_loop` (loses response IR + reverse-gen + intake).
- Do **not** make `aggregate_opinions` itself objection-gating (regresses all council workspaces).
- Do **not** treat `growth_loop` as the finding bin (it is the detection-exit proof).
- Do **not** re-open `P5-SEC-BENIGN-CORPUS-001` (RESOLVED; G2's home).
- Do **not** try to fix the model-catalog spine re-pin fan-out here (separate, out of scope).

---

## Resource / operational constraints

Single M4 Pro Mac Mini, 64 GB unified memory; Ollama sole chat backend; historical ~15.5–20 GiB single-model cap. Council fan-out of N reviewer calls and any concurrent hunt compete for memory ⇒ bound roster size and serialize reviewer calls under a memory cap; training runs offline/off-hours. Lab is Proxmox + Splunk + AD (`10.10.11.0/24`), 4 active vulhub targets, MCP fleet on 8917–8932. `PROMOTE_POLICY=confirm` pervasive — every consequential promotion (finding, detection, trained model, roster change, playbook) is operator-gated.

---

## Required design changes (consolidated)

1. Reclassify LOOP, PLAY, BR-DRIFT, HARV(labeler), TRAIN-accept, field-journal from NEW to RETROFIT/REUSE; compose LOOP on `platform.agent` + `loop.py`.
2. Reorient finding origin to `episode.derive_verdict` FAILED (miss = suspect finding), not a new primitive.
3. Build the cousin metric as the 5-axis composite (§H), code-graded, feature-explained; retrofit `unknown_defense` grade space onto ORG.
4. Build BR-DRIFT on the `drift_gate` baseline engine, retargeted to per-detection firing; add the four-way signal disambiguation.
5. HEART = objection gate *beside* `aggregate_opinions`; refactor (not replace) `council_agreement`, keeping translation + disagreement-as-novelty.
6. Build real BIN G0–G3; put `growth_loop`'s proof legs under HND; keep `response_loop`; add HND generalization as a sibling.
7. Correct SCORE: distance-weighted value so a far NEW cousin can exceed a known-bad, without demoting ANOMALOUS below CONFIRMED (BN).
8. Persist coverage + known-benign/covered/dead-cell DB + cost ledger + decision log in SUB; enforce ORG pre-hunt recall + universal indexing in the tool.
9. TRAIN: build harvest + train/fuse wiring; add only the llama.cpp GGUF-convert tool; gate with `candidate_eval` + `model-canary`; confirm-serve.
10. Honor the seven-memory-kinds taxonomy and the BM/BL/BN/BQ/AZ/BR/AW gates throughout.

---

## Final recommendation

**DESIGN REQUIRES REFINEMENT.** Adopt the thesis and the component set, apply the ten changes above, and re-cost the build on the (larger-than-credited) existing substrate. The result is a defensive hunting system that discovers structurally-adjacent attacks our detections miss, adversarially attempts to disprove its own findings, promotes only evidence-backed discoveries under operator confirm, exits as family-generalizing detections, and compounds through all six feeds including training its own cousin-specialist models — with more of it reused than rebuilt, and every claim grounded in code at HEAD `47d3e884`.
