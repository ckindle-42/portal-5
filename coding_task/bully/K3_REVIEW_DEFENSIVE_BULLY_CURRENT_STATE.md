# REVIEW — Defensive Bully Current State

**Review of record.** This document records the evidence and reasoning behind the
final Defensive Bully design. Every load-bearing claim was verified by reading the
cited code at the review HEAD, not inferred from names, search matches, or the
prior handoff. Where the prior handoff/build-program and current HEAD disagree,
HEAD wins and the disagreement is recorded as drift.

---

## 1. Executive verdict

The existing design (`BUILD_PROGRAM_DEFENSIVE_BULLY.md`) is conceptually correct
and its component inventory is largely right. Its thesis — cousin discovery as the
product, suspect-until-proven promotion, an adversarial fleet council, six
compounding feeds, Red left alone — survives deep review intact.

Its **implementation assertions**, however, drifted from HEAD in
ten material places, and it missed four existing assets that change the build:

| # | Prior design claim | Verified reality at HEAD | Consequence |
|---|---|---|---|
| 1 | `multichain.consolidate` is **clear-by-default** (no signal → DISMISS) | It is **escalate-by-default**: no-concluder → `ESCALATE`/`ANOMALOUS_UNCLASSIFIED` (`multichain.py:127-138`); DISMISS requires unanimous `RULED_OUT` *and* zero signal (`multichain.py:162-172`); unnamed anomaly forces escalation (`:155-161,178-179`) | BIN2 "replace clear-by-default" is **already partially satisfied**. Reframed: suspect-by-default must land at the *finding/alert* level (the bin), not the consolidation level |
| 2 | `EvidenceStore`/`CaseNotebook` are "the seed of persistent state" | `EvidenceStore` is **in-memory only** (`investigation/evidence.py:118-119`), used only by `bench_investigation.py` + tests. `CaseNotebook` is SQLite with a `:memory:` default and **no production callers** (`case_notebook.py:53`); its `supersede()` is real (`:162-169`) | SUB is more NEW than the design admits. What is reusable is the **EvidenceRecord schema** (provenance, source-authority, supports/contradicts) and the **CaseNotebook SQLite+supersede pattern**, not any store |
| 3 | `capability_graph`, `field_journal` = RETROFIT, "behavior-changing recall" | `capability_graph` is rebuilt **per invocation** from assets + replayed result JSON; there is no graph store (`capability_graph.py:251-315`). `field_journal.recall` is keyword-count scoring (`field_journal.py:95-115`); `loop.py:205-211` consults it but only records `len(prior)` — the content never enters a prompt or decision. The **only** behavior-changing read is `capability/index.py::_journal_prior_score` (journal hit-count ranks capabilities) | The design's "persistent coverage" and "behaviour-changing recall" primitives exist in shape only. SUB owns this state going forward; capability_graph stays an ephemeral readout |
| 4 | ORG = "retrofit `rag_mcp`" (kb_ingest/kb_search) | `rag_mcp` (`portal/modules/research/tools/rag_mcp.py`) is document-directory-oriented: `kb_ingest(kb_id, source_dir)` chunks **files** (`:215-310`); `kb_search` returns **rerank scores, not vector distances** (`:411-464`); no record-level upsert/delete, no metadata filtering, no raw k-NN distance | ORG needs a record-level, distance-returning, metadata-filterable API. Final design: a security-side organ module on the **same infrastructure** (LanceDB, embedding :8917, reranker :8925), not a rag_mcp retrofit. rag_mcp stays a generic doc KB (MCP independence, Rule 3) |
| 5 | BR-DRIFT is NEW | `drift_gate.py` **already exists** — rolling-window metric drift + model canary (`drift_gate.py:1-60`; `TRACKED_METRICS`, `NOISE_FLOOR`, `MIN_BASELINE_RUNS`, scipy-based). It drifts **bench metrics**, not detection behavior | The temporal-cousin instrument **seeds from drift_gate's rolling-baseline machinery** and retargets its signals. Not a greenfield build |
| 6 | G3 analyst-visible is a gate to invent | `siem/blue_triage.py` **already polls Splunk alerts and produces P1–P4 triage reports** through the pipeline's blueteam workspace (`blue_triage.py:1-60`) | G3 becomes **measurable**: ship the candidate as a Splunk notable, run the triage lane, observe report priority/SLA. The asset existed; the design didn't know |
| 7 | MUT = retrofit `emergent_gaps` + new probe | `emergent_gaps.py` verified as landed-but-undetected → Gap feed. **But the design missed two more MUT primitives**: the `--evasion` loop re-runs red with blue's detections as an adaptation directive (`blue.py::_build_evasion_feedback:2185-2214`, `_run_evasion_purple:2217`); and `capture_recipes.py` executes **deterministic model-free attacks** (`scripts/security_capture_recipes.py`) | MUT has three existing seeds, not one: deliberate variant direction (scenario overlay), detection-feedback evasion, and deterministic re-execution (the G1b replay engine) |
| 8 | B/P brain: REPLACE `blue.py`/`blue_orchestrate.py` wholesale | The **driver shells** are bench-only. But `blue_orchestrate`'s section machinery (Retriever/Hunter/Expert loop, `_cite_or_drop` label-blind grounding at `blue.py:831-912`, mentor, budgets, handoff capture) is a genuinely good **investigation arm**, and `blue.py::collect_and_ship_scenario_telemetry` (`:1710-1912`) is the telemetry plane the hunt loop itself needs | Refined disposition: **SPLIT, not REPLACE**. Section runners + telemetry + grounding are REUSED inside the new loop; the bench-driver shell and scoring orientation retire |
| 9 | Platform council carries objections; `aggregate_opinions` discards them | **Confirmed** (`council.py:77-96` data model; `:190-237` counts votes only). **Sharper finding**: the security adapter `council_agreement._platform_opinions` (`:44-66`) doesn't even *populate* `strongest_objection`/`missing_evidence` — it maps to bare SUPPORT/REJECT/ABSTAIN | HEART keeps platform council mechanics (isolation, roster accounting, ESCALATE-on-subfloor) and adds the **objection gate** the concept requires |
| 10 | PROMOTE_POLICY=confirm "throughout" | PROMOTE_POLICY is **prose-only** — not a machine-readable key anywhere in `config/portal.yaml`; the operative artifact is `config/PENDING_MODEL_VERDICTS.md` + `scripts/execute_pending_verdicts.py` (never auto-edits routing) | The final design makes promote-policy **machine-readable** in the hunt config; operator-confirm becomes enforced configuration, not convention |

**Assets the prior design did not know about:**

- `drift_gate.py` — rolling-baseline + canary machinery (→ BR-DRIFT seed).
- `siem/blue_triage.py` — live Splunk→triage-report lane (→ G3 measurement).
- `blue.py::_build_evasion_feedback` / `_run_evasion_purple` — detection-feedback
  red re-execution (→ MUT directive channel).
- `capture_recipes.py` + `scripts/security_capture_recipes.py` — deterministic,
  model-free attack re-execution and capture certification (→ BIN G1b dynamic
  reproduction engine and HND regression-test generator).
- `spl_detections.yaml` `distinguishing_features.discriminator_tokens` /
  `sibling_ids` + `spl_variants` — machine-readable per-technique discriminators
  and sibling relationships (→ cousin explanation layer + contradiction gate
  `_discriminator_contradicts`, `blue.py:915-960`).
- `episode.py` truth-plane verdict machinery (`derive_verdict:146-183`: synthetic
  never PROVEN; RED_LANDED + DETECTION_CONFIRMED → PROVEN) — already the
  code-decides substrate the bully needs.
- `portal/platform/agent/{loop,decide,rank,goal}.py` — promoted generic bounded
  agent-loop primitives (evaluated for LOOP; rejected — see §16).
- `siem/spl_backend.py::query_episode` (`:161-205`) — episode-scoped,
  **label-blind** unlabeled telemetry haystack via indexed `episode_id` HEC
  field. The exact retrieval primitive a label-blind hunt needs.

**Final verdict: `DESIGN REQUIRES REFINEMENT`** — the architecture's skeleton is
kept; the component map, dispositions, and ten drift corrections above materially
change what gets built. Not "valid as written" (its retrofit targets and
replacement scope are wrong in places) and not "material redesign" (the concept
translation, cousin thesis, six feeds, adversarial heart, and phasing all stand).

