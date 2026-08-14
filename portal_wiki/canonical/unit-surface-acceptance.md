---
id: unit-surface-acceptance
kind: mixed
title: "Acceptance harness \u2014 staged live-stack scenario suite"
sources:
- type: code
  path: tests/acceptance/*.py
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785882800.0
updated_at: 1785882800.0
---

The acceptance suite is the live-stack harness that proves Portal 5 still
serves. `cli.py` is the operator entry point, `_common.py` the shared section
infrastructure, `runner.py` the canonical sequence with its skip rules, and
`results.py` the run-summary writer. The `s*` modules are the staged scenario
map — one probe per stage, each driving the live stack.

## Why

The harness is one contract spread across four shared modules and a staged map
of section modules, and mirroring it per stage hid where the real decisions
live. A section failure means the stack or its configuration is broken, never
the test — the harness exists to attribute breakage to the platform, so that
attribution belongs in one subsystem unit, not a per-section retelling.
Section selection by `S`-identifier with loud rejection of unknown ids keeps a
typo from silently running nothing.

## Interfaces

`cli.py` parses the `--section` argument and hands the resolved list to
`run_sections`. `runner.py` maps each `S`-identifier in `ALL_SECTIONS` to its
section function and enforces the canonical order, calling
`_memory_cleanup` before the memory-heavy phases. `_common.py`
re-exports `record` and `_log` from `results.py` and supplies `_chat`, `_mcp`,
`_await_ollama_ready`, and `_git_sha`. `results.py` writes `R` entries into
`_log`, classifies failures through `_classify`, and renders
`ACCEPTANCE_RESULTS.md` via `_write_results`.

## Gotchas

New section-specific behavior belongs in the section module, never in
`_common.py` — the shared module is the single import point, not a junk
drawer. Skip rules are deliberate: opt-in lanes such as `S18` degrade to a
`WARN` when `SANDBOX_LAB_EXEC` is unset rather than failing a normal CI run. A
`WARN` is a real warning, not a pass.
