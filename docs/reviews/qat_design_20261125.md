# QAT stage design vs governing intent — 2026-11-25

Scope: `tests/qat/scenarios.py` and the stage definitions (`runner.py`, `uat_behavioral.py`,
`preflight.py`, `hardening.py`, `gate.py`, `__main__.py`), against
`docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md`, `docs/MODEL_SEAT_PROCESS.md` and the workspace
catalog in `config/portal.yaml`. Method: code read, offline plan builds (`--dry-run`,
`build_plan`), existing receipts under `results/qat/` (read-only), and the live catalog.
No live stack was exercised by this lane, with one exception disclosed under OPEN.
Grading-correctness findings are not re-litigated here — see
`docs/reviews/qat_grading_20261125.md` and `docs/reviews/qat_grading_second_opinion_20261125.md`;
this review covers stage design, coverage and unattended-run feasibility.

Four confirmed small defects are fixed in this lane as separate commits (D1, D3, D5-notes,
D4-notes, plus the persona-sweep slot bug); larger ones are proposed briefs at the bottom.

## Answers to the brief's questions

### Q1 — Does each stage test real use of each workspace or persona?

| Stage | Real use? | Evidence |
|---|---|---|
| 0 preflight | Ground truth, no model use | `preflight.py` runs the repo's own CLIs; honest |
| 1 hardening | Real product surfaces (health, auth, negative probes, SSRF, redaction) | `hardening.py`; product-facing, good |
| 2 smoke_routing | Not real use, but the served-model==routing-resolution check is a real routing verification; rows correctly tagged `plumbing-only` (`scenarios.py:153`) | `scenarios.py:47` one-line self-intro probe |
| 2 journeys | Mixed: coding/bigfix/CAD/documents/media rows do real artifact work with byte-level validation; reasoning/vision/daily/compliance rows are short generic tasks (plumbing-tagged) | `scenarios.py:296-345,709-791` |
| 2 personas_pin_sweep | **No** — see D2: addresses the workspace, not the persona; pin never checked | `scenarios.py:707-742` |
| 3 security | Strongest stage: real botsv1 telemetry through `query_splunk`, MITRE drafting on every catalog variant (pipeline-addressed), injection/refusal probes with machine claims (`mitre`/`spl`/`severity`) | `scenarios.py:907-1046`, `runner.py:1207-1229` |
| 4 adaptive_deep | **No** — meta-prompts ("Give your best complete answer for your specialisation", `scenarios.py:1075`); machine PASS = non-empty; the operator rubric never enters the verdict (D6) | `scenarios.py:1051-1079` |
| 5 human_grade | Yes — real multi-turn journeys, browser-driven, real artifacts, real corpora (`tests/fixtures/realuse_v1/`); graders loose (covered by the grading reviews) | `uat_behavioral.py` |

Persona coverage overall: 110 production personas; 12 get a one-line role-statement through
their workspace (no persona prompt), and ~8 get real Stage-5 contract cases
(`agentorchestrator`, `dataanalyst`, `datascientist`, `complianceanalyst`, `linuxterminal`,
`excelsheet`, `webresearcher`, plus the roster case). The 41 coding personas are represented
by 1 sweep row + 2 contract rows.

### Q2 — Which production workspaces/personas have no scenario, or only a trivial one?

No scenario anywhere (from the live catalog, 22 workspaces / 24 seeded presets):

- `auto-council` — the Stage-2 spec entry silently dropped (D3, now annotated); council
  product path untested by QAT.
- `compliance-council-deepseek-r1`, `compliance-council-granite41`, `compliance-council-qwen38`,
  `compliance-mapping`, `compliance-reading-overflow` — compliance pipeline seats, zero rows.
