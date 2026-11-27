# Portal 5 Test Strategy — Live Is the Proof; Offline Is Only the Pre-Boot Merge Gate

**Date:** 2026-11-27 · **Lane:** `lane/neon-tests3` · **Base SHA:** `29df39df6` (`main`; `origin/main` is 9 commits ahead at `29c9272ad`, which includes `test-reduce2` `b4413f773`)

---

## Executive Summary

Portal 5's core rule is explicit (`CLAUDE.md:27-40`): **"Live against the system — never synthetic, never a test. A passing test is not evidence."** Yet the repository's offline test suite grew into a second codebase that absorbs more churn than the product while missing every defect that mattered:

- **Churn asymmetry (last 30 days, `2026-10-28` → `2026-11-27`):** `tests/` + `portal/**/tests/` took **3,052 file edits (+184,487 / −210,788 lines = 395,275 churned lines)** vs `portal/` product's **1,414 file edits (+73,856 / −24,265 lines = 98,121 churned lines)** — **4.0× the line churn of the product**.
- **Defect blindness (2026-11-26/27 live fixes):** QAT stall cascade (`82c5de66f`, `cd33a7038`, `38d304f45`), oMLX `xhigh` template runaway (`6e4ec54de`, `bc66578fb`), tool-loop wire silence (`1d1fc6241`), working-set compliance seat reuse + oMLX settle (`2b908d3c8`, `d76085acc`), sandbox `/session` UID/DAC_OVERRIDE permissions (`f2de54d36`, `35168efcb`), and trace receipt `hunt_sources` clipping (`29df39df6`) were **all discovered live** while 6,134–7,027 offline unit tests stayed 100% green.
- **Runtime bloat (measured at `29df39df6`, `pytest -n 4`):**
  - `portal/**/tests`: **180.0 s** (1,487 tests — 94% is offline security-bench / ablation / scoring machinery in `portal/modules/security/tests/`)
  - `tests/qat/tests`: **48.7 s** (388 tests — 100%-mocked unit tests testing the *live QAT test harness itself*)
  - `tests/unit`: **54.9 s** (4,150 tests — of which `test_spine_gates.py` alone burns **22.6 s** re-running `validate_system.py` checks `AJ`/`BR`/`BS` + routing regression that already run on pre-push)
  - `tests/security`: **6.3 s** (587 tests — 83 phase-by-phase build-out files in `tests/security/bully/`)
  - `tests/wfe/tests`: **3.6 s** (366 tests — already cut to 28 LOC in `b4413f773`)
  - **78% of total pytest wall time (228.7 s of 293.5 s)** comes from `portal/modules/security/tests/` and `tests/qat/tests/` alone.

### Why Plan B (`PHASE2_PLAN.md`) and `test-reduce2` (`b4413f773`) Did Not Go Far Enough

1. **Plan B (`docs/test_trim/PHASE2_PLAN.md`) proposed building ~30 new `scripts/proofs/owui_*_matrix.py` / `ide_mcp_matrix.py` exercisers before trimming ~14k physical LOC of mock-heavy files.** That duplicates what already exists: `tests/qat` **already ships 242 live OWUI→Pipeline→engine scenarios across Stages 0–5** (verified via `uv run --extra dev python -m tests.qat --dry-run`), covering every workspace, persona, sandbox, document lifecycle, media async poll, memory cross-session + graph admin, RAG followup, CAD STL render/measure, Obscura browser, Proxmox readonly, security toolbelt, Splunk hunt, compliance policy conversation, and platform introspection. Furthermore, Plan B's 5% mock-density filter missed the largest bloat clusters — pure-Python bench/scoring/research build-out suites (`portal/modules/security/tests/`, `tests/security/bully/`, `tests/unit/test_hunt_notables*`, `tests/unit/test_hunt_scoreboard*`, `tests/unit/test_compliance_*`, `tests/qat/tests/`).
2. **`test-reduce2` (`b4413f773`) refused to cut any product-behaviour test**, stopping at −11.2k LOC (99.7k under its metric, ratio 0.494) and logging an honest negative.
3. **Measurement defect in `coding_task/measure_test_loc.py`:** `measure_test_loc.py` summed `tests/unit` + **all of `tests/wfe` (including 30,009 nonblank LOC of live WFE evaluation harness)** + `portal/**/tests`, while **excluding** `tests/security` (9,173 LOC) and `tests/qat/tests` (6,894 LOC). That simultaneously over-counted 30k of live eval infrastructure and under-counted 16k of actual offline pytest suites.

### Baseline Census (Verified on Both `29df39df6` and `origin/main` `29c9272ad`)

