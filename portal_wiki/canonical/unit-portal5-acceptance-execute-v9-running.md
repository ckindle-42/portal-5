---
id: unit-portal5-acceptance-execute-v9-running
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Running"
sources:
- type: code
  path: tests/portal5_acceptance_v6.py
- type: code
  path: tests/acceptance/cli.py
- type: code
  path: tests/acceptance/runner.py
- type: code
  path: tests/acceptance/s03_routing.py
- type: code
  path: tests/acceptance/s06_security_workspaces.py
- type: code
  path: tests/acceptance/s10_personas_ollama.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.695101
updated_at: 1784946220.695101
---

The runner entry point is `tests/portal5_acceptance_v6.py`, which is a thin
wrapper: it re-exports `WORKSPACE_PROMPTS` and the related signal dicts and
calls `acceptance.cli.main`, with all real behavior in
`tests/acceptance/{cli,runner,results,_common}.py`. Before launching, confirm no
newer runner exists by listing `tests/portal5_acceptance_v*.py`.

Section selection is handled by the `--section` argument in
`tests/acceptance/cli.py` and by `_parse_sections` in
`tests/acceptance/runner.py`, which accepts a single id, a comma-separated list,
an inclusive numeric range such as `--section S0-S5`, or `ALL`. The
authoritative section list is the `tests/acceptance/s*.py` file set on disk,
each wrapped by a function in the runner's `ALL_SECTIONS` map. Key sections for
the current surface: S3/S3a routes the production catalog; S6 covers the
`auto-security` workspace and its variants; S10 and S10c exercise personas (S10
via Ollama chats with expected-model checks, S10c via the compliance fixture);
S17 covers CAD render; S21 exercises the LLM intent router; S23 checks model
diversity in the Ollama catalog.

## Why

The runner is deliberately a thin entry point so the section files stay the
authoritative catalog and the CLI stays stable across runner versions. Section
selection supports ids, comma lists, and ranges because operators frequently
re-run just the sections relevant to a change rather than the whole suite,
which takes a long wall-clock time. Confirming the newest runner up front
prevents executing an outdated suite.
