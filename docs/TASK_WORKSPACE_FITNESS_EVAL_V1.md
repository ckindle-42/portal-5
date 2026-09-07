# Task: Workspace Fitness Evaluation (WFE) — real-use fleet validation before any removal

**Supersedes the removal execution of** `MODEL_FLEET_CLOSEOUT_20260906` — that determination is now the **provisional input map** to this task. Its 92 REMOVED_CLOSED rows are HELD: nothing is deleted until this program completes and the register is re-issued (v4). Its 78 INTEGRATED rows are equally provisional: the settings audit has already shown production placements carrying silent defects (see Phase 0 findings).

**Doctrine (operator, 2026-09-07):** short-prompt tests cannot diagnose real usability. Each workspace/persona has an intended purpose with tools exposed to perform it; different models excel at different things — one size does not fit all, which is why the catalog is large. Models set out for one task often work better at another. Model cards inform; **real-world use decides**. Model **diversity is a decision factor** (purpose/fold/go). Every queued model AND every incumbent gets proper research to verify **settings, design, intent, execution, and capabilities** before fold/purpose/removed is decided.

**Existing instruments are not sufficient:** UAT validates shipped pipeline routes; bench probes measure narrow single-turn slices. What was missing — and this task builds — is the **workspace fitness** instrument: a model evaluated *in* its lane, *with* its persona prompt, *with* its tools exposed, on *real checkable work*, multi-turn.

## Framework (built, committed at `tests/wfe/`)

| Component | File | Role |
|---|---|---|
| Settings/design/intent auditor | `tests/wfe/settings_audit.py` | Zero-model-call verification of every workspace/persona/council seat: installed, registered, baked-ctx vs declared context_limit, sampling vs lane policy, tool-flag vs declared tools, pin resolution. `uv run python -m tests.wfe.settings_audit` |
| Fitness runner | `tests/wfe/runner.py` | Multi-turn tool loop (file_read/file_list/repo_search/pytest_run/file_write/http_get) with the workspace's hint + persona prompt; objective checkers (`pytest_pass`, `file_exists`, `file_contains`, `transcript_contains`, `human_review`); per-task turn/latency/tool budget; verbatim transcripts |
| Seed suites | `tests/wfe/suites/*.jsonl` | coding (2), research (2, networked), compliance_agentic (2 — the Sept-6 cases run *agentically* through tools), creative (2, human_review). Vision suite: extend `vision_probe` until runner gains image support |
| Workload map | `tests/wfe/workloads.yaml` | workspace → home suite + discovery suites + arms (incumbent first, then challengers) |
| Results | `tests/wfe/results/` | one JSON per run; fitness matrix compiled from these |

## Phase 0 — remediate the settings audit (no model calls; ~half a day)

Run `uv run python -m tests.wfe.settings_audit`. Known open items at task-creation time (fix before Phase 1):

- **WFE-0.1** `auto-coding` hint bakes `temperature 0.7` (coding lane; policy review: standardize or amend `LANE_SAMPLING`).
- **WFE-0.2** `bench-exec-exploit`, `bench-north-mini-code`, `bench-qwen36-cad` declare tools against `supports_tools: false` registrations — verify tool behavior live, then fix the flag or strip the declaration.
- **WFE-0.3** `auto-general-uncensored` hint rolled back to base 35B tag (apply-params failed to create `-ctx8k`); create the derived tag, restore the hint, re-audit.
- **WFE-0.4** council mistral seat unregistered in backends.yaml (works via council.yaml direct load; register for uniformity).
- **WFE-0.5** personas with stale/pin mismatches were fixed 2026-09-07 (dolphin/lily/30b-q5/E2b spelling/VulnLLM+nemotron case) — re-audit must show zero `persona_pin_absent`.
- **WFE-0.6 card ground-truth registry (the settings-research pass).** `config/model_card_expectations.yaml` is seeded with session-verified behavioral facts (gpt-oss harmony/format conflict; granite-4.2 quant-level system-honored failures; glm missing num_ctx + stop-token note; nemotron tag-case sensitivity) and **79 marked research-debt items**. For every integrated family: pull the model card's recommended inference block (temperature/top_p/top_k/min_p/repeat_penalty), the card's true max context, and the tool-support claim; record source URL + date; flip `verified: true`. Then diff every installed tag's baked parameters against the card (the auditor now fails `sampling_vs_card` / `ctx_over_card_max` on mismatch). Templates: where the stock Ollama template is suspect, record `known_good_template_sha` from a behaviorally-verified run and `template_source` — the auditor warns on `template_drift`.
- **WFE-0.7 behavioral template probes.** `uv run python -m tests.wfe.settings_audit --behavioral` runs one system-honored probe + one JSON-mode probe per hint (~2 calls each). `template_system_ignored` FAIL = broken/out-of-date chat template (the granite-4.2-small class of failure); empty-JSON warns for harmony-format models. Run this on every production hint before Phase 1; every FAIL needs a template fix (custom Modelfile from `template_source`) or a recorded design exception.