| Tree | Role | `29df39df6` (HEAD) nonblank LOC | `origin/main` (`29c9272ad`) nonblank LOC |
|---|---|---:|---:|
| `portal/` (excluding `/tests/`) | **Product code** | **202,099** (193,719 no-comment) | **202,107** (193,728 no-comment) |
| `tests/unit/` | Offline pytest | 66,518 (359 files) | 58,788 (327 files) |
| `portal/**/tests/` | Offline pytest | 10,985 (101 files) | 10,985 (101 files) |
| `tests/security/` | Offline pytest | 9,173 (96 files) | 9,173 (96 files) |
| `tests/qat/tests/` | Offline pytest (harness self-test) | 6,894 (12 files) | 6,894 (12 files) |
| `tests/wfe/tests/` | Offline pytest (harness self-test) | 3,497 (16 files) | 28 (2 files) |
| `tests/frontend/` + `tests/integration/` | Offline/hybrid pytest | 254 (3 files) | 254 (3 files) |
| **ALL OFFLINE PYTEST SUITES** | **True offline test LOC** | **97,321** (587 files, **32.5%** share, ratio **0.482**) | **86,022** (541 files, **29.9%** share, ratio **0.426**) |
| `tests/wfe/` (excl. `tests/`) | Live WFE harness + graded payloads | 30,009 (97 files) | 30,009 (97 files) |
| `tests/qat/` (excl. `tests/`) | Live QAT harness (242 scenarios) | 10,761 (14 files) | 10,761 (14 files) |
| `tests/benchmarks/` + `tests/other` | Live bench runners & libs | 19,699 (109 files) | 19,699 (109 files) |
| Legacy `measure_test_loc.py` sum (`unit` + all `wfe` + `portal/**/tests`) | Mixed (includes 30k WFE harness) | 111,009 (ratio 0.549) | 99,810 (ratio 0.494) |

**Target (operator, 2026-11-27):** Offline tests **≤ 20% of (product + offline test)** ⇔ **`test / product ≤ 0.25`** (≤ 50,524 nonblank LOC at 202.1k product; ≤ 48,000 LOC at ~192–193.7k no-comment product; less is better).

---

## 1. What the Merge Gate Must Contain (and Nothing More)

An offline check earns its seat in the merge gate **if and only if** it can fail on a real defect introduced by a commit **before** a live run can boot or safely execute, OR it guards a deterministic invariant with **no live oracle**.

### Layer A — Zero-Test-LOC Static & Structural Gates (keep 100%)
These catch syntax, type, import, schema, config, secret, and drift errors at **0 test LOC**:
1. `uv run ruff check .` and `uv run ruff format --check .` (lint + syntax + style)
2. `uv run mypy --exclude "portal/modules/compliance/" portal/` (strict static types)
3. `uv run python3 -m portal.platform.inference.cli config validate` (config schema + Rule 6)
4. `python3 scripts/complexity_report.py --gate` (data_lines, god_lines, unwired_scripts, identical_pairs, committed_blob_bytes — plus new test-ratio ceiling below)
5. `scripts/validate_system.py --skip-pytest` on pre-push (220 structural/config/wiki/arm checks — remove duplicate pytest wrappers like `test_spine_gates.py` that re-run the exact same checks during `pytest`)

### Layer B — Minimum Offline Contract Suite (Target Budget: ≤ 35k nonblank LOC, ≤ 15% test share, ≤ 25 s wall time)
Keep **only** five narrow categories of offline tests:

1. **Engine wire & protocol boundary contracts (~5.5k LOC):** Catch silent HTTP-200 corruption (e.g., P5-OLLAMA-V1-SAMPLING-001, P5-OMLX-QWEN38-MTP-001, P5-OLLAMA-STREAM-ABORT-001) before a live run wastes GPU time:
   - `test_ollama_native.py`, `test_omlx_backend.py`, `test_reasoning_effort.py`, `test_security_seat_reasoning_effort.py`, `test_thinking_channels.py`, `test_text_tool_call_salvage.py`, `test_stream_pipeline_errors.py`, `test_stream_repetition_guard.py`, `test_stream_inband_error.py`, `test_stream_fallback.py`, `test_streaming_client*.py`, `test_pipeline_hardening.py`
2. **Load-guard, memory-ceiling, placement & failover safety invariants (~3.3k LOC):** Catch admission/eviction/prefill bugs that would OOM or wedge the M4 Pro host in a live run (P5-LOADGUARD-PS-001, P5-OMLX-CEILING-001, `d76085acc`, `65a50031b`):
   - `test_load_guard.py`, `test_load_guard_container_settings.py`, `test_load_guard_omlx_settle.py`, `test_router_placement.py`, `test_failover_protection_and_empty_hop.py`, `test_failover_window_floor.py`, `test_context_overflow_guard.py`, `test_capacity_fallback.py`, `test_seat_fit.py`