---

## 2. Current HEAD / repository state

```text
pwd:        /Users/chris/projects/portal-5
branch:     main
HEAD:       47d3e884c8f0415ed26dbf77f5e817a22ce613ac
            "chore(spine): re-pin units after lane-closeout + Ollama-docs commit"
remote:     origin https://github.com/ckindle-42/portal-5.git
status:     clean vs origin/main (not ahead/behind); working tree has only
            untracked bench artifacts (another agent's in-flight run): .serena/,
            results/antares_probe/baseline_pytest.txt, tests/benchmarks/results/*,
            bench_cad_probe.DEEPWEN_FOLLOWUP_001.py
```

Recent history (`git log --oneline -15`): lane-closeout eval gating, slot-fix
workspace resolution, complexity-ratchet trims, closeout-verdict miner fix,
bench_cad_probe reasoning fix, secondary card-driven evals. Security-module
history (`git log --oneline -- portal/modules/security/`): capture-recipe
certification series, V6 hunt-and-notify scoreboard (`d817f256`), V5A recall
attribution (`d31da27a`), P1 council-quorum reconcile (`2bceecce`), P3 benign
alert-fatigue (`d17a5012`), V5B routed remediation, cli.py facade decomposition
(`e232bf01` et al.), config-JSON extraction (`3d2aca98`, `65958b7f`).

The prior design's reference commit was `ee9272e` (2026-08-13). Review HEAD
`47d3e884` is ~6 commits newer; no security-module code changed between them
(the delta is eval-gate instrumentation + spine re-pins). Handoff claims were
nonetheless re-verified against `47d3e884` individually; the drift table above
is the result.

**Review method note:** breadth mapping was assisted by parallel read-only
explorer agents; **every load-bearing claim used in this review and the design
was then personally re-verified by reading the cited files at HEAD** (episode.py,
multichain.py, growth_loop.py, emergent_gaps.py, unknown_defense.py,
council_agreement.py, platform council.py, investigation/evidence.py,
investigation/case_notebook.py, loop.py, field_journal.py, recall_attribution.py,
capability_graph.py, response_loop.py, analyst_verdict.py, playbooks.py,
notify_scoreboard.py, blue_orchestrate.py key sections, blue.py key sections,
agentic_blue_eval.py key sections, exec_chain.py key sections, rag_mcp.py,
cli/models.py, spl_detections.py/.yaml, drift_gate.py, blue_triage.py,
telemetry.py, spl_backend.py, security_mcp.py, playbooks, config/portal.yaml,
config/security_corpus.yaml, config/spine_surfaces.yaml, KNOWN_LIMITATIONS.md).

---

## 3. Required reading completed

| Document | Lines | Read | Treatment |
|---|---|---|---|
| `coding_task/v8/BULLY_CONCEPT_SOURCE.md` | 304 | Complete | Concept-mechanism authority |
| `coding_task/v8/BUILD_PROGRAM_DEFENSIVE_BULLY.md` | 472 | Complete | Design hypotheses to verify |
| `coding_task/v8/HANDOFF_DEFENSIVE_BULLY_CONTEXT.md` | 306 | Complete | Historical reasoning; claims re-verified |
| `coding_task/v8/design_review.md` | 2172 | Complete | This task's contract |
| root `CLAUDE.md` | — | Complete (system-provided) | Ground rules 1–13 |
| `KNOWN_LIMITATIONS.md` (P5-SEC-META3-001, P5-SEC-BENIGN-CORPUS-001) | — | Relevant entries complete | Resolved-status honored; benign corpus NOT reopened |
| `config/spine_surfaces.yaml` | 410 | Security surfaces read | BR coverage mechanics |
| `config/portal.yaml` | 2068 | Security workspaces + MCP fleet read | Wiring + roster config |
| `config/backends.yaml` | 905 | Structure + security groups read | Fleet/registry mechanics |
| `config/security_corpus.yaml` | 71 | Complete | Label-blind corpus contract |
| `config/lab_targets.yaml` | — | Read | Lab host truth |
| `.env.example` | — | Security/lab/Splunk vars read | Config surface |
| `portal_wiki/canonical/unit-surface-sec-core.md` + `unit-surface-investigation.md` + adjacent | — | Read | Spine reality |
| `scripts/validation/{registry,validate_system,blue_orchestration,security_bench,wiki}.py` | — | Check implementations for BQ/AZ/BM/BL/BN/BR/AW/BS/AL read | Live gates |
| `docs/security/corpus_injection.md`, `docs/AGENT_LOOP.md`, `docs/LAB_SETUP.md` | — | Skimmed for relevance | Context |

Historical `coding_task/` security build programs (V1–V5 blue orchestration,
RBP_02/03, SEC maturation) were consulted for intent where cited by code
comments (`BUILD_PROGRAM_SEC_RBP_V1` phases, `DESIGN_SEC_BLUE_ORCHESTRATION_V1/V2`,
`DESIGN_EMERGENT_LAB_AGENT_V2`).

---

## 4. Major source areas read

`portal/modules/security/core/` (70 .py files): the RBP engine. Personally read
in full or in load-bearing part: `episode.py`, `multichain.py`, `growth_loop.py`,
`emergent_gaps.py`, `unknown_defense.py`, `council_agreement.py`, `loop.py`,
`field_journal.py`, `recall_attribution.py`, `capability_graph.py`,
`response_loop.py`, `analyst_verdict.py`, `playbooks.py`, `notify_scoreboard.py`,
`drift_gate.py`, `telemetry.py`, `continuous_eval.py` (head), `blue.py` (grounding,
unknown-defense wiring, purple scoring, telemetry shipping, evasion),
`blue_orchestrate.py` (dispatcher, council runner, similarity runner,
three-section loop), `agentic_blue_eval.py` (local Episode, load_episode),
`exec_chain.py` (SCENARIOS, `_run_chain_test`), `siem/spl_backend.py`
(query_episode), `siem/blue_triage.py`, `siem/spl_detections.py/.yaml`,
`investigation/{evidence,case_notebook,agents,bench_investigation}.py`,
`tools/security_mcp.py`, `capability/index.py` (journal prior score).

Platform: `portal/platform/inference/router/council.py` (full),
`router/handlers.py` (council wiring), `portal/platform/agent/{loop,decide}.py`
(heads), `portal/platform/inference/cli/models.py` (import-gguf, pull,
apply-params), `portal/modules/research/tools/rag_mcp.py` (full read of ingest/
search/versioning), embedding server `scripts/embedding-server.py` (head),
`reranker_mcp.py` (via manifest + agent read).

Ops: `execute_local_sec_bench.sh`, `scripts/bench_supervisor.py` (via agent),
`scripts/security_capture_recipes.py` (via agent + spot), `.pre-commit-config.yaml`.

---

## 5. Current Portal architecture (as verified)

Portal 5 is an Open WebUI enhancement layer: OWUI :8080 → Portal Pipeline :9099 →
Ollama :11434 (sole chat tier, host-native on M4 Pro 64GB) → local GGUF models.
MCP fleet :8910–8932 provides tools as independent services (Rule 3). MLX remains
for speech/transcription/embedding-adjacent services — **verified nuance**: the
:8917 embedding service is actually `scripts/embedding-server.py`, a CPU-pinned
sentence-transformers (`microsoft/harrier-oss-v1-0.6b`) FastAPI server, not MLX;
only the :8925 reranker (`mlx-community/Qwen3-Reranker-0.6B-mxfp8`) is MLX.
Config flows `config/portal.yaml` → `./launch.sh sync-config` → derived
`backends.yaml workspace_routing`, `.mcp.json`, OWUI workspace imports (Rule 6 —
never hand-edit derived files).

Knowledge infrastructure at HEAD:

- **RAG MCP :8921** (`rag_mcp.py`): LanceDB at `PORTAL5_LANCE_DIR`
  (`/Volumes/data01/portal5_lance`), per-KB tables, directory ingest, chunk
  1000/150, two-stage vector→rerank retrieval, LanceDB time-travel
  (`kb_versions`/`kb_restore`). PRODUCTION_WIRED (compose, no profile gate).
- **Memory MCP :8920**: second LanceDB store, hybrid recall (vector + recency +
  tags). PRODUCTION_WIRED.
- **Wiki :8931**: git-backed canonical fact-units + `provenance_ledger.jsonl` +
  writeback adapters. The doc spine — design facts, not runtime knowledge.

