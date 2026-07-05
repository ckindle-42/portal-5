---
id: unit-SEC_BENCH-multiseat-v2-results-2026-07-05
kind: mixed
title: "SEC_BENCH — Multi-Seat Model Bench V2 results (2026-07-05): BugTraceAI-27B, security-slm-1.5b, CyberSecQwen-4B (deferred)"
sources:
- type: doc
  path: coding_task/TASK_SEC_BENCH_MULTISEAT_V2.md
- type: code
  path: tests/benchmarks/bench_security/results/candidates/
- type: code
  path: tests/benchmarks/bench_security/investigation/agents.py
- type: code
  path: tests/benchmarks/bench_security/unknown_defense.py
last_generated_commit: 3c7d4825cce8be60c904f2144212d2c2a1d65792
confidence: high
tags:
- sec-bench
- multiseat
- candidate-eval
- status
created_at: 1783448400.0
updated_at: 1783448400.0
---

## Purpose

Real per-seat evaluation of three candidate models against the E2E capture library
(`EXEC_SEC_E2E_SYSTEM_V1`), per `coding_task/TASK_SEC_BENCH_MULTISEAT_V2.md`. All results isolated to
`results/candidates/`; `PROMOTE_POLICY: confirm` — nothing here auto-replaces a fleet incumbent.

## Model A — BugTraceAI-CORE-Ultra-27B (`hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K`)

**TPS note:** 5.0 t/s, below the 20 t/s intake floor — benched with `--force` per the task's own contingency.
Its slowness makes it impractical for full-scenario (`--all-scenarios`) benching; see Blue-analyst below.

| Seat | Verdict | Delta vs incumbent | Detail |
|---|---|---|---|
| Red — exploit | WORSE | −0.024 coverage, −1 lab_success | Stalled on `ctf_multi_service` (multi-step chain), tied elsewhere |
| Red — recon | NEUTRAL | +0.000 across all 6 scenarios | Only assigned a subset of multi-model chain steps; those it touched (kerberoast_to_da, ctf_multi_service) still WIN, matching incumbent exactly |
| Red — solo | **BETTER** | **+0.480 coverage, +2 lab_success** | Its full-spectrum reasoner profile dominates when running the WHOLE chain alone — clear win |
| Blue-analyst | Weak/inconsistent | n/a (no incumbent comparison run) | Benched on a 6-scenario representative subset (kerberoast_to_da, asrep_to_lateral, web_sqli_dump, web_ssrf, vuln_weblogic_rce, meta3_ssh_brute) — NOT `--all-scenarios`, because at ~5 t/s a full 84-scenario blue-chain replay projected to 20+ hours (confirmed: the initial `--all-scenarios` attempt was still stuck on scenario 1 after 26 minutes, killed). Results: kerberoast_to_da f1=0.50 (`PROVEN` — caught T1558.003, missed T1003.006/T1053.005), asrep_to_lateral f1=0.00 (`FAILED`), web_sqli_dump f1=0.00, web_ssrf f1=0.67, vuln_weblogic_rce f1=0.00, meta3_ssh_brute f1=0.00. Two of six runs also logged a `400 Bad Request` mid-chain — consistent with the task file's own warning that thinking models can wrap tool calls oddly. **Net: not a strong blue-defender candidate**, inconsistent even where it partially works. |
| Investigation (Analyst/Challenger) | **BLOCKED — no hook exists** | n/a | `investigation/agents.py::run_analyst`/`run_challenger` and `investigation/bench_investigation.py::run_single_agent_baseline`/`run_multi_agent` are ALL scaffolded structure only — every implementation literally says "In production, this calls the pipeline... In this slice, we create the structure." There is no `model` parameter anywhere in either file, not even a single shared model hook, let alone per-agent selection. This needs a real wiring task before any model can be benched as Analyst/Challenger. Correctly not faked. |

## Model B — security-slm-1.5b (`hf.co/Nguuma/security-slm-unsloth-1.5b:latest`)