3. **Config, routing, tool-exposure & contract schemas (~4.2k LOC):** Catch unbootable config, missing seat hints, tool-name collisions, or stale live-check mappings:
   - `test_config_schema.py`, `test_config_validate.py`, `test_catalog_schema.py`, `test_routing.py`, `test_auto_router_handoff.py`, `test_backend_registry_health.py`, `test_mcp_fleet_single_source.py`, `test_mcp_http_client.py`, `test_native_mcp_service.py`, `test_owui_tool_merge_dedup.py`, `test_channels.py`, `test_request_no_tools.py`, `test_require_tool_before_answer.py`, `test_required_tool_choice_retry.py`, `test_tool_repeat_guard.py`, `test_tool_dispatch_order.py`, `test_tool_dispatch_timeout.py`, `test_tool_backoff.py`, `test_tool_loop_byte_budget.py`, `test_seat_primary_matches_production.py`, `test_model_catalog_parity.py`, `test_generated_artifacts_fresh.py`, `test_hint_validator.py`, `test_variant_hints_resolve_in_routing.py`, `test_live_check_map.py`
4. **Security & isolation walls (~2.5k LOC):** Deterministic safety boundaries where a regression would leak data, escape sandbox, or execute unapproved destructive actions before a live check finishes:
   - `test_sandbox_network_isolation.py`, `test_sandbox_images.py`, `test_lab_guard_shell_injection.py`, `test_adversarial_safety_guard.py`, `test_download_link_safety.py`, `test_documents_read_refusal.py`, `test_jarvis_personal_approvals.py`, `test_hunt_knowledge.py`, `test_mawa_join_guard.py`, `test_egress_aliyuncs.py`, `test_pipeline_mcp_confine.py`, `tests/security/bully/test_truth_y4_quarantine_and_guard.py`, `portal/modules/security/tests/test_write_isolation.py`, `portal/modules/security/tests/test_sandbox_output_cap.py`
5. **Deterministic invariants with no live oracle yet (~4.5k LOC):**
   - Compliance V6 core contracts & citation/quote fidelity (`IN_SERVICE=False` — no live corpus oracle yet): `test_compliance_engine.py`, `test_compliance_change_pipeline.py`, `test_compliance_citation_by_quote.py`, `test_compliance_citation_integrity.py`, `test_compliance_v3_contract.py`, `test_compliance_v3_matrices.py`, `test_compliance_tiers.py`, `test_compliance_gate.py`, `test_compliance_auth.py`, `test_compliance_review_decide_auth.py`, `test_compliance_machine_seat_isolation.py`, `test_compliance_reading_acceptance.py` (imported by `scripts/verify_compliance_reading_acceptance.py`)
   - Retrieval τ guard (`test_rag_multimodal.py` — mandated by `KNOWN_LIMITATIONS.md` P5-VL-RETR-002; `test_chunking_5tuple.py`)
   - Wiki core + thin module MCP contracts (`test_wiki_core.py`, `portal/platform/wiki/tests/`, `portal/platform/agent/tests/`, `portal/modules/*/tests/test_*_mcp.py`, `tests/security/review/*`)

Everything outside Layers A & B moves to live verification or is deleted outright.

---

## 2. What Moves to Live — Area Ownership & Diff-Driven Triggering

Every product area already has a live exerciser in `tests/qat` (242 scenarios), `scripts/smoke_stream.sh`, `portal trace`, `scripts/memory_canary.py`, or `scripts/proofs/owui_hunt_chat.py`. **No new matrix framework is needed.** Instead, a declarative `config/live_check_map.yaml` + `scripts/live_checks_for_diff.py` maps any commit's changed files to the exact minimal live subset for the orchestrator to run after merge+rebuild:

| Product Area | Live Proof Owner (existing, zero new harness) | Trigger Rule (`config/live_check_map.yaml`) |
|---|---|---|
| Pipeline streaming / tool loop / engine adapters | `./scripts/smoke_stream.sh` + `portal trace --section engines --section workspaces` + QAT `s2-p1-auto`, `s2-p4-omlx-tool-calling`, `s5-route-kubernetes-rbac` | `pipeline-streaming` |
| LoadGuard / placement / seat-fit / working sets | `portal trace --section engines --section pins` + QAT `p0-load-guard`, `s2-p1-auto-daily`, `s2-p1-auto-coding` + `scripts/memory_canary.py` | `pipeline-load-guard` |
| Routing / `portal.yaml` / `backends.yaml` / personas | `smoke_stream.sh` + `portal trace --section pins --section engines --section workspaces` + QAT `p0-routing-baseline`, `p0-exposure-gap`, `s5-route-*`, `s5-daily-out-of-lane` | `pipeline-routing-and-config` |
| Coding & DinD code sandbox | QAT `s2-p3-auto-coding`, `s5-sandbox-python-bash-network-isolation`, `s5-sandbox-lifecycle` | `module-coding-sandbox` |
| Documents MCP (PDF/Office/convert) | QAT `s2-p3-auto-documents`, `s2-p3-auto-documents-pdf-read`, `s5-documents-office-content`, `s5-documents-full-lifecycle`, `s5-documents-full-lifecycle-convert` | `module-documents` |
| CAD (OpenSCAD / build123d / STL) | QAT `s2-p3-auto-coding::cad`, `s5-cad-stl-render`, `s5-cad-measurement-and-convert` | `module-cad` |
| Media (image / video / music / TTS / STT / voice-clone) | QAT `--phase media_heavy` + `s5-media-image-quality`, `s5-media-tts-speech`, `s5-media-stt-accuracy` | `module-media` |
| Memory & EmbeddingGemma 2 | QAT `s2-p4-memory-roundtrip`, `s5-memory-cross-session`, `s5-memory-graph-admin` | `platform-memory-and-embedding` |
| Retrieval / RAG / VL reranker | QAT `s2-p3-rag-roundtrip`, `s5-rag-followup` | `platform-retrieval-and-rag` |
| Research & Obscura browser | QAT `s2-p2-auto-research`, `s2-p3-obscura-browser`, `s5-browser-web-research`, `s5-browser-web-research-obscura` | `module-research-and-browser` |
| Data MCP | QAT `s2-p3-data-mcp`, `s5-persona-correlation-dataanalyst` | `module-data` |
| Security / Hunt / Bully / MITRE / Detections / ICS / VulnIntel / NetForensics | `portal trace --section lab` + QAT `p0-lab-ready`, `s3-security-reviewer`, `s3-hunt-mcp-mitre`, `s5-security-hunt-workflow`, `s5-security-toolbelt` + `scripts/proofs/owui_hunt_chat.py` | `module-security-hunt` |
| Compliance (`IN_SERVICE=False`) | QAT `--phase compliance_smoke` + `s5-compliance-multiframework`, `s5-compliance-policy-conversation` | `module-compliance` |
| Orchestration / Jarvis / General | QAT `--phase jarvis_personal` + `s5-daily-everyday-no-suggestion`, `s5-persona-clarify-agentorchestrator`, `s5-persona-destructive-agentorchestrator` | `module-orchestration-and-general` |
| Platform MCP host / agent / storage / wiki | `portal trace --section platform` + QAT `p0-portal-trace`, `s2-p7-pipeline-mcp`, `s5-platform-introspection-and-git` | `platform-mcp-host-and-agent`, `platform-storage-and-wiki` |
| QAT harness (`tests/qat/**`) | `uv run --extra dev python -m tests.qat --dry-run` + QAT `p0-portal-trace`, `s2-p1-auto` | `qat-harness` |

**Post-merge orchestrator workflow:**
```bash
uv run python scripts/live_checks_for_diff.py --base origin/main
```
If `rebuild_required: yes` (any change under `portal/**`, `config/portal.yaml`, `deploy/**`, `pyproject.toml`, `uv.lock`), the command list starts with `./launch.sh rebuild && ./launch.sh up`, followed by only the deduplicated live commands covering the changed surface — turning a multi-hour full QAT sweep into a 1–5 minute targeted live proof per merge.

---

## 3. What Gets Deleted Outright — Category Breakdown & Arithmetic

Every deletion area below is **100% disjoint from `origin/main` (`29df39df6..29c9272ad`, i.e., `b4413f773`)** so this branch merges cleanly with zero conflicts and hits **≤ 20% test share even standalone** (and **~13–14% share** once combined with `b4413f773`).