Validation: 74 lettered checks registered in `scripts/validation/` (CLAUDE.md
prose says 72 — stale); all run **pre-push** (~60s) per `.pre-commit-config.yaml`;
pre-commit runs ruff + unit tests + portal-config-validate.

Model lifecycle: `portal models pull` / `import-gguf` (tempfile Modelfile
`FROM <gguf>` + `ollama create`, `cli/models.py:217-259`) / `apply-params`
(ctx-tagged derived models, writes model_hints back into portal.yaml) → bench →
`config/PENDING_MODEL_VERDICTS.md` → operator verdict →
`scripts/execute_pending_verdicts.py`. **No training code exists anywhere**
(repo-wide search: no `mlx_lm.lora`, no LoRA/SFT pipeline, no training deps in
pyproject; only inference-time LoRA *assets* in ComfyUI and retired MLX-serving
scripts in `scripts/_archive/`). VERIFIED FACT.

---

## 6. Current Red architecture (traced end-to-end)

**Entry points.** All red execution is synchronous and request/CLI-scoped:

1. Bench CLI `python3 -m portal.modules.security.core` (alias `portal security`):
   `--chain-models` (red-only), `--purple` (red+blue), `--evasion`,
   `--defense-efficacy`, `--exec-eval`, `--step-models`, `candidate-eval`,
   `loop run --lab-exec`, `goal emergent` (CONFIG_GATED `PORTAL_EMERGENT=1`,
   `objective_entry.py:23,38`). Driven by operators via
   `execute_local_sec_bench.sh` → `scripts/bench_supervisor.py`. BENCH_ONLY.
2. Production pipeline workspaces `auto-security::pentest` /
   `purpleteam-exec` (`config/portal.yaml:548-566,668-712`) — a user's
   `execute_bash` lands in the same attack image via sandbox MCP :8914.
   PRODUCTION_WIRED but CONFIG_GATED on `SANDBOX_LAB_EXEC=true` +
   `SANDBOX_LAB_IMAGE=portal5-attack:latest`.
3. Deterministic recipes: `scripts/security_capture_recipes.py` — model-free
   attack execution + telemetry ship. BENCH_ONLY (operator script).

No scheduler, daemon, cron, or MCP tool executes red. VERIFIED.

**`red_order`** is a per-scenario authored list of expected tool names in
`exec_chain.py::SCENARIOS` (`:221+`), loaded onto `BenchConfig` as
`chain_expected_order` (`_config.py::set_scenario`). It is both script (embedded
in `red_prompt`) and scoring ruler (LCS order-accuracy). Execution is
`_run_chain_test` (`exec_chain.py:3564+`): a bounded multi-turn tool-call loop
(`len(red_order)*2` or 20 for objective scenarios), dispatching each model tool
call to `lab.lab_dispatch` when live, else synthetic.

**Lab execution.** `lab.py::_lab_dispatch_inner` maps tool names to real commands
(impacket/nxc/nmap/curl chains) executed via MCP bridges: sandbox :8914
(`execute_bash` inside the `portal5-attack` Kali image in DinD — built from
`Dockerfile.attack`, self-verified against `config/attack_image_contract.json`)
and Proxmox MCP :8927 (VM lifecycle, snapshot allowlist). Scope guard:
`perception.py` `LAB_CIDR=10.10.11.0/24`, `assert_in_lab` raises outside it.
Hard gate `verify_lab_targets_reachable` aborts runs when the lab is down
(override `--force-unreachable-lab`); per-scenario readiness via
`scripts/lab_targets.ensure_target_ready`; failures score `indeterminate`,
never red-fail (`classify_scenario_result`).

**Telemetry landing.** `blue.py::collect_and_ship_scenario_telemetry`
(`:1710-1912`): collects Windows events via WinRM / LXC logs (`siem/collect.py`),
builds a **counterfactual** plane from red's command ledger (retained, never
shipped), saves captures to `results/captures/` (`capture_store.save_capture`
with validity gate), ships to Splunk HEC index `portal5_lab` with indexed
`episode_id` + `evidence_origin` fields (`hec_ship.ship_batch`), confirms
indexing (`index_wait.wait_indexed`). Episode-scoped PCAP via
`siem/network_capture.py`. Failures degrade honestly: `TELEMETRY_*` reason codes
→ Episode verdict `INDETERMINATE`.

**Episode production + consumption.** `episode.py::Episode` — reason-coded axes
(red/telemetry/detection/response) + `evidence_refs`; `derive_verdict` is pure
code (synthetic never PROVEN). Persisted: embedded in purple result JSON,
`save_evidence("red"|"purple")` under `results/captures/`, and the wiki
`provenance_ledger`. Consumed by `_score_purple` → capability graph update →
compliance report; replayed by `load_latest_red_capture` /
`agentic_blue_eval.load_episode` (its own local Episode dataclass — **two
Episode shapes coexist**, reconciled in the final design).

**Directed execution knobs that exist today:** scenario selection only, plus:
`--dynamic-cve` (model-researched CVEs), `--judgment` (decoy-host scope
discipline), `--evasion` (blue detections fed back as red adaptation directive),
`--step-models`/`--chain-dag` (per-step model assignment),
`exec_sequences.json` `fallback_techniques` (sub-technique alternates surfaced to
the model on round ≥2), playbooks (`loop run`), objective classes
(`goal emergent`). **No mutation/variant/parameter-sweep framework exists** —
VERIFIED by direct search + read.

**Boundary evaluation:** the design boundary — *Red is the means; the bully
directs what Red runs but never rewrites Red execution* — is **confirmed
correct**. Red already exposes exactly the direction surface a mutation director
needs (scenario overlay + prompt parameters + evasion directive + fallback
techniques) without touching execution. MUT builds on that surface.

---

## 7. Current Blue/Purple architecture (traced end-to-end)

**Entry points.** Everything funnels through the bench CLI: `--blue-models`
(detection chain), `--purple`, `--blue-mode orchestrated|2-section|council|
multichain` (require `--replay-captured-red`), `agentic_blue_eval.py`'s own main
(+ `_sweep_driver.py`). Nothing in the serving path (pipeline, MCP, OWUI, launchd)
triggers blue analysis autonomously. The `blueteam-orchestrated` and
`blueteam-council` workspace variants hold model rosters and are
`expose_to_owui: false` (`config/portal.yaml:700-747`). BENCH_ONLY, VERIFIED.

**Flow.** `run_purple_tests` (`blue.py:1941-2179`): per red model — mint
episode, network capture, `_run_chain_test`, ship telemetry, save evidence; per
blue model — `_run_blue_chain_test` (tool loop with `query_windows_events`/
`query_splunk`/`report_detection`/`recommend_containment`, pipeline-routed by
default), then `_score_purple` (`:1519+`) builds the Episode and derives truth.
`_run_unknown_defense` (`blue.py:1450-1513`) adds U1 similarity (observed
features vs MITRE catalog + wiki overlay), U3/U4 anomaly (**dormant** —
`results/baselines/` has no baselines; reported honestly as `no-baseline`),
U2 bridge into `investigation.agents.InvestigationGraph` on SIMILAR/anomaly.

`blue_orchestrate.run_blue_orchestration` (`:1537-1627`) dispatches three shapes:
3-section (Retriever `run_tool_model` → Hunter `run_reasoning_model` loop with
history caps, stall handoff at 3 no-hypothesis rounds, mentor at 2, budgets
per-role → Expert `run_expert_model` terminal verdict), 2-section ablation arm,
council roster (`_run_council:2533` — one shared lead-hunter evidence gather via
`capture_expert_handoff`, then N members independently conclude from the SAME
pool, `compute_agreement`, optional fed arbiter). Grounding: `_cite_or_drop`
(label-blind since 2026-07-23; fabricated-citation history documented inline),
`_discriminator_contradicts` (sibling sub-technique contradiction via
`discriminator_tokens`/`sibling_ids`, label-blind).

**Scoring.** `scoring.py` pure scorers (detection tiered recall, chain coherence,
scope discipline, pivot correctness, argument adaptation); `toolcall_reliability`
hard gate (valid_rate ≥ 0.70, spiral ≤ 0.10); `notify_scoreboard` (eval-only):
`NOTIFY_VERDICTS = {CONFIRMED, ANOMALOUS_UNCLASSIFIED}` (`:21`) — anomaly is a
full catch; trust ordering `CONFIRMED_CORRECT(3) > HONEST_ANOMALY(2) >
SILENCE_ON_PRESENT(1) > CONFIRMED_WRONG(0)`; benign false-flags typed
(`CONFIRMED_ON_BENIGN` vs `ANOMALY_ON_BENIGN`) for alert-fatigue measurement (BQ).