Exit: `0 FAIL` from the auditor (non-card kinds), behavioral probes pass or carry recorded exceptions, and WFE-0.6 registry coverage = every INTEGRATED family `verified: true`.

- **WFE-0.8 harness fidelity — thinking/streaming/endpoint.** The harness itself has had defects (gpt-oss 0.000 = think:false+format:json artifact; Sept probes ran `/api/chat` non-streaming while production serves `/v1/chat/completions`, which ignores `num_ctx` and has no think knob). Therefore, before any campaign:
  1. Set `harness_policy.think` per thinking-capable family in `model_card_expectations.yaml` (qwen3*, deepseek-r1, glm-z1, phi4-reasoning, gpt-oss=true). The runner resolves policy per tag and records the RESOLVED dimensions (`endpoint/stream/think`) in every result row.
  2. Run the harness self-test per model: `uv run python -m tests.wfe.runner --model <tag> --preflight` — checks strict-json vs native (the gpt-oss breakage class), stream-vs-non-stream content parity, and v1 reachability. `REVIEW` verdicts block that model's campaign until explained.
  3. Default endpoint is `v1` (production fidelity); `--endpoint api` arms are comparison-only and marked as such in analysis. Instrument caveats from the Sept runs are recorded here and in the closeout register.

## Phase 1 — incumbent verification (the "verify settings, design, intent, execution, capabilities" pass)

For every workload in `workloads.yaml`: run the **home suite with the incumbent arm**. Acceptance for each workspace: incumbent completes ≥ its historical bar (coding: ≥ 80% tasks; research: citation-grounded completions; compliance_agentic: correct determinations WITH tool use; creative: operator rubric). An incumbent that fails its own lane on real work is a **production finding** — fix settings (ctx baking, sampling) or open a lane replacement decision BEFORE evaluating challengers.

## Phase 2 — candidate placement (use-probe tier + contenders)

Each challenger runs (a) the home suite, (b) one discovery suite. Decisions per the stop rules already recorded in `MODEL_FLEET_CLOSEOUT_20260906.tasks.json` (USE-PROBE rows carry their assignments):

- kat-coder: real tool-loop coding vs bare-codegen exam — its 100% repair-elasticity + 7× speed profile was never tested in-flow
- command-r:35b: grounded-RAG documents work (its card's design purpose; prior tests were 500-token packets — the opposite of its design)
- granite4.2:30b: analyst long-document work (short-packet compliance gap may not transfer)
- fable-fusion: creative real sessions (operator rubric; no synthetic instrument exists)
- e2b/e4b family: fast-utility discovery (router-assist/drafting) vs their removed-by-default status
- OCR GGUFs: real-documents comparison vs the MLX OCR stack (the "MLX covers it" assumption was config-derived, never benched)

## Phase 3 — cross-lane discovery sweep

Deliberate "works better at something else" search: every Phase-2 challenger also runs one non-home suite; any over-performance vs the home incumbent opens a **lane-fit decision** (fold-in/add/replace) with the same stop-rule discipline. Diversity factor applies: prefer the lineage-diverse option on near-ties (lineage census is in the closeout register §1; gpt-oss retained on it).

## Phase 4 — re-issue the closeout register (v4)

Fold WFE results back into `MODEL_FLEET_CLOSEOUT_20260906.tasks.json`: every USE-PROBE row terminates per its stop rule; production placements corrected per Phase 0/1 findings; removal manifest re-computed (blob-exact, shared-weight-safe). **Only now** execute the removal pass (`ollama rm` per manifest), re-run `scripts/model_cleanup_audit.py` (must show zero REMOVED-on-disk exceptions), `./launch.sh rebuild`, storage-effect report, commit.

## Governance

- Bounded: each task carries turn/time budgets; each row carries a stop rule; no open-ended campaign — the exit is the register v4, not "more testing."
- Honest instruments: checkers are objective (pytest/files/citations) except creative (human_review, explicitly marked).
- No removals, no production hint changes, before Phase 4 — except Phase-0 remediations, which are each reversible one-liners recorded here.
- Costs: suites are small by design (2 tasks per suite × 6 workloads × ~2 arms ≈ 50–70 task-runs for Phases 1–3); scale a suite only when its stop rule is ambiguous.
- Decision records: every WFE-influenced change gets the same register treatment as the closeout (reason, evidence refs, date).

## Coverage matrix — the holistic dimension contract (v2)

The operator's examples (templates, think/stream, settings, intent, usability, diversity) plus the gaps found in design review define the dimensions a fitness decision REQUIRES. Status: BUILT (harness covers it), PARTIAL, or PENDING (must exist before its tier's decisions are trusted).