- `hunt-reasoning` — zero rows (the hunt *workflow* is covered via `security-reviewer`).
- `tools-specialist` (+`::fast`) — zero rows; personas point at it but the sweep filters them out.
- `auto-security::blueteam-orchestrated` — excluded by `CLI_ONLY_PRESETS` (`scenarios.py:37`).
- Non-exposed variants of exposed workspaces: `auto-daily::gemma-fast` (**the incumbent
  arm-read seat in the MODEL_SEAT_PROCESS ledger**), `auto-coding::{devstral_coder,
  fast-repair, gemma4-heretic-coder, glm-coder, hauhaucs-coder, heavy, laguna, lite,
  northmini, ornith, ornith15-coder, qwen38coder, qwen38coder-dflash, uncensored,
  uncensored-agentic}`, `auto-documents::extract-uncensored`,
  `auto-general-uncensored::{creative,throwaway,throwaway-gemma4-heretic,throwaway-ornith15}`,
  `auto-reasoning::{deep,glm-thinker,magistralstrategist}`, `auto-research::data`,
  `auto-spl::nano`, `auto-vision::{gemma4jangvision,gemma_vision}`.
  Note the asymmetry: `auto-security`'s 16 non-exposed variants DO get pipeline-addressed
  canonical rows (`scenarios.py:907`), proving the pattern exists — it is just not applied
  to any other workspace family.

Trivial-only: `auto-reasoning` (schoolbook proof), `auto-reasoning::math` (one arithmetic
line), `auto-vision` (harness-generated red-square PNG — WFE dimension 26 "real images" is
still PENDING), `auto-daily` family (Kyoto trip plan), `auto-compliance` (smoke only, but
honestly annotated IN_SERVICE=False — settled, not re-litigated), and the 12 persona sweep
rows (D2).

### Q3 — Which scenarios test the harness rather than the product?

- `s2-p7-risky-step-confirmation` (`scenarios.py:866`): asserts
  `PORTAL_ARM_APPROVAL_TTL_SECONDS` from **the QAT runner's .env**, never the pipeline's
  runtime config; prompt never executed. Counts as an acceptance row.
- The `kind="infra"` rows (D4): `s2-p3-data-mcp` ("SELECT 1 via the data MCP"),
  `s2-p3-proxmox-readonly`, `s2-p3-unifi-readonly`, `s2-p7-pipeline-mcp`,
  `s3-hunt-mcp-{mitre,vulnintel,icsot,netforensics}` — `_run_infra` (`runner.py:991`) only
  GETs `/health` (+`/ready` for data). Deployment health probes wearing usage-scenario
  titles; all count as acceptance rows.
- `s3-lab-exec` (D5): permanently SKIP — no probe target exists for its `lab` tag.
- Stage-4 `continuity` (minor): the harness replays the conversation branch in the request
  (`prior_messages`, `runner.py:1579`), imitating what OWUI does — an API-level echo test,
  not the product's own state path. The browser-driven Stage 5 is the real one.
- The red-square vision probe is a harness-generated fixture — acceptable as a plumbing
  smoke (it is tagged plumbing-only), but it is not seat-fitness evidence.

### Q4 — Is the end-to-end run (Stage 0–5, one SHA, browser-driven, quiet host) achievable unattended?

After the D1 fix, mechanically yes — one process, per-row checkpoints, row-level lineage,
headless Playwright, meaningful exit code. It was **not** achievable before D1: the
documented full-cascade command interleaved Stage 5 between Stage-2 phases (23 phase
switches, 7 `human_grade` re-entries, ~22 full gate+eviction cycles), and no receipt shows
a single-process 0–5 run ever happened (`results/qat/release_1_0_20261123T080329Z` ran
stages 0–4; Stage 5 ran in separate `stage5-browser-verify-*` runs).

Where it still needs a human or an orchestrator decision:

1. **Setup**: `.env` named keys incl. `OPENWEBUI_ADMIN_PASSWORD`. Missing password only
   warns (`__main__.py:74-83`) then every live row FAILs at signin — should fail fast.