**Council.** Security council = `council_agreement.compute_agreement` adapter
over platform `aggregate_opinions`; fail-safe (zero participation →
ANOMALOUS_UNCLASSIFIED + arbiter; split → disagreement-as-novelty; RULED_OUT
needs unanimity). Platform council is production-wired for council workspaces
(`router/handlers.py:41-42,579,590`).

**Persistent state today:** `results/` JSON per run; `results/captures/`;
`results/checkpoints/`; `field_journal/*.json` (in-git; keyword recall);
`results/baselines/` (empty); wiki units + provenance ledger; LanceDB volumes.
**No cross-run state changes what the next blue run does** — VERIFIED: verdict
paths never read prior-run state; the capability graph rebuilds per invocation;
`continuous_eval.py` and `response_loop.py` are test-only libraries;
`growth_loop.run_growth_loop` has no CLI wrapper (test-only) and its
`prove_draft` legs are placeholder-true (`growth_loop.py:209,215,221`).

**Historical conclusion re-evaluation:** the handoff's "current B/P is largely a
benchmark/evaluation architecture" is **CONFIRMED at HEAD**, with one
softening: the fail-safe consolidation philosophy (escalate-not-dismiss) and the
label-blind grounding gates have already moved the verdict *semantics* toward
the concept; what is missing is not honesty plumbing but the **compounding
organism** — persistent hunt state, pre-hunt recall that changes behavior,
semantic cousin distance, real proof gates, and the hunt driver.

---

## 8. Runtime wiring and call paths (classification summary)

Full per-surface tables were built during the trace; the load-bearing
classifications:

| Surface | Classification | Evidence |
|---|---|---|
| `exec_chain._run_chain_test` / `run_chain_tests` | BENCH_ONLY (CONFIG_GATED live via `SANDBOX_LAB_EXEC`) | `exec_chain.py:3564,3904`; CLI `commands/blue_modes.py:791-1012` |
| `lab.lab_dispatch` | PRODUCTION_WIRED primitive (bench + pipeline share sandbox :8914) | `lab.py:1010-1039`; `code_sandbox_mcp.py:154-158` |
| `blue.run_purple_tests` / `run_blue_chain_tests` | BENCH_ONLY | `blue.py:1941,1342`; callers `blue_modes.py:1080`, `cli.py:892-895` |
| `blue_orchestrate.run_blue_orchestration` | BENCH_ONLY (+ validation + tests) | `blue_orchestrate.py:1537`; `blue_modes.py:127,210,330`; corpus benches |
| `blue_orchestrate` section runners (tool/reasoning/expert/mentor) | INDIRECTLY_WIRED (via bench only) — **reusable arm** | `blue_orchestrate.py:496,662,1098,1263` |
| `council_agreement.compute_agreement` | BENCH_ONLY adapter over platform primitive | `council_agreement.py:69`; caller `blue_orchestrate.py:2650` |
| platform `council.run_council_review` | PRODUCTION_WIRED (council workspaces) | `router/handlers.py:579,590` |
| `loop.run_engagement` / `resume_engagement` | PARTIALLY_WIRED (operator CLI; no scheduler) | `loop.py:176,652`; `loop_cli.py` |
| `growth_loop` | LIBRARY_ONLY (test-only; placeholder gates) | `growth_loop.py:252,209` |
| `continuous_eval`, `response_loop` | LIBRARY_ONLY / TEST_ONLY | test-only callers |
| `emergent_gaps` | LIBRARY_ONLY feed (test callers) — cousin-generator embryo | `emergent_gaps.py:68-80` |
| `unknown_defense` U1 | INDIRECTLY_WIRED in purple (flags only) | `blue.py:1450`; `unknown_defense.py:76-154` |
| `drift_gate` | PRODUCTION-WIRED-ish (CLI `drift-check`; validation AN) — metric drift | `drift_gate.py:1-60`; `drift_cli.py` |
| `blue_triage` | PRODUCTION-WIRED lane (env-gated Splunk poll → pipeline enrich) | `siem/blue_triage.py:1-60` |
| `rag_mcp` kb_ingest/kb_search | PRODUCTION_WIRED (doc KBs) | `rag_mcp.py:215,411` |
| `investigation.EvidenceStore` | TEST_ONLY (in-memory) | `evidence.py:118`; callers bench_investigation+tests |
| `investigation.CaseNotebook` | TEST_ONLY (SQLite :memory:) | `case_notebook.py:53` |
| `field_journal` | PARTIALLY_WIRED (writes from loop/blue_modes; behavior read only in `capability/index.py`) | `field_journal.py:95`; `loop.py:205` |
| `capability_graph` | LIBRARY_ONLY ephemeral (rebuilt per invocation) | `capability_graph.py:251-315` |
| `models.py import-gguf` | PRODUCTION_WIRED operator CLI | `cli/models.py:217-259` |
| Training toolchain | **ABSENT** | repo-wide search; pyproject |

---

## 9. Original Bully principles (mechanical reading of the concept)

From `BULLY_CONCEPT_SOURCE.md` (read completely), the mechanism underneath each
feature:

| Concept element | What happens | Why it works | General principle | Defensive analogue |
|---|---|---|---|---|
| Hallucination bin | Findings enter `hallucinations/`, promoted through G0 compile → G1 clean-VM repro → G2 exploitable → G3 low-priv | LLM output is confident nonsense often enough that trust must be earned; "6/6 early findings disproven dynamically" | **Suspect-until-proven; proof is executable, not rhetorical** | Alert bin: a detection finding starts as a suspect and earns promotion through evidence gates |
| Grammar fuzzing | Structurally *valid* files with adversarial field values reach parsers; random bytes get "invalid format" | Validity is what exercises deep code paths | **Adversarial variation within structural validity** | Atomic mutation: valid TTPs with perturbed params/timing/artifacts — noise is dropped by the sensor pipeline, valid variants expose cousin gaps |
| Campaign knowledge loop | Pre-hunt RAG query ("seen this binary? what worked? what blocked us?"); post-hunt record; FAISS auto-index | Prevents the most expensive mistake: re-running the same campaign for the same nothing | **Mandatory recall before action; universal capture after** | Pre-hunt organ recall enforced in code; universal indexing of every emission, positive and negative |
| Known-defence DB | AM-PPL/SxS/signature-validation outcomes recorded; multiplicative priority penalty | Dead ends cost the most; negatives compound | **Negative results are first-class state that steers** | Known-benefit/known-benign/known-covered/known-defense DB multiplicatively steers target selection |
| ROI target selection | Conservative payout / hunt-hours; competition multiplier | Gravitates to under-scrutinized high-value targets | **Expected value per unit cost, pessimistically estimated** | Risk-reduction per hunt-cost, pessimistically estimated, steers to the biggest blind spot |
| Low-priv gate | SYSTEM-only findings are worthless | Consumer context defines value | **Validate in the consumer's context** | SOC-analyst-context gate: a finding invisible in the real console under queue load is not promotable |
| Variant analysis | Found one bug → hunt its cousins (TIFF OOM → SFNT OOM) | Weaknesses come in families | **Discovery is directional, not point-wise** | Cousin engine: same/similar/new/different against embedded hunt memory |
| Coverage plateau | Stop when new signal stops; record it | Grinding an exhausted neighborhood burns budget | **Marginal discovery rate governs stopping** | Plateau on gap-classification deltas + cost-per-cousin trend |
| Cost tracking (TokenBurn) | Cost-per-finding trend matters more than any number | Compounding must be economic as well as technical | **Measure the economics of learning** | Cost ledger per hunt; cost-per-promoted-cousin tracked and shown falling |
| Thin MCP / thick logic | Servers are `@mcp.tool()` wrappers; logic in modules | Testable, tunable, model-independent | **Tools are transport; intelligence is code** | All bully logic in security-core modules; MCP surface unchanged |
| Per-campaign CLAUDE.md | Campaign-specific tuned instructions, refined each run | Small models perform inside narrow shapes | **Learned operating instructions per campaign class** | Per-scenario-class playbook memory shaping fleet models |
| Self-bullying | "Me bullying it → it bullying itself" | Adversarial self-review catches hallucination pre-submission | **Falsification before promotion** | Fleet council tasked to *disprove* findings; unrebutted objection blocks |
| Human at consequential points | Vendor submissions stay human-gated | Trust boundary | **Operator confirms consequential action** | PROMOTE_POLICY=confirm on findings, detections, models, playbooks, roster |
| Local-model offloading + own training | Offset work to local models; training a research-focused model | Cost + specialization | **The fleet sharpens on its own history** | HARV → TRAIN → bench-gate → serve cousin-specialists |