Real HF repo resolved 2026-07-05 (task file only said "AGENT: resolve GGUF ref," never done in this task or
its V1 predecessor) — `Nguuma/security-slm-unsloth-1.5b`, a DeepSeek-R1-Distill-Qwen-1.5B fine-tune for
2026 AI-native attacks (MCP poisoning, agentic lateral movement, Crescendo jailbreaks). Q4_K_M GGUF, pull
via `ollama pull hf.co/Nguuma/security-slm-unsloth-1.5b:latest` (note: `:Q4_K_M` tag does not resolve,
`:latest` does). Confirmed `tools`+`thinking` capabilities natively — no toolfix needed.

| Seat | Result |
|---|---|
| Classifier/triage (`soc_alert_triage` prompt, `--direct-theory`) | **0.70** theory score — hits all 4 required structural headers (CLASSIF/SEVER/CONTAIN/SUMMAR) but cites **zero** MITRE ATT&CK IDs despite `mitre_min: 1`. Genuine, honest gap: well-organized output, no technique grounding. |
| Unknown-defense pre-classifier | **N/A — no LLM hook exists.** `unknown_defense.py::compute_similarity` is explicitly documented "U1: Heuristic feature-overlap (explainable, cited) — not embeddings" — pure deterministic word-overlap code, zero model involvement by design. There is no seat here for any model to fill. |
| Blue floor-check (`--replay-captured-red --purple --all-scenarios`, full 84 scenarios) | **f1 = 0.00 on all 74 scored scenarios** (2 `FAILED`, 72 `INDETERMINATE`, 10 `N/A`/no-ground-truth). A clean, complete floor — confirms the 1.5B model is too weak to be a working blue-defender, exactly as the task anticipated ("documenting where the 1.5b is too weak is as valuable as where it wins"). Ran at ~1.3 min/scenario — the full 84-scenario run was tractable (~110 min) unlike BugTraceAI's, since the model is tiny. |

**Verdict on security-slm-1.5b:** genuinely useful only as a classifier/triage-shaped assistant (0.70, structurally competent) — NOT usable as a blue-defender (complete floor) and has no applicable unknown-defense seat.

## Model C — CyberSecQwen-4B (`hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M`) — DEFERRED, not faked

A working `cybersecqwen-4b-toolfix` Modelfile existed briefly (2026-07-04, per `config/MODEL_CATALOG.md`) but
was **never committed to the repo** — only an ephemeral local `ollama create` tag in a since-lost session.
Re-attempted 2026-07-05:
- `RENDERER qwen3.5`/`PARSER qwen3.5` (Ollama 0.31.1 builtin) loads without error but doesn't match this
  fine-tune's actual output format — the model emits a Llama-style `<function=name><parameter=x>value
  </parameter></function>` block, not Hermes-style `<tool_call>{...}</tool_call>` JSON.
- A hand-authored Hermes-style `<tool_call>` template (explicit system-prompt instructions to comply) also
  failed — the model answered in plain prose with no `tool_calls` in the response at all.

Deferred per the task's own "note it + defer" instruction rather than faking a working bench. **Needs real
iteration on the model's actual native tool-call format** before it can be benched as a blue-defender
candidate — e.g. run it interactively without any tool schema to observe its natural style, or check the
`athena129/CyberSecQwen-4B` model card/discussions for the training format used.

## Overall takeaway

- **BugTraceAI-27B's real strength is running a full attack chain solo** (+0.480 coverage) — not as a
  multi-model chain participant (WORSE on exploit, NEUTRAL on recon) or as a blue-analyst (weak,
  inconsistent, occasional malformed tool calls). Its slow TPS (5 t/s) also makes full-scenario blue-analyst
  benching impractical without a representative-subset compromise.
- **security-slm-1.5b earns its "cheap connective tissue" framing only partially**: solid at
  structured-output classifier/triage tasks (0.70), but a complete floor as blue-defender (f1=0.00
  everywhere) and has no applicable seat for the unknown-defense pre-classifier role (that hook is
  intentionally non-model heuristic code).
- **CyberSecQwen-4B remains genuinely untested** — blocked on restoring its tool-call template, an
  infrastructure gap, not a capability finding.
- **Investigation seats (Analyst/Challenger) are structurally unwired for ANY model** — this is the one
  finding that applies regardless of which candidate you'd want to test there; a real wiring task is needed
  first (see also [[unit-SEC_BENCH-e2e-run-status-2026-07-05]] for the parallel E2E-run status note from the
  same investigation).