| Cut Area (one revertable commit each) | What Is Cut | Est. Nonblank LOC Cut | Runtime Saved | Live / Gate Replacement |
|---|---|---:|---:|---|
| **Area 1:** QAT harness self-tests | All 12 files in `tests/qat/tests/` (mocked tests of the live QAT runner) | **−6,894** | **~48.7 s** | `python -m tests.qat --dry-run` + real QAT runs |
| **Area 2:** Security-bench / scoring / ablation tests | 69 bench/eval/scoring/sweep files in `portal/modules/security/tests/` (keep `conftest.py` + 5 core safety/isolation contract files ~150 LOC so wiki glob stays valid) | **−10,120** | **~175 s** | `scripts/validation/security_bench.py` + `blue_orchestration.py` + live QAT S3/S5 |
| **Area 3:** Bully research build-out tests | 80 phase-by-phase build-out files in `tests/security/bully/` (keep `test_full_assembly_f1.py`, `test_truth_y4_quarantine_and_guard.py`, `test_p1_1_contracts.py` = 422 LOC) | **−7,656** | ~6 s | `scripts/validation/bully_relate.py` + `scripts/defensive_bully_specimen_e2e.py` + QAT S3/S5 |
| **Area 4:** Hunt / notables / scoreboard / splunk-setup mock suites | ~36 files in `tests/unit/test_hunt_*`, `test_splunk_setup.py`, `test_siem_*`, `test_mawa_join*.py` (except guard), `test_portal_mitre_mcp.py`, `test_bench_security_qat.py` (keep security walls + `unwired_scripts` anchors) | **−12,200** | ~5 s | QAT `s3-security-reviewer`, `s3-hunt-*`, `s5-security-hunt-workflow`, `s5-security-toolbelt`, `owui_hunt_chat.py` |
| **Area 5:** Jarvis / orchestration / council mocked behavioral suites | ~17 files in `tests/unit/test_jarvis_*`, `test_arm_*`, `test_orchestration_*`, `test_council_*`, `test_telegram_*` (keep `test_jarvis_personal_approvals.py` safety wall + `orchestration_fake_pipeline.py` imported by `scripts/orchestration_acceptance.py`) | **−3,750** | ~3 s | QAT `--phase jarvis_personal`, `s5-persona-*-agentorchestrator`, `validate_system.py` `HR..HW`, `orchestration_acceptance.py` |
| **Area 6:** Mocked MCP / media / CAD / ops / duplicate-validate suites | ~38 files in `tests/unit/` + `tests/frontend/test_reasoning_display.py` (mocked documents/media/CAD/RAG/memory/proxmox/git MCPs + `test_spine_gates.py` / `test_wiki_quality.py` / `test_wiki_truth_claims.py` / `test_validation_test_hygiene.py` duplicating `validate_system.py` + historical walkdown/installer/notification mocks) | **−6,200** | **~45 s** | QAT Stages 2 & 5 (`s5-documents-*`, `s5-media-*`, `s5-cad-*`, `s5-memory-*`, `s5-rag-followup`, `s5-proxmox-readonly`, `s5-gui-persona-roster`) + `validate_system.py` |
| **Area 7:** Compliance pre-service bloat + legacy mocked pipeline/trace/metrics | ~47 overlapping compliance files in `tests/unit/test_compliance_*` (keep core V6 engine/change/citation/gate/auth/acceptance contracts) + `test_pipeline.py`, `test_trace_sections.py`, `test_tps_metrics.py`, `test_admin_reclaim_idle.py`, `test_pipeline_empty_prompt.py`, `test_research_tool_loop_cap.py` | **−8,500** | ~5 s | QAT `p0-portal-trace`, `s1-hardening`, `s2-p1-*`, `s5-compliance-*` + retained core pipeline/load-guard/streaming/compliance contract suites |
| **TOTAL PLANNED CUT** | **~299 offline test files deleted (disjoint from `b4413f773`)** | **~−55,320** | **~−285 s** | |

### Arithmetic Verification

- **Standalone on `lane/neon-tests3` (from `29df39df6` baseline of 97,321 offline LOC):**
  - `97,321 − 55,320 + ~65 (test_live_check_map.py) ≈ 42,066 nonblank LOC`
  - **Test share:** `42,066 / (202,099 + 42,066) = 17.2%` (**≤ 20% target met**)
  - **Test:product ratio:** `42,066 / 202,099 = 0.208` (**≤ 0.25 target met**, and **≤ 48,000 LOC**!)
- **Combined with `origin/main` (`29c9272ad`, which already deleted 11,299 LOC in `b4413f773`):**
  - `86,022 − 55,320 + ~65 ≈ 30,767 nonblank LOC`
  - **Test share:** `30,767 / (202,107 + 30,767) = 13.2%` (**far below 20%!**)
  - **Test:product ratio:** `30,767 / 202,107 = 0.152` (**≤ 0.25 target beaten by ~40%!**)

---

## 4. Guard Rails So Tests Do Not Regrow