Every principle has a defensive home. The prior design's mapping survives; the
review's job was checking whether Portal's current code *embodies* any of it —
mostly it does not (storage without retrieval-impact; gates without execution;
council without objection-gating), which is exactly the build surface.

---

## 10. The 15-point translation review

Fidelity scale: STRONG / STRONG_WITH_REFINEMENT / PARTIAL / SURFACE_ONLY /
MIS-TRANSLATED / MISSING / SUPERSEDED_BY_BETTER_PORTAL_CAPABILITY.

| # | Offensive primitive | Principle | Existing translation | Portal capability (verified) | Fidelity | Final recommended translation |
|---|---|---|---|---|---|---|
| 1 | Hunt a binary for a bug | Directed coverage probing | Hunt a (TTP × log-source × detection) cell — LOOP+TGT | Capability graph defines cells; no hunt driver | STRONG | Keep. LOOP consumes Episode; TGT ranks cells |
| 2 | Finding = working 0-day PoC | Proof-bearing discovery | Finding = missed/near-missed detection — BIN+BR | RED_ONLY gaps + emergent_gaps already represent "landed, undetected" | STRONG | Keep. Finding = cousin-graded detection gap with evidence |
| 3 | Hallucination bin G0–G3 | Suspect-until-proven | Alert bin G0 evidence → G1 replay → G2 not-benign → G3 analyst-visible | growth_loop gates placeholder-true; multichain already escalate-default | STRONG_WITH_REFINEMENT | Keep gates; real G1 (static replay + dynamic re-execution), G2 via benign corpus + verdict contracts, G3 **measured via blue_triage lane**; suspect-by-default at the *finding* level |
| 4 | Known-defence DB | Negative steering | Known-defence/benign/covered DB — SUB+TGT | No persistent store exists (capability_graph ephemeral) | STRONG (concept) / MISSING (impl) | Keep translation; SUB owns it; multiplicative penalties in TGT |
| 5 | ROI bounty ranking | Expected value steering | Risk-reduction/cost — TGT | Nothing exists | STRONG | Keep; cost model from bench stats + lab actions |
| 6 | Low-priv gate | Consumer-context value | SOC-analyst-context gate — BIN G3 | `blue_triage.py` lane exists | SUPERSEDED_BY_BETTER_PORTAL_CAPABILITY | G3 measured through the real Splunk→triage lane under queue load, not asserted |
| 7 | Bounty submission exit | Actionable handoff | Detection-engineering handoff — HND | `response_loop` draft shapes; `spl_detections.yaml` structure; purpleteam chains produce Sigma/SPL prose | STRONG_WITH_REFINEMENT | HND emits family-generalizing detection package + regression recipe (capture_recipes) + FP analysis (benign corpus) + ATT&CK delta; operator confirms |
| 8 | Grammar fuzzing | Structural validity + adversarial variation | Atomic mutation — MUT | emergent_gaps + **evasion feedback loop** + **capture_recipes** + `exec_sequences.json` fallback_techniques | STRONG_WITH_REFINEMENT | MUT = mutation spec → scenario overlay directing red within a code-enforced budget; three existing seeds wired in |
| 9 | Personal FAISS queried inline | Semantic memory | Hunt-knowledge organ — ORG | rag_mcp infra (LanceDB+8917+8925) but document-oriented, no distances | STRONG_WITH_REFINEMENT | ORG = security-side organ module on the same infra; record-level, distance-returning, provenance-tagged; mandatory pre-hunt recall enforced in LOOP code |
| 10 | One model bullying itself | Self-falsification | Fleet council bullying — HEART | Platform council isolation + roster math; objections carried but discarded; security adapter drops them entirely | STRONG_WITH_REFINEMENT | HEART: seats tasked to falsify; **objection-presence gate** in code; rebuttal round; quorum kept as participation floor only (BL) |
| 11 | Fine-tune own hunts | Fleet sharpening | HARV+TRAIN | Feed leg (kb_ingest-class infra) + redeploy leg (`models.py import-gguf`) + acceptance bench exist; **TRAIN absent** | STRONG | Keep; TRAIN installs `mlx_lm` LoRA toolchain host-native; bench gates base-vs-trained |
| 12 | Variant analysis | Family hunting | Spatial + temporal cousins — BR-COUSIN + BR-DRIFT | unknown_defense U1 (lexical), drift_gate (metric drift) | STRONG_WITH_REFINEMENT | BR-COUSIN composite multi-dimensional distance on ORG; BR-DRIFT retargets drift_gate machinery to detection-firing signals |
| 13 | Knowledge loop | Compounding memory | Same, tool-enforced; universal indexing — ORG invariant | Nothing enforces recall/index today | STRONG | Keep as hard invariant: LOOP code calls recall before direction and indexes after, unconditionally |
| 14 | Coverage plateau | Marginal-value stopping | PLT | Nothing exists; capability_graph is ephemeral | STRONG | PLT on rolling marginal cousin-discovery rate + known-state saturation + cost-per-cousin trend |
| 15 | Per-campaign CLAUDE.md | Learned operating shapes | Playbook memory — PLAY | `playbooks.py` static YAML pattern; field_journal reusable patterns | STRONG_WITH_REFINEMENT | PLAY = learned, versioned per-scenario-class instruction sets; drafted from hunt outcomes; operator-confirmed promotion; injected into hunt-loop model context |

No translation is MIS-TRANSLATED or SURFACE_ONLY at the concept level. The
dominant refinement theme: **Portal already owns primitives the design planned
to invent (triage lane, drift machinery, evasion feedback, deterministic
recipes), and lacks exactly the pieces the design must build precisely
(persistent substrate, semantic distance, real proof gates, objection gate,
training leg).**

---

## 11. Current reusable-asset inventory (verified)

| Asset | Location | Reuse value |
|---|---|---|
| Episode truth plane | `episode.py` (derive_verdict, reason codes) | The bully's input contract + code-decides substrate. REUSE unchanged |
| Episode-scoped label-blind query | `siem/spl_backend.py::query_episode` | Hunt investigation retrieval. REUSE |
| Telemetry ship + capture store + validity gate | `blue.py:1710-1912`, `siem/capture_store.py`, `hec_ship.py`, `index_wait.py`, `network_capture.py` | MUT/LOOP telemetry plane. REUSE |
| Grounding gates | `blue.py::_cite_or_drop` (831), `_discriminator_contradicts` (915) | Investigation-arm honesty. REUSE |
| Section machinery | `blue_orchestrate.py` runners + handoff capture + budgets + mentor | LOOP's investigation arm. REUSE (extracted from bench shell) |
| Council mechanics | platform `council.py` (isolation, parse, roster accounting, ESCALATE floors) | HEART base. REUSE; new aggregation |
| Verdict semantics | `analyst_verdict.py` (SectionOutput, match_grade/similar_to carry, ungrounded quarantine) | Cousin verdict carry. REUSE |
| Scoreboard semantics | `notify_scoreboard.py` (NOTIFY_VERDICTS, trust ranks, benign typing) | SCORE base. REUSE+EXTEND by distance |
| Honest-miss labeler | `recall_attribution.py` (label-blind evidence_presence; discriminators from SPL) | HARV eval-side labels. REUSE |
| Detection library | `siem/spl_detections.yaml` (+`spl_variants`, `distinguishing_features`) | Cousin explanation + HND generalization source. REUSE |
| Deterministic attack recipes | `capture_recipes.py` + `scripts/security_capture_recipes.py` | BIN G1b replay + HND regression tests. REUSE |
| Evasion feedback | `blue.py::_build_evasion_feedback`/`_run_evasion_purple` | MUT directive channel. REUSE |
| Emergent gap feed | `emergent_gaps.py` | MUT off-script cousin supply. REUSE |
| Drift machinery | `drift_gate.py` (rolling baseline, canary, scipy) | BR-DRIFT seed. RETROFIT signals |
| Triage lane | `siem/blue_triage.py` | BIN G3 measurement. REUSE |
| LanceDB + embed/rerank services | rag_mcp infra, :8917/:8925 | ORG substrate. REUSE infra (new module) |
| EvidenceRecord schema / CaseNotebook pattern | `investigation/evidence.py`, `case_notebook.py` | SUB record schema + supersede pattern. EXTRACT |
| Growth-loop draft shapes | `growth_loop.py` (DraftDetection, ProofResult, surface_for_confirm) | BIN detection-draft shape. EXTRACT; gates REPLACED |
| Response primitives | `response_loop.py::RESPONSE_PRIMITIVES` + technique map | HND IR implications seed. EXTRACT |
| Playbook YAML pattern | `playbooks.py` + `playbooks/security/` | PLAY container format. RETROFIT to learned memory |
| Field journal patterns | `field_journal.py` (reusable/pitfalls extraction) | PLAY/HARV source. REUSE as input; superseded as store |
| Model redeploy | `cli/models.py import-gguf`, `apply-params` | TRAIN redeploy leg. REUSE |
| Candidate gate | `candidate_eval.py` (6-scenario delta vs incumbent), `intake.py` (TPS/tools gates), PENDING_MODEL_VERDICTS flow | TRAIN acceptance. REPOSITION as model-acceptance gate |
| Platform agent primitives | `portal/platform/agent/{loop,decide,rank,goal}` | Evaluated for LOOP — **rejected as base** (see §16); discipline (caps, honest-BLOCKED) mirrored |
| Lab scope guard | `perception.py` (LAB_CIDR, assert_in_lab) | MUT budget/scope enforcement. REUSE |
| Provenance ledger | `portal/platform/wiki/provenance_ledger.py` | Promotion audit trail. REUSE |