2. **Playwright**: Stage-5 browser cases FAIL hard without it (`uat_behavioral.py:2994`),
   but the Stage-2 browser row SKIPs (`runner.py:1647`) — "browser-driven" can silently
   degrade one stage and hard-fail the other. Inconsistent.
3. **Quiet host**: the inter-phase gate evicts ALL resident models and can spin its 600 s
   budget then BLOCK the cascade (grading review F9). Nothing checks that no other
   eval/bench is in flight; QAT itself will evict seats another run needs. Orchestrator
   must schedule exclusivity.
4. **OWUI memories**: Stage-5 runs snapshot→clear→restore in-process
   (`runner.py:511-552`). A SIGKILL/power loss mid-run leaves the operator's real OWUI
   memories cleared with the snapshot lost — the one place an unattended QAT run can
   destroy live user state.
5. **Stage 4 rubric**: worksheets are a separate manual flow and the frozen scores never
   reach the verdict (D6) — an unattended run's "acceptance" for 92 of ~188 rows is a
   non-empty-content check.
6. **Stage 5 STT**: WARN by design until a human compares playback (README).
7. **Sign-off**: `review.html` [GATE] packet is human by design.
8. **One SHA**: true for a single process (lineage stamped per row, `--rerun-failed`
   refuses mismatched lineage). But the fingerprint is taken once at start
   (`runner.py:482`); a multi-hour run whose host config drifts mid-run (engine
   autoupdate, live-checkout pull, `backends.yaml` is mounted) keeps stamping the start
   SHA — WFE dimension 22 (environment fingerprint gate) has no QAT equivalent.

### Q5 — Minimal added/retired scenarios

Retire or demote (removes fake-usage acceptance rows):

1. Move the 8 MCP `kind="infra"` health rows into Stage 1 hardening (where health probes
   already live), or keep them as rows but tag `plumbing-only` and rename to "…health".
2. Retire `s3-lab-exec` until a real lab-exec scenario exists (it has never been able to PASS).
3. Rewrite or retire the persona pin sweep (D2) — today it tests neither personas nor pins.

Add (minimal, reusing existing patterns):

4. Pipeline-addressed smoke rows (the `s3-canonical` pattern, `kind="pipeline"`,
   ROUTING_PROBE + served-model check) for the production seats that carry decisions:
   `auto-daily::gemma-fast`, `auto-council`, `hunt-reasoning`, `compliance-mapping`,
   `compliance-reading-overflow`. ~5 rows, no OWUI exposure needed.
5. Persona-faithful sweep: address persona slugs the way Stage 5 does
   (`uat_behavioral.py:_persona_cases`), one per persona category (13 categories → 13
   rows), graded on the trace resolving the persona's seat.
6. One real-image `auto-vision` row from `tests/fixtures/realuse_v1/` instead of the
   red square (aligns with WFE dim 26).

Keep as-is: Stage 3 hunt/canonical/adversarial, Stage 2 artifact rows (coding/CAD/
documents/media/pdf-read), Stage 5 journeys.

## Findings (detail)

### D1 — Full cascade ran Stage 5 interleaved into Stages 1–2 (FIXED, commit 1)
- `tests/qat/uat_behavioral.py:154` (`tier=UAT_TIER_BASE + index`; was `tier=index`),
  `tests/qat/runner.py:779-791` (gate on every `(stage, phase)` switch).
- Claim: UAT tiers 1..43 collided with `s1-hardening` (tier 1) and Stage-2 tiers 10–80, so
  the documented `uv run python -m tests.qat` (stages 0→5, README) ordered the cascade
  0,1,5,2,5,2,…,4. Measured on the live catalog: 23 phase switches, 7 `human_grade`
  re-entries, ~22 `run_gate` invocations — each evicting every resident model and each
  capable of burning the 600 s wait budget.
- Failure scenario: full unattended run; every alternation evicts the seat the previous
  row loaded → every row cold-loads → runtime inflation; on a host with any background
  memory use a gate BLOCKs and the remaining cascade is marked BLOCKED/INFRA.
