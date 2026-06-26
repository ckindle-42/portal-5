# Bench coverage audit — HEAD 6d98b97 (2026-06-26)

Snapshot of bench-instrument coverage against the live workspace catalog.
Run when counts drift; supersedes prior date-stamped audits.

## Counts (verified)

- Workspaces total: 90 (42 production + 48 bench)
- MCP fleet: 21 servers
- Models (registry): 10 (1 live + 9 retired)
- Personas: 130

## bench_tps.py discovery

`bench_tps.py` discovers bench workspaces dynamically from `portal.yaml`.
Bench workspaces are those with `id` starting with `bench-`. At HEAD,
48 bench workspaces exist. The pipeline_bench_skip list is empty.

## bench_security.py coverage

The security bench harness (`bench_security.py`) uses its own model registry
in `_data.py` (3,612 lines). This is a tightly-coupled scenario tree
containing prompts, scoring rubrics, and refusal patterns for the security
workspace fleet. Audit conclusion: leave as is — no natural decomposition
seam; the data structure is a coherent scenario graph that doesn't lift
cleanly to YAML.

## Action items

- None at HEAD. Counts are current.

## Re-audit cadence

Re-run when bench count drifts by >=3 workspaces or annually, whichever sooner.