---

## 12. Cousin-model analysis (task §H)

**What makes attack B a cousin of attack A — the reviewed answer.**

Embedding similarity alone is insufficient (semantic text distance conflates
description similarity with behavioral similarity; U1's history proves lexical
approaches silently zero out). ATT&CK ID equality alone is insufficient (same
technique, different telemetry shape, is exactly the cousin that escapes a
signature). The review's conclusion, carried into the design:

A cousin relationship is **multi-dimensional with vetoes**, computed over a
canonical **hunt record** (not free text):

```text
hunt_record = {
  technique_context:  candidate ATT&CK IDs + tactic (may be empty pre-grading),
  telemetry_signature: sourcetypes + field-name histogram of observed events,
  behavior_sequence:  ordered list of step kinds (recon→exploit→persist→…),
  artifacts:          tools, hashes, paths, accounts, hosts, protocols,
  detection_response: per-detection outcome vector (fired/weak/absent),
  outcome:            verdict + episode refs,
}
```

Dimensions (each must earn its place — measurable value stated):

| Dim | Measure | Why it earns its place |
|---|---|---|
| D1 semantic | cosine distance over organ embeddings of the record's narrative+fields | Catches "same shape, different vocabulary" — the thing lexical U1 missed |
| D2 ATT&CK graph | 0 same technique; sibling sub-technique; same tactic; cross-tactic (from `sibling_ids` + tactic structure) | Deterministic family structure; the "cousin" claim's backbone |
| D3 telemetry shape | field-signature Jaccard + sourcetype overlap | A detection fires on fields; same-technique/different-fields is the escape case |
| D4 behavioral sequence | normalized edit distance over step-kind sequences | Ordering distinguishes attack pattern from shared tooling |
| D5 detection response | distance over per-detection outcome vectors | The defensive question is differential: does our coverage transfer? |

Excluded after evaluation: timing (noisy in a lab), identity/host context
(lab-small), protocol (subsumed by D3), confidence (a gate input, not a
distance), baseline deviation (belongs to the *temporal* surface), temporal
evolution (same). Each was tested against "does it change a grading decision on
the known corpus?" — the kept five do.

**Grading semantics (deterministic, config-thresholded, per-dimension
decomposed):**

- **SAME**: D2 = 0 ∧ discriminators match (spl_detections distinguishing
  tokens present) ∧ D1 ≤ τ_same. Veto: any discriminator contradiction → not SAME.
- **SIMILAR**: composite ≤ τ_similar ∧ at least one of D2 ∈ {sibling, same
  tactic} or D3 ≥ τ_fields. The "variant" band.
- **NEW**: τ_similar < composite ≤ τ_new ∧ tactic-family related. Genuinely new
  but neighborhood-anchored.
- **DIFFERENT**: composite > τ_new. Not a cousin; not interesting.
- **ANOMALOUS_UNCLASSIFIED**: not SAME/SIMILAR to any *covered* known ∧ detection
  response blind (no rule fired) ∧ anomaly evidence present (D3/D4 deviation
  from known-benign shapes). **The product.**

Human explanation: every grading emits its per-dimension decomposition plus the
feature-overlap citation layer (U1's preserved value: embedding *finds*,
feature overlap *explains*), so an analyst sees "0.82 composite: same tactic
(D2), shared fields {EventCode, TargetUserName} (D3), reordered persistence
before lateral (D4), no rule fired (D5=blind)".

Meaningful novelty vs arbitrary semantic distance: novelty requires D5 blindness
+ D3/D4 structural deviation, not merely D1 distance. This is the anti-"embedding
astrology" control.

## 13. Spatial-cousin analysis

Spatial cousin = near-neighbor attack behavior structurally related to known
behavior but escaping existing coverage. Representation: hunt records embedded
in ORG; neighborhoods = k-NN around known-bad records, bounded by composite
distance. Discovery mechanism: MUT manufactures structured variants around a
chosen known; BR-COUSIN grades each manufactured episode against the
neighborhood; SIMILAR-with-D5-blind or ANOMALOUS_UNCLASSIFIED = a discovered
cousin. The neighborhood map (which cells resolved, which open) persists in SUB
— that is what makes the *next* hunt start smarter.

## 14. Temporal-cousin analysis

Temporal cousin = a technique/detection relationship that drifts from its own
baseline until the detection is effectively a stranger to the technique (the
"N-1" idea defensively: yesterday's detection vs today's behavior).

Verified seed: `drift_gate.py` — rolling-window statistics + canary + scipy,
today over bench metrics (`blue_f1`, `detection_coverage`, …) as flags-never-
verdicts. The final design retargets the machinery to per-detection baselines
persisted in SUB:

- fire-rate vs baseline; hit latency (event→index→alert); row-shape (fields
  returned); partial-satisfaction (which SPL clauses still match); telemetry
  completeness (sourcetype loss).

Drift classification (the four-way the task demands): **telemetry failure**
(sourcetype volume collapse) vs **environmental change** (host/baseline
population shift) vs **detection degradation** (rule still runs, weaker/partial
matches) vs **attacker evolution** (behavior sequence/fields shifted while
technique persists — the temporal cousin, routed to BR-COUSIN as a spatial
grading input). Only the last is a cousin; the rest are ops signals.

## 15. Alert-bin analysis (task §O)

Gates reviewed: G0 evidence-exists, G1 replay-reproduces, G2 not-benign,
G3 analyst-visible. Verdict: **keep all four; sharpen G1 and G3; insert the
council between G2 and G3; operator confirm last.**

- G0 — evidence exists: deterministic; observed-origin evidence only
  (`telemetry.py::OBSERVED_EVIDENCE_ORIGINS`); counterfactual/synthetic
  evidence cannot pass. Already enforceable with existing origin plumbing.
- G1 — replay/reproduction, split into sub-gates:
  - **G1a static**: the candidate signature fires on the *replayed* capture
    (capture_store replay + SPL execution) — signature-only proof.
  - **G1b dynamic**: re-execution reproduces the behavior chain + expected
    artifacts. Engine: `capture_recipes.py` (deterministic) or directed red
    re-run; artifacts verified via telemetry contracts + oracles. **A
    signature hit alone never promotes** — static+dynamic pairing is the gate.
- G2 — not-benign: two instruments: (a) the verdict-contract counter-evidence
  discipline already in `blue_orchestrate._VERDICT_GROUNDING_POLICY`
  (dual-use primitive ≠ malicious); (b) regression against the benign corpus
  (`benign_corpus_bench.py`) — the candidate's discriminators must not fire on
  benign cells. Preserves BQ. P5-SEC-BENIGN-CORPUS-001 stays resolved — G2 is
  its concept-native home, as the handoff instructed.
