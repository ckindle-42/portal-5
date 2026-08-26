---
id: unit-surface-binary-research
kind: mixed
title: "Binary research harness — project-directory RE workspace + toolchain MCP"
sources:
- type: code
  path: portal/modules/binary_research/**/*.py
claims: []
confidence: high
tags:
- authored-v1
- module
- binary-research
created_at: 1787786654.0
updated_at: 1787786654.0
---

The binary research harness is a CLI-first agent loop for static reverse
engineering, split into an infrastructure layer and a per-item workspace
layer. `tools/binresearch_mcp.py` owns the `portal5-binresearch` container and
exposes `re_exec`, `re_python`, and `re_tools` over MCP + REST on port 8930,
mounting one project subfolder at a time from the DinD-side projects root.
`harness/workspace.py` resolves a project directory (`resolve_project`),
creates its static structure (`init_project`), checks it (`is_initialized`),
and appends turns to `trace.jsonl` via `TraceLog`. `harness/policy.py`'s
`Policy` jails all file access to that project directory and gates network,
artifact-execution, and host-escape commands through `check_bash`.
`harness/re_client.py`'s `REClient` is the thin HTTP client the harness uses
to reach the MCP. `harness/tools.py` implements the four model-facing tools
(`tool_read`, `tool_write`, `tool_edit`, `tool_bash`) behind `run_tool`.
`harness/verifiers.py` discovers and runs `verifiers/*.sh`/`*.py` scripts and
grades the aggregate as a `Verdict`. `harness/llm.py`'s `complete` is the
OpenAI-compatible model socket, and `harness/loop.py`'s `Budget` and `run`
drive the agent loop until a verdict is ALL PASS or the budget is exhausted.

## Why

The two layers are kept structurally separate because they have different
lifecycles: the MCP and container are installed once and stay usable for
every future research item, while each item's directory (artifacts,
hypotheses, evidence, verifiers) is disposable and item-specific. Routing all
container access through `re_exec`/`re_python` rather than a shared Docker
socket means a brand-new project is mountable with zero per-project wiring —
the MCP just binds `<projects-root>/<name>` into the container by name. The
verdict logic in `verifiers.py` treats a single passing check as insufficient
completion (`PARTIAL PASS` is not done) specifically so the model cannot
declare victory on a lucky first probe; ALL PASS across every registered
verifier is the only stopping condition the loop honors.

## Gotchas

`Policy.check_bash` denies executing anything under `artifacts/` unless
`allow_execution_of_artifacts` is set, because RE workspaces routinely contain
untrusted samples — the harness is for static inspection, not detonation.
`tool_bash`'s `target='host'` escape hatch exists only for macOS Mach-O tools
(`otool`/`codesign`/`lipo`) that have no Linux equivalent in the RE container,
and is itself gated by `allow_host_exec` so it is never the default path.