1. **Complexity-gate ceiling on offline test ratio (operator-owned in `config/complexity_budget.yaml`):**
   - Extend `scripts/complexity_report.py` with two metrics computed cleanly from tracked `.py` files (excluding live harnesses `tests/wfe/`, `tests/qat/`, `tests/benchmarks/` outside their `tests/` subdirs):
     - `offline_test_lines` (integer nonblank LOC; ceiling e.g. `40000` after merge, or `48000` hard cap)
     - `offline_test_ratio_bps` (integer basis points `round(10000 * offline_test_lines / product_lines)`; ceiling **`2500`** = 0.25 ratio = **20.0% share**)
   - Using integer basis points fits `_load_budget()`'s existing non-negative `int` schema in `scripts/complexity_report.py:329` with zero schema redesign. Per `WORKER_CONTRACT.md` §4, this lane does **not** edit `config/complexity_budget.yaml`; the operator adopts the ceiling via `scripts/complexity_report.py --write-budget --reason "..."` after merging.
2. **Fix `coding_task/measure_test_loc.py`:** Stop counting 30,009 LOC of live `tests/wfe/` harness as offline tests, and include `tests/security/` and `tests/qat/tests/` so the metric reflects what `pytest tests portal` actually runs.
3. **Update `coding_task/BRIEF_TEMPLATE.md` / `WORKER_CONTRACT.md`:**
   - Replace the default "write a unit test for every bug fix" reflex with a two-branch rule:
     - **Behavioural defect found live in a QAT-covered surface →** add/tighten a **QAT scenario assertion or receipt check** (under `tests/qat/`), and point `ORCHESTRATOR RUNS` at `scripts/live_checks_for_diff.py --base origin/main`. **Zero new mocked unit test.**
     - **Wire-protocol, load-guard, config-schema, or security-boundary defect →** at most **1 focused regression test** appended to the owning contract file (never a new `test_<bug_ticket>.py` file).
4. **Prevent `unwired_scripts` & wiki `BS` friction when deleting tests:**
   - Operator CLI scripts belong in `scripts/OPERATOR_TOOLS.md`, never "wired" solely through a unit test import.
   - Canonical wiki units (`portal_wiki/canonical/*.md`) should cite product modules (`portal/...`), not individual `tests/unit/test_*.py` filenames, so trimming tests never breaks `AJ`/`BS`.

---

## 5. Risks, Staging Order & Revert Points

- **Staging order (lowest risk → highest judgment):**
  1. Commit 0: Strategy doc + `config/live_check_map.yaml` + `scripts/live_checks_for_diff.py` + `test_live_check_map.py` (additive PoC).
  2. Commit 1 (Area 1): Delete `tests/qat/tests/` (−6.9k LOC, −48.7 s) — zero product code covered.
  3. Commit 2 (Area 2): Trim `portal/modules/security/tests/` (−10.1k LOC, −175 s) — eliminates 3-minute bench suite and `field_journal` write-through.
  4. Commit 3 (Area 3): Trim `tests/security/bully/` (−7.7k LOC) — build-out research phase tests.
  5. Commit 4 (Area 4): Trim `tests/unit/` hunt/notables/scoreboard/splunk-setup (−12.2k LOC).
  6. Commit 5 (Area 5): Trim `tests/unit/` jarvis/orchestration/council (−3.8k LOC).
  7. Commit 6 (Area 6): Trim `tests/unit/` mocked MCP/media/CAD/ops/duplicate-validate + `tests/frontend/` (−6.2k LOC, −45 s).
  8. Commit 7 (Area 7): Trim `tests/unit/` compliance pre-service bloat + legacy mocked pipeline/trace/metrics (−8.5k LOC).
- **Revertability:** Every area is a single self-contained commit (`git revert <sha>` restores any area cleanly in seconds) and leaves `bash scripts/ci_local.sh` green.
- **Key risks & mitigations:**
  1. *Compliance (`IN_SERVICE=False`) has no live ACME corpus oracle yet:* Mitigated by retaining the 14 core deterministic Compliance V6 contract/citation/gate/auth/acceptance files (~1,800 LOC).
  2. *Deleting a test cited in `portal_wiki/canonical/` breaks `validate_system.py` checks `AJ`/`BS`:* Mitigated by removing dead test `sources:` entries in the same area commit and running `scripts/validate_system.py --skip-pytest --skip-lifespan --skip-cli` after cuts.
  3. *Deleting the sole test referencing a `scripts/*.py` file trips `unwired_scripts` (ceiling 25/25, headroom 0):* Mitigated by keeping the 11 sole-reference test files (or registering real operator scripts in `scripts/OPERATOR_TOOLS.md`) and running `python3 scripts/complexity_report.py --gate` on every commit.
  4. *Orchestrator must actually run `scripts/live_checks_for_diff.py` after merging product changes:* Without post-merge execution of the mapped QAT scenarios, cutting mocked behavioral tests would open a blind spot. Wiring `live_checks_for_diff.py` into the orchestrator's post-merge checklist closes the loop.