- HEART (falsification) sits here: cheap deterministic gates first, adversarial
  model review before the expensive analyst-context gate.
- G3 — analyst-visible: **measured, not asserted**: ship the candidate as a
  Splunk notable (HEC, `evidence_origin=observed`), run the `blue_triage` lane
  against it under a queue-load corpus (seeded benign + concurrent alert
  volume), pass iff the lane produces a triage report at or above the
  configured priority (P≤2 default) within the configured SLA. A finding only
  the harness can see fails — the low-priv lesson, defensive.

Promotion state machine (BIN owns it): `SUSPECT → G0 → G1a → G1b → G2 →
COUNCIL(HEART) → G3 → PENDING_OPERATOR → PROMOTED | KILLED`. Killed cousins are
recorded to SUB+ORG with kill rationale (negative learning). Suspect-by-default
lives here — at the finding level — which is why the (already fail-safe)
multichain consolidation does not need the BIN2 surgery the prior design
assumed.

## 16. Council analysis (task §N)

Platform `council.py` verified: isolated reviewers (never see each other),
strict JSON contract with `strongest_objection`/`missing_evidence`/
`conditions_to_change`, code-side participation/quorum over the full roster
(non-voters never shrink the denominator), ESCALATE on sub-floor or no-quorum,
synthesizer may explain but never change the code decision, fallback markdown
preserves objections/dissent. Production-wired for council workspaces.

The gap to the concept is precise: (1) seats are generic reviewers, not
**tasked falsifiers**; (2) `aggregate_opinions` reduces to vote-counts —
objections are rendered, never **gated on**; (3) the security adapter
(`council_agreement._platform_opinions:44-66`) constructs bare
SUPPORT/REJECT/ABSTAIN opinions and never even populates the objection fields.

HEART therefore: seats receive the candidate cousin + evidence pack and are
tasked to **break it** (strongest case it is benign / already-covered /
hallucinated, with cited evidence). Code gate: a *material* objection —
deterministic criteria: cites a specific evidence contradiction, an
already-covered detection ID, or a benign-context indicator from the verdict
contract — that is **unrebutted** blocks promotion. Rebuttal: the promoting
chain answers with evidence; a falsification re-pass confirms resolution.
Quorum/participation remain as *floors* (BL honored: non-voters count against
the roster); they are not the decision. Dissent is always persisted to the
decision record (minority views never dropped — `_fallback_markdown` already
models this preservation).