- Severity: stability (and breaks the documented stage order) · Confidence: high (dry-run
  plan output before/after; `_execute` code path).
- Fix: Stage-5 tiers now 301+; plan shows 15 contiguous phase blocks, stages 0→5.
  Tests: `test_full_plan_runs_stages_in_order_with_contiguous_phases`,
  `test_uat_registry_cascades_after_stage4`.
- Live check (orchestrator): `uv run python -m tests.qat --dry-run` — `stage 5 · phase
  human_grade` must appear once, after `stage 4 · phase adaptive_deep`; in a real full
  run, `results.jsonl` scenario order has no `s5-*` row before the last `s4-*` row, and
  gate evictions drop from ~22 to ~13.

### D2 — `personas_pin_sweep` verifies neither the persona nor the pin
- `tests/qat/scenarios.py:707-742`; `tests/qat/runner.py:292-344` (`_primary_model_failure`).
- Claim: the s2-p5 row's `model_slug` is `p.workspace_model`, so the turn goes to the
  **workspace preset**; the persona's system prompt is never applied (contrast Stage 5,
  which addresses `persona.slug`). `expected=p.model_pin` is decorative — `expected`
  strings are not machine-graded (established in both 11-25 grading reviews) — and the
  machine grader checks the *workspace's* primary hint instead. Production has 110
  personas and **zero** `model_pin` values (`load_personas()` on the live catalog), so the
  phase name is stale too. Fixed sub-bug (commit 3): the eligibility filter ran *after*
  the 12-slot cap, so an ineligible persona could consume a slot and silently shrink
  coverage below 12.
- Failure scenario: OWUI seeding drops a persona's system prompt or points the persona
  model entry at the wrong seat → every s2-p5 row still PASSes (workspace answered,
  workspace primary served) → the run reports persona coverage it did not exercise.
- Severity: missing-feature · Confidence: high (code; Stage-5 persona addressing read for
  contrast).
- Live check: `uv run python -m tests.qat --phase personas_pin_sweep --api-only`; for an
  s2-p5 row, the chat's model id in the request is the workspace preset, and
  `evidence.trace.workspace` is not the persona slug.