---

## 6. Retained Floor — Tests Whose Removal Would Let Real Defects Through Uncaught

The following tests remain in the offline merge gate after all 7 cuts because removing them would allow silent or host-wedging regressions with no faster live catch:
- **Engine wire & streaming contracts:** `test_ollama_native.py`, `test_omlx_backend.py`, `test_reasoning_effort.py`, `test_security_seat_reasoning_effort.py`, `test_thinking_channels.py`, `test_text_tool_call_salvage.py`, `test_stream_pipeline_errors.py`, `test_stream_repetition_guard.py`, `test_stream_inband_error.py`, `test_stream_fallback.py`, `test_streaming_client*.py`, `test_pipeline_hardening.py`
- **Host memory & failover safety:** `test_load_guard*.py`, `test_router_placement.py`, `test_failover_*.py`, `test_context_overflow_guard.py`, `test_capacity_fallback.py`, `test_seat_fit.py`
- **Config, routing & tool exposure:** `test_config_schema.py`, `test_config_validate.py`, `test_catalog_schema.py`, `test_routing.py`, `test_auto_router_handoff.py`, `test_backend_registry_health.py`, `test_mcp_fleet_single_source.py`, `test_mcp_http_client.py`, `test_native_mcp_service.py`, `test_owui_tool_merge_dedup.py`, `test_channels.py`, `test_request_no_tools.py`, `test_require_tool_before_answer.py`, `test_required_tool_choice_retry.py`, `test_tool_repeat_guard.py`, `test_tool_dispatch_*.py`, `test_tool_backoff.py`, `test_tool_loop_byte_budget.py`, `test_seat_primary_matches_production.py`, `test_model_catalog_parity.py`, `test_generated_artifacts_fresh.py`, `test_hint_validator.py`, `test_variant_hints_resolve_in_routing.py`, `test_live_check_map.py`
- **Security & isolation walls:** `test_sandbox_network_isolation.py`, `test_sandbox_images.py`, `test_lab_guard_shell_injection.py`, `test_adversarial_safety_guard.py`, `test_download_link_safety.py`, `test_documents_read_refusal.py`, `test_jarvis_personal_approvals.py`, `test_hunt_knowledge.py`, `test_mawa_join_guard.py`, `test_egress_aliyuncs.py`, `test_pipeline_mcp_confine.py`, `tests/security/bully/test_truth_y4_quarantine_and_guard.py`, `portal/modules/security/tests/test_write_isolation.py`, `portal/modules/security/tests/test_sandbox_output_cap.py`
- **No-live-oracle deterministic invariants:** Core Compliance V6 contract/citation/gate/auth/acceptance files, `test_rag_multimodal.py` (τ guard), `test_chunking_5tuple.py`, `test_wiki_core.py`, `portal/platform/wiki/tests/`, `portal/platform/agent/tests/`, thin `portal/modules/*/tests/test_*_mcp.py`, `tests/security/review/*`, plus the 11 `unwired_scripts` anchor tests (until their scripts are either retired or moved to `OPERATOR_TOOLS.md`).

---

## 7. Measured Post-Cut Results (Executed on `lane/neon-tests3`)

All 7 area cuts were executed as single, independently revertable commits with **zero file overlap** with `origin/main` (`29df39df6..29c9272ad`, including `b4413f773`):

| Commit | Area | Files | Nonblank LOC Delta |
|---|---|---:|---:|
| `f0b56a396` | Strategy doc + `live_check_map.yaml` + `live_checks_for_diff.py` + contract test | 5 | +580 |
| `f9c5792d0` | Area 1 (`tests/qat/tests/`) | 12 | −6,894 |
| `ec9ecf1da` | Area 2 (`portal/modules/security/tests/`) | 68 | −10,191 |
| `fa3ee6ec6` | Area 3 (mocked MCP/media/CAD/ops + duplicate `validate_system` tests) | 37 | −6,078 |
| `80861f9e2` | Area 4 (`tests/security/bully/` phase build-out tests) | 80 | −7,654 |
| `8e544d386` | Area 5 (mocked hunt/notables/scoreboard/splunk-setup suites) | 45 | −13,195 |
| `f9b26ce2a` | Area 6 (mocked jarvis/orchestration/council behavioral suites) | 14 | −3,629 |
| `21e6e9e37` | Area 7 (pre-service compliance bloat + legacy mocked pipeline/trace/metrics) | 42 | +6 / −7,707 |
| Final commit | Ignore offline test paths in `live_checks_for_diff.py` + append §7 measured results | 3 | +25 |