ROSTER review: config rosters exist (`blueteam-council`, `auto-council`).
Anti-monoculture rules adopted into the design: ≤1 seat per model family per
roster (config-enforced); retrospective weights bounded [0.5, 2.0], recomputed
from objection-validity + cousin-call correctness; weights influence seat
selection order and advisory aggregates only — **never the objection gate** (the
weakest seat's material objection still blocks); abstentions count against
participation; all weight changes are decision-logged and operator-visible.

## 17. Knowledge/compounding analysis + the six feeds (task §L)

Current state: storage exists (results JSON, captures, field journal, wiki,
LanceDB) but **no retrieve→decide→change chain** closes anywhere in the
security arm. The learning chain is broken at *retrieval* (nothing queries
prior state pre-run) and *decision impact* (the one behavior-changing read is
capability ranking by journal hit-count).

The final design's six feeds, each with the full loop spelled out and a
**measurable changed-behavior instrument** (details in DESIGN doc §Six feeds):

1. **Semantic hunt memory (ORG)** — source: every hunt emission; capture:
   universal indexing invariant; validation: record schema gate; persistence:
   LanceDB `hunt_memory`; retrieval: mandatory pre-hunt recall (LOOP code);
   decision impact: TGT ranking + BR-COUSIN grading; instrument: recall-hit
   utilization + neighborhood reuse rate across hunts.
2. **Known-state DB (SUB)** — source: hunt outcomes (benign/covered/defense/
   dead-end); validation: outcome evidence refs required; retrieval: TGT
   multiplicative penalties; instrument: deprioritized-cell skip rate; waste
   rate (hunts into known-dead cells) trending to zero.
3. **ROI/target intelligence** — source: SUB cost ledger + cousin yield;
   retrieval: TGT score; instrument: cost-per-promoted-cousin trend (PLT).
4. **Training-pair harvest** — source: verdicts+rationales, council
   objection/rebuttal exchanges, cousin distance judgments; validation:
   schema + provenance + label-blind discipline (BM preserved —
   production grading never reads eval answer keys; eval-side honest-miss
   labels come from `recall_attribution`); persistence: versioned JSONL;
   retrieval: TRAIN; instrument: corpus growth + per-role coverage.
5. **Fleet-local fine-tune** — source: corpus; validation: bench gate
   (base vs retrieval-only vs playbook-only vs retrieval+playbook vs trained);
   persistence: GGUF + Ollama model + provenance; retrieval: hunt loop uses
   the served specialist; instrument: cousin-judgment bench delta + base-
   capability retention (catastrophic-forgetting control).
6. **Playbook memory** — source: successful hunt trajectories per scenario
   class; validation: playbook schema + operator confirm; persistence:
   versioned playbook records; retrieval: LOOP injects the class playbook into
   model context; instrument: budget consumption + time-to-conclusion for
   playbook-shaped vs unshaped hunts.

Cross-cutting answers: provenance = hunt_id/episode_id on every record;
negative observations = first-class records (kills, dead ends);
contradiction = supersede (CaseNotebook pattern) with reason codes, never
delete; aging/decay = recency-decayed retrieval boost + staleness flags on
known-state entries past a confidence half-life; poisoning resistance = organ
records are provenance-classed (`hunt-emission`, `operator-assertion`,
`external-intel`), retrieval filters by class, and low-authority classes can
never alone justify a SAME grading; retrieval evaluation = periodic
recall-precision probe against held-out hunts; deterministic enforcement =
LOOP code calls recall/index unconditionally — model discretion is not
involved.

## 18. Training-flywheel analysis (task §M)

Legs re-verified: FEED (organ/LanceDB infra) EXISTS; REDEPLOY
(`models.py import-gguf`) EXISTS; ACCEPT (bench harness + candidate_eval +
PENDING_MODEL_VERDICTS) EXISTS and is repositioned unchanged; HARVEST = build;
TRAIN = genuinely absent (VERIFIED: no `mlx_lm`, no LoRA/SFT code, no training
deps).

Design answers carried forward: corpus = role-tagged JSONL (hunter / analyst /
disprover / cousin-smeller) with evidence→verdict+rationale pairs, objection
exchanges, and distance judgments as first-class example types; provenance per
example (hunt_id, episode_id, model, distances, outcome); splits by hunt-date
with a scenario-family holdout; dataset versioning (content-hash + manifest);
model versioning (`<base>-cousin-<datasetver>`); reproducibility (seed, config,
dataset hash recorded); rollback (previous GGUF retained; `ollama create` of
prior tag); promotion criteria = beats incumbent on cousin-judgment bench ∧
no regression on the general security bench ∧ operator confirm;
catastrophic-forgetting control = the repositioned general bench is part of
the gate. Training survives **only on measurable gain** against the four
comparison arms (base / +retrieval / +playbook / +both).

## 19. Mutation analysis (task §P)

The concept's key insight — structural validity + adversarial variation —
translates to a **MutationSpec** consumed by Red's existing direction surface:
scenario overlay (variant of a base scenario), red_prompt parameter substitution
(timing, args, artifact choices), sub-technique adjacency from
`exec_sequences.json fallback_techniques` + `spl_detections.yaml sibling_ids`,
evasion directive channel (`_build_evasion_feedback` generalized: "these
detections fired; vary within validity"). Budget in code: max variants per
neighborhood per hunt, max perturbation distance, scope guard unchanged
(`perception.assert_in_lab`). Red execution code untouched — VERIFIED the
existing direction surface suffices (scenario red_order/red_prompt are data,
`_prepare_scenario` already substitutes target vars).

## 20. Targeting/ROI, plateau, cost (task §Q)

ROI score = expected gap-closure value / expected cost, with: cell criticality
(asset weight × technique severity), cousin novelty prior (distance
distribution of the neighborhood), prior miss rate, multiplicative known-state
penalties (benign/covered/defended/dead-end), historical yield; cost =
projected model-turns + lab-minutes + analyst-minutes from the SUB cost ledger.
Plateau: a neighborhood is exhausted when rolling marginal cousin-discovery
(SIMILAR+NEW+ANOMALOUS records per iteration) < floor for N consecutive
iterations AND known-state saturation > ceiling — *not* when embedding clusters
stop (cluster stability is explicitly rejected as the stop signal). Cost:
per-hunt token/wall-clock/lab-action/operator-minute ledger; headline metric =
cost per promoted cousin, tracked over hunt number; compounding claim is
falsifiable against it.

## 21. Detection-handoff analysis (task §R)

A promoted cousin exits through HND as a **family-generalizing package**:
generalized SPL (lifted from the cousin's discriminators to the family level)
+ Sigma rule + per-sourcetype variants (spl_variants pattern), required
telemetry contract, ATT&CK mapping delta, evidence package (episode refs),
reproduction instructions (a new capture recipe — regression test), FP analysis
(benign-corpus results), known limitations, IR implications (seeded from
`response_loop.RESPONSE_PRIMITIVES` technique map). Portal generates everything
deterministically derivable; the operator confirms the spl_detections.yaml
change (a code change through the normal validation pipeline — BQ/AZ must hold).

## 22. Recent architectural drift since the historical design point

- `75c5054f`/`f88abc4e` (eval-gate closeout, instrument freeze): SUPPORTS_DESIGN
  (a stable acceptance instrument for TRAIN).
- `59839264` (exit codes through bench CLI): SUPPORTS_DESIGN (LOOP failure
  semantics).
- `3d2aca98`/`65958b7f` (literals → config/security JSON): SUPPORTS_DESIGN
  (hunt config convention).
- `e232bf01` et al. (cli.py facade decomposition into `commands/`): SUPPORTS_DESIGN
  (clean subcommand seam for a `hunt` command).
- Council-quorum reconcile `2bceecce`, scoreboard `d817f256`, recall attribution
  `d31da27a`, benign fatigue `d17a5012`: SUPPORTS_DESIGN (BN/BM/BQ instruments).
- Capture-recipe certification series: PROVIDES_BETTER_PRIMITIVE (G1b/HND).
- `drift_gate.py` landing (TASK_SEC_DRIFT_GATE_V1): PROVIDES_BETTER_PRIMITIVE
  (BR-DRIFT seed) — post-dates the historical design's component survey.
- Spine collapse to `spine_surfaces.yaml` globs: CHANGES_ASSUMPTION in the
  design's favor (new core modules cost zero units — VERIFIED at
  `config/spine_surfaces.yaml:360-377`).
- Nothing found that CONFLICTS_WITH_DESIGN.

## 23. Replacement/migration analysis (task §T; full table in MIGRATION doc)

Guiding correction: **do not treat B/P as one disposable block.** The bench
*driver shell* and *scoring orientation* retire; the *section machinery*,
*telemetry plane*, *grounding gates*, *verdict semantics*, and *scoreboard
semantics* are load-bearing and move into the new system. `growth_loop`/
`response_loop`/`continuous_eval` are extracted-from and retired (their
valuable shapes live on in BIN/HND/SUB). `council_agreement` is replaced by the
objection-gate aggregation; `multichain.consolidate` is **kept** (already
fail-safe) as the multichain analysis mode's triage. `decision_engine.py` shim
stays (platform-owned re-export). Every retirement has a live replacement and
an honest-BLOCKED rule; Red never sees the change (Episode contract preserved).

## 24. Missing frontier-level capabilities (task §U) — justified additions only

1. **Persistent hunt substrate** (SUB) — the absence that breaks every feed.
2. **Record-level, distance-returning semantic organ API** (ORG) — raw cosine
   distances, metadata/provenance filters, record upsert; rag_mcp lacks all.
3. **Objection-gate aggregation** (HEART) — the concept's heart, absent.
4. **Real proof gates** (BIN G1a/G1b) — placeholder-true today.
5. **Composite cousin distance + explanation** (BR-COUSIN).
6. **Detection-baseline drift signals** (BR-DRIFT) on drift_gate machinery.
7. **Mutation director + budget** (MUT) on Red's direction surface.
8. **Decision-event log + cost ledger** (SUB) — provenance of *decisions*,
   not just evidence; compounding economics.
9. **Training-pair harvest + toolchain** (HARV/TRAIN).
10. **Learned playbook memory** (PLAY).
11. **Retrospective roster weighting** (ROSTER), bounded and non-gating.

Evaluated and rejected (no demonstrated architectural value now): behavioral
graph/causal-event-graph DBs, active-learning toolchains, novel vector DBs,
cluster-discovery frameworks, shadow/canary *deployment* infrastructure (the
bench already is the gate), experiment-tracking platforms.

## 25. Unnecessary complexity identified (task §V)

- `continuous_eval.py` — in-memory dashboard library superseded by SUB+PLT. RETIRE.
- `growth_loop.py` — placeholder gates; shapes extracted. RETIRE after extraction.
- `response_loop.py` — deterministic mappers superseded by HND. RETIRE after
  extracting RESPONSE_PRIMITIVES + technique map.
- `agentic_blue_eval.Episode` (second Episode type) — reconcile: replay DTO
  renamed/documented; single truth-plane Episode in `episode.py`.
- The wiki as runtime hunt memory — explicitly not built; spine stays design-facts.
- A `portal/platform/agent/loop.py` base for the hunt loop — rejected: the hunt
  loop's control flow (direct-red → episode → grade → gates → council → record)
  is security-specific and tighter than the generic provider/executor shape;
  forcing it buys indirection, loses clarity. The *discipline* (hard caps,
  confidence floors, honest-BLOCKED) is mirrored, not inherited.

## 26. Resource/operational constraints

- M4 Pro 64GB host; Ollama sole chat tier; council/hunt concurrency bounded by
  backend memory budgets in `config/backends.yaml`; per-turn bench timeouts
  (`CHAIN_MODEL_TURN_TIMEOUT_S=300`); slot-based pipeline concurrency.
- Embedding :8917 is CPU-pinned sentence-transformers (thread-safety note);
  reranker :8925 MLX. ORG must batch-embed and tolerate reranker fallback.
- LanceDB lives at `/Volumes/data01/portal5_lance`; the hunt substrate follows
  the same out-of-repo data-dir convention (`PORTAL5_HUNT_DIR`).
- Live hunts require the lab (10.10.11.0/24), `SANDBOX_LAB_EXEC=true`, attack
  image loaded in DinD, Splunk HEC token — all existing operator config.
- Spine: new modules land under `unit-surface-sec-core` globs → zero new units;
  at most one authored design unit per phase; no repin tax beyond normal.

## 27. Required design changes (summary carried into the final design)

1. SUB is NEW, seeded from the EvidenceRecord **schema** + CaseNotebook
   **pattern** — not from any existing store.
2. ORG is a new security-side organ module on the existing
   LanceDB/embed/rerank infra; rag_mcp is untouched.
3. BR-COUSIN composite distance as specified in §12, retrofits U1's grading
   vocabulary + explanation layer, not its scorer.
4. BR-DRIFT seeds from `drift_gate.py`, retargeted signals.
5. LOOP reuses blue_orchestrate's section machinery as its investigation arm;
   only the bench-driver shell retires.
6. BIN: real gates incl. G1a/G1b split and G3 measured via the triage lane;
   suspect-by-default at the finding level; BIN2 reframed accordingly.
7. HEART: objection-presence gate in code; falsification-tasked seats;
   platform mechanics reused; `council_agreement` replaced.
8. MUT: three seeds wired (variant overlay, evasion directive, deterministic
   recipes + emergent feed).
9. SCORE: distance-graded extension of notify_scoreboard semantics.
10. PROMOTE_POLICY becomes machine-readable hunt config.
11. Two-Episode reconciliation (truth-plane Episode is canonical;
    replay DTO renamed).
12. Six feeds each get a named measurable-change instrument (§17).

## 28. Final recommendation

**`DESIGN REQUIRES REFINEMENT`** — proceed to the final design package with the
twelve corrections above. The concept translation, thesis, invariants, and
phasing of the prior program are adopted; its parts inventory and disposition
table are corrected against HEAD; the cousin model, alert bin, council, feeds,
and flywheel are specified to implementation precision in the companion
documents.