### D3 — `auto-council` silently dropped from the Stage-2 spec (FIXED, commit 2)
- `tests/qat/scenarios.py:266` (spec), `:296-311` (was `if pid in d.presets`).
- Claim: `auto-council` (`config/portal.yaml`, `expose_to_owui: false`) is not a seeded
  preset, so the council journey scenario was dropped with no row, no annotation —
  contradicting the module docstring's "never silently skipped" principle. Council had
  zero QAT coverage anywhere (only `auto-security`'s council *variants* get canonical rows).
- Failure scenario: council orchestration regresses (e.g. `council.yaml` seat change);
  the full cascade stays green; the report's capability matrix simply has no council line.
- Severity: missing-feature · Confidence: high.
- Fix: spec presets that are not seeded now emit an annotated disabled row
  (`s2-p2-auto-council`, `NOT_SEEDED_ANNOTATION`, plumbing-tagged, visible in
  `--dry-run` as `[DISABLED — annotated]`). Test:
  `test_unseeded_spec_preset_annotated_disabled`.
- Live check: `uv run python -m tests.qat --dry-run | grep s2-p2-auto-council`.
- Real council coverage (pipeline-addressed turn) is proposed brief PB1, not a lane fix —
  a council turn is multi-model and expensive; that is an operator scheduling decision.

### D4 — Infra "usage" scenarios are /health probes with decorative prompts (notes FIXED, commit 4)
- `tests/qat/runner.py:991-1019` (`_run_infra`), `tests/qat/scenarios.py:459-464`
  (`s2-p3-data-mcp`, prompt "SELECT 1 via the data MCP", old note claimed "the SQL chat
  path is exercised via the MCP surface directly"), `:470-505` (proxmox/unifi),
  `:855-861` (pipeline-mcp), `:975-981` (hunt MCP rows), `:866-885`
  (`s2-p7-risky-step-confirmation`).
- Claim: `kind="infra"` never executes the prompt. `_run_infra` matches scenario tags
  against MCP fleet ids and GETs `/health` (+`/ready` for data); the "policy" row asserts
  the runner's own `.env` value. All of these rows count as **acceptance** rows (the
  plumbing tag only applies to stage-2/3 `chat`/`pipeline` kinds, `scenarios.py:153-159`).
- Failure scenario: data MCP answers `/health` but its SQL tool is broken →
  `s2-p3-data-mcp` PASSes and the acceptance matrix tells the operator the SQL lane was
  exercised. Demonstrated offline: calling `_run_infra` directly returns PASS with
  evidence containing only the two HTTP probes, prompt untouched.
- Severity: missing-feature / report honesty · Confidence: high.
- Fix (this lane): honest notes on every infra row (`INFRA_HEALTH_NOTE`, data-mcp note
  rewritten, risky-step note names the .env-vs-runtime gap). Test:
  `test_infra_prompt_scenarios_carry_probe_only_note`. The behavioral fix (real MCP tool
  call, or demotion to Stage 1) is proposed brief PB5.
- Live check: any run; `jq 'select(.scenario_id=="s2-p3-data-mcp")' results.jsonl` —
  evidence has `checks` with HTTP probes only, no tool spans.

### D5 — `s3-lab-exec` is permanently SKIP (dead scenario; note FIXED, commit 4)
- `tests/qat/scenarios.py:1030-1046` (`tags=("lab",)`), `runner.py:991-1012`.
- Claim: `"lab"` is not an MCP fleet id and not `"policy"`, so `_run_infra` finds no probe
  targets and returns SKIP "no probe targets for scenario" — **even when `p0-lab-ready`
  PASSed** and the requirement gate opened. Demonstrated offline by calling `_run_infra`
  with a PASSed `p0-lab-ready` row: SKIP. The scenario has never been able to run.
- Failure scenario: report shows `s3-lab-exec SKIP` on a lab-ready host; the operator
  reads it as "lab gated off" when in fact no executor exists.
- Severity: missing-feature · Confidence: high.
- Fix (this lane): the note now states the row always SKIPs and names `p0-lab-ready` as
  the real gate. Retire-or-implement is a Q5 decision (propose: retire until real
  lab-exec scenarios exist).
- Live check: full run on a lab-ready host — row detail is "no probe targets for scenario".

### D6 — Stage 4: half the acceptance verdict is a non-empty check; rubric scores never count
- `tests/qat/scenarios.py:1051-1079` (dims incl. `core` = "Give your best complete answer
  for your specialisation"), `runner.py:1696-1736` (worksheet emit/ingest),
  `__main__.py:111-124` (verdict), `report.py:52-54` (acceptance = non-plumbing rows).
- Claim: 92 of 242 plan rows (and 92 of ~188 acceptance rows) are Stage-4 adaptive rows.
  They are not plumbing-tagged (the tag applies to stages 2–3 only), so an unattended run
  counts them as acceptance with a machine check of "non-empty + hygiene + served model"
  against a meta-prompt. The operator rubric flow is separate, manual, and
  `worksheets_frozen.json` is never merged into rows, the report, or the verdict.
  (Grading-side statement already made in second-opinion finding #1; the design-side gap
  here is that the *stage's own contract* — "operator scores 1–5 via worksheets" — has no
  path back into acceptance.)
- Failure scenario: unattended full run reports e.g. "180 PASS acceptance"; ~half of that
  number is content-free; a seat that answers every specialisation prompt with fluent
  nonsense is fully green until a human happens to run the worksheet flow and read it.
- Severity: breaks-results (verdict semantics) · Confidence: high.
- Live check: run `--stage 4 --emit-worksheets`, fill one worksheet with score 1, run
  `--stage 4 --ingest-worksheets` — `QAT_REPORT.md` and the exit code are unchanged.
- Proposed brief PB4.

### D7 — Unattended-run blockers and risks (inventory, not a single defect)
See Q4. The two that are code-level and small enough to fix in a lane later:
- `__main__.py:74-83`: missing `OPENWEBUI_ADMIN_PASSWORD` warns and proceeds → should exit.
- `runner.py:511-552`: OWUI memory snapshot held only in process memory across a
  multi-hour run → should persist the snapshot to the run dir before `clear_memories`,
  and restore-from-disk on startup if a crashed run left status≠restored.
- `uat_behavioral.py:2994` vs `runner.py:1647`: Playwright absence FAILs Stage 5 but
  SKIPs Stage 2 → pick one policy (proposed brief PB3 covers all three).

### D8 — Coverage census (input to Q2/Q5, no fix claimed)
- Severity: missing-feature · Confidence: high (enumerated from the live catalog and the
  built plan; reproducible with the command below).
- Live check: `uv run python -m tests.qat --dry-run` and diff the model column against
  `config/portal.yaml` workspaces/variants — the Q2 list is that diff.

## Fixed in this lane (separate commits)

1. **D1** `uat_behavioral.py` Stage-5 tier base 300 (+2 tests).
2. **D3** `scenarios.py` annotated disabled row for unseeded spec presets (+1 test).
3. **D2 sub-bug** `scenarios.py` persona sweep filters before the cap (+1 test).
4. **D4/D5 notes** `scenarios.py` honest annotations on all infra rows (+1 test).

Deliberately NOT changed (behavior beyond a small fix / operator decisions): what the
persona sweep addresses (PB2), council pipeline coverage (PB1), infra-row demotion (PB5),
Stage-4 verdict wiring (PB4), unattended-run driver hardening (PB3), and anything already
owned by the two grading reviews.

## Proposed briefs

- **PB1 — pipeline-addressed coverage for non-exposed production seats.** Extend the
  `s3-canonical` pattern (`kind="pipeline"`, served-model graded) to the seats that carry
  decisions: `auto-daily::gemma-fast` (ledger incumbent), `auto-council`, `hunt-reasoning`,
  `compliance-mapping`, `compliance-reading-overflow`. Operator picks the variant list for
  `auto-coding`/`auto-general-uncensored` (15+4 variants — probably a WFE workloads.yaml
  question, not a QAT one).
- **PB2 — persona-faithful sweep.** s2-p5 rows address persona slugs (Stage-5 pattern),
  sample one persona per category (13 rows), grade that the trace resolved the persona's
  seat; rename the phase (no pins exist).
- **PB3 — unattended-run driver.** Fail fast on missing secrets; one Playwright policy;
  persist the OWUI memory snapshot to disk and recover after a crash; host-quiet
  precondition probe; re-fingerprint config at run end and annotate drift (WFE dim 22).
- **PB4 — Stage-4 rubric → verdict.** Ingested worksheet scores merge into row
  evidence/status (or Stage-4 rows are marked rubric-pending in the acceptance matrix).
- **PB5 — real MCP tool-call rows or demotion.** data/proxmox/unifi/pipeline-mcp rows
  either call one real tool (via a workspace that grants it, or the MCP surface directly)
  or move to Stage 1 hardening as the health checks they are.

## Verification (this lane)

- `uv run pytest tests/qat/tests/ -q` — green (tail in the lane report).
- Per-commit gate `uv run pytest tests/unit/ -q && uv run ruff check . && uv run ruff
  format --check . && uv run mypy portal/ && python3 scripts/complexity_report.py --gate`
  — output in the lane report.
- Plan evidence: `--dry-run` before fix: stage order `0,1,5,2,5,2,…,4`, 23 phase switches;
  after fix: `0,1,2,3,4,5`, 15 contiguous blocks, 242 scenarios (was 241 + the new
  annotated `s2-p2-auto-council`).