| # | Dimension | Why | Instrument | Status |
|---|---|---|---|---|
| 1 | Settings/design/intent audit | silent regressions (glm 128K class) | `settings_audit.py` | BUILT |
| 2 | Card ground truth (sampling/ctx/tools/template) | "correct params per model" | registry + `--behavioral` probes | BUILT (research debt 79 items = WFE-0.6) |
| 3 | Think/stream/endpoint fidelity | harness defects masquerade as model results | harness dims + `--preflight` | BUILT (WFE-0.8) |
| 4 | Real-work tool loops in-lane | usability ≠ short prompts | `runner.py` + suites | BUILT (seed suites; expand per §Power) |
| 5 | Cross-lane discovery | "works better at something else" | discovery suites | BUILT (workloads.yaml) |
| 6 | Lineage diversity | portfolio factor | lineage census | BUILT (register §1) |
| 7 | Memory co-residency | chain budgets, swap reality | budget math + **live swap test PENDING** | PARTIAL |
| 8 | Production-sampling fitness | temp-0 passes ≠ temp-0.7 product | runner at workspace temperature, n≥3 seeds | PENDING (WFE-1.1) |
| 9 | Effective context (needle @ 10/32/64K graded fills) | baked ctx ≠ retrieval quality | needle suite | PENDING (WFE-1.2) |
| 10 | Prompt-eval latency at fill (TTFT) | 64K-capable but unusable | timed fills | PENDING (WFE-1.2) |
| 11 | Multi-turn accumulation (10–20 turns) | personas are conversations | multi-turn suite | PENDING (WFE-1.3) |
| 12 | Memory/RAG tool fidelity (remember→recall) | declared tools nobody verified | memory task pair | PENDING (WFE-1.4) |
| 13 | Tool-error recovery injection | malformed spirals (bakeoff evidence) | deliberate tool-fault injection | PENDING (WFE-1.5) |
| 14 | Tool discipline (call when needed / abstain / no confabulated success after ERROR) | hallucinated tool results | fault + negative-space checkers | PENDING (WFE-1.5) |
| 15 | Truncation & schema conformance under pipeline contracts | num_predict × verbose models | contract checker with nested schemas | PENDING (WFE-1.6) |
| 16 | Fake-citation detection (fetch the cited URL, verify content) | plausible fabrications pass keyword checks | checker upgrade: verify citations | PENDING (WFE-1.7) |
| 17 | Prompt-injection robustness (web lanes fetch untrusted pages) | injected instructions steer tools | canary-injection tasks | PENDING (WFE-1.8) |
| 18 | Over-compliance placement risk (uncensored models in general seats) | intent's safety half | placement review vs lane intent | PARTIAL (register notes; enforce in Phase 2) |
| 19 | Contamination control (private/novel tasks; training-recency inflation) | newer models score by memorization | private task bank + per-model contamination flag | PENDING (WFE-1.9) |
| 20 | Checker soundness (unit tests FOR the checkers) | harness defects = false verdicts | checker unit tests | PENDING (WFE-1.10; existing pytest_pass logic needs hardening) |
| 21 | Suite calibration & statistical power | 2 tasks cannot separate models | calibration run + min n/CI per suite before decisions | PENDING (WFE-1.11) |
| 22 | Environment fingerprint gate (Ollama version changes behavior) | 0.32→0.33 invalidated a gsha | env stamp + canary re-run on upgrade | PARTIAL (gsha exists) → standing gate (WFE-1.12) |
| 23 | Standing canary suite post-swap | promotions drift unverified | fixed canary re-run after ANY hint/pin change | PENDING (WFE-1.13; both this session's promotions get canaried) |
| 24 | Token economics (cost per completed task) | fast model × 5x tokens ≠ fast | tokens/task in fitness matrix | PENDING (WFE-1.14) |
| 25 | Cold-start & concurrency/swap under real loading | warm numbers lie | timed cold loads; 2-model co-resident latency test | PENDING (WFE-1.15, with #7) |
| 26 | Multimodal through the pipeline (real images, not 4 synthetic cases) | vision seats unverified at production resolution | extend runner images OR keep vision_probe + widen cases | PENDING (WFE-1.16) |

**Rule:** a disposition (integrate/re-tier/remove) that depends on a PENDING dimension is provisional until that dimension's instrument exists and has run for the models in question. This is what "proper testing before fold/purpose/removed" means operationally. Phase ordering follows dependency: WFE-1.10 (checker soundness) and WFE-1.11 (calibration) precede any decision that cites a suite; WFE-1.13 (canary) executes immediately after ANY Phase-2-influenced production change.

## Acceptance checklist

- [ ] Phase 0: auditor exits 0 FAIL
- [ ] Phase 1: every workload incumbent completes its home suite at or above bar; settings corrections recorded
- [ ] Phase 2: every use-probe row has a home + discovery result and a terminal disposition per stop rule
- [ ] Phase 3: cross-lane findings recorded (including "no discovery" negatives)
- [ ] Phase 4: register v4 issued; removal manifest executed and verified; `model_cleanup_audit.py` clean; gates green