### Before / After Test Share & Ratio

| Tree | Baseline (`29df39df6`) | Standalone (`lane/neon-tests3`) | Combined w/ `origin/main` (`b4413f773`) |
|---|---:|---:|---:|
| `portal/` (product, nonblank / no-comment) | 202,099 / 193,719 | 202,099 / 193,719 | 202,107 / 193,728 |
| `tests/unit/` | 66,518 (359 files) | 35,985 (223 files) | 28,155 (191 files) |
| `portal/**/tests/` | 10,985 (101 files) | 794 (33 files) | 794 (33 files) |
| `tests/security/` | 9,173 (96 files) | 1,517 (16 files) | 1,517 (16 files) |
| `tests/qat/tests/` | 6,894 (12 files) | 0 (0 files) | 0 (0 files) |
| `tests/wfe/tests/` | 3,497 (16 files) | 3,497 (16 files) | 28 (2 files) |
| `tests/frontend/` + `tests/integration/` | 254 (3 files) | 254 (3 files) | 254 (3 files) |
| **ALL OFFLINE PYTEST (nonblank)** | **97,321 (32.5%, ratio 0.482)** | **42,047 (17.22%, ratio 0.2081)** | **30,748 (13.21%, ratio 0.1521)** |
| **ALL OFFLINE PYTEST (no-comment)** | **~95,500** | **41,457 (17.63%, ratio 0.2140)** | **30,270 (13.51%, ratio 0.1563)** |

- **Target (≤ 20% share / ratio ≤ 0.25 / ≤ 48k LOC):** **MET standalone (17.22%, 42,047 LOC, −56.8%)** and **beaten by ~39% once merged with `origin/main` (13.21%, 30,748 LOC, ratio 0.1521)**.
- Under legacy `coding_task/measure_test_loc.py` scope (excluding the 30,009 LOC live WFE harness): **40,276 LOC (ratio 0.1993)** standalone; **28,977 LOC (ratio 0.1434)** combined with `origin/main`.

### Before / After Runtime

| Suite | Before (`29df39df6`, `-n 4`) | After (`lane/neon-tests3`, `-n 4`) | Speedup / Delta |
|---|---:|---:|---:|
| `portal/**/tests` | 180.0 s (1,487 tests) | **3.17 s** (113 passed) | **−98.2% (56.8× faster)** |
| `tests/qat/tests` | 48.7 s (388 tests) | **0.00 s** (deleted) | **−100%** |
| `tests/unit` | 54.9 s (4,150 tests) | **36.99 s** (2,360 passed, 36 skipped) | **−32.6%** |
| `tests/security` | 6.3 s (587 tests) | **2.12 s** (104 passed) | **−66.3%** |
| `tests/wfe/tests` | 3.6 s (366 tests) | **3.01 s** (366 passed; 28 LOC on `origin/main`) | — |
| `tests/frontend` + `tests/integration` | — | **3.25 s** (1 passed, 2 skipped) | — |
| **5-bucket sum (`-n 4`)** | **293.5 s** | **45.29 s** | **−84.6% (6.5× faster)** |
| **Full CI suite (`pytest tests portal -n auto -q`)** | ~6,134–7,027 tests | **24.91 s** (2,944 passed, 38 skipped) | Under 25 s budget |
| **Single-process `tests/unit/`** | 109 s (3,669 tests on `b4413f773`) | **88.24 s** (2,360 passed, 36 skipped; drops further after merge w/ `b4413f773`) | — |

### Gate Verification

- `uv run ruff check .`: **All checks passed!**
- `uv run ruff format --check .`: **1430 files already formatted**
- `uv run mypy --exclude "portal/modules/compliance/" portal/`: **Success: no issues found in 568 source files**
- `python3 scripts/complexity_report.py --gate`: **GATE OK** (`data_lines: 10,201 <= 13,370`, `god_lines: 64,772 <= 71,202`, `unwired_scripts: 25 <= 25`, `identical_pairs: 0 <= 0`, `committed_blob_bytes: 1,792,894 <= 1,873,616`)
- `uv run python scripts/validate_system.py --skip-pytest --skip-lifespan --skip-cli`: **220 pass · 1 fail · 7 warn · 5 skip** — `AJ`, `BR`, `BS`, `HX`, `HR..HW` all pass; the sole failure (`HK`) is pre-existing on untouched `docs/BREAKER_V1_MIGRATION_PLAN.md`.
- `bash scripts/ci_local.sh`: **PASS** (full isolated `.ci-local-venv` mirror of `.github/workflows/unit-tests.yml`).
