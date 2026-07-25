---
id: unit-model-catalog-blue-red-candidate-batch-evaluated-2026-07-03-none-promoted
kind: what
title: "MODEL_CATALOG \u2014 Blue/red candidate batch evaluated 2026-07-03 \u2014\
  \ none promoted"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "Blue/red candidate batch evaluated 2026-07-03 \u2014 none promoted"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.623596
updated_at: 1784946220.623596
---

Eight candidates pulled and evaluated against the EXEC_SEC_FULL_COVERAGE_V1.md full-coverage run (which
exposed a real detection gap: sylink/sylink:8b, the auto-blueteam incumbent, scored f1=0 on 69/70
scenarios outside AD). PROMOTE_POLICY=confirm — comparison only, no fleet config touched. Raw result JSON
files are committed under `tests/benchmarks/bench_security/results/` (fleet-validation
`sec_full_red_20260703T081509Z.json` / `sec_full_purple_20260703T082741Z.json`) and
`tests/benchmarks/bench_security/results/candidates/` (per-candidate blue/red runs) — this summary is a
guide to that data, not a replacement for it. Ollama models removed post-eval (disk reclaim; none
promoted, so none need to stay pulled). See git history (commits 9eb53c4..b763301, plus the
candidate_eval.py path-sanitization fix) for the harness fixes this batch also surfaced and repaired
(purple mode ignoring --all-scenarios, AD blue telemetry always synthetic, self-index/stage2 file
discovery, candidate-eval --force for quality-over-speed evaluation, a result-file write bug that
silently dropped RedTeamLab-redteam-v5's first run).
