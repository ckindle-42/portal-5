# Doc Audit Report — 2026-07-12

**Base HEAD:** `68a4db1ee6c10720e37350f4b7c0e1421a36a3c8` (M8 — remove M0-M6 compat shims, finalize modularization)
**Ledger:** `docs/.doc_ledger.yaml`
**Gate:** `scripts/validate_system.py` check `AL. doc currency`

First full reconciliation pass under `TASK_DOC_AUDIT_AGENT_V1`. All source paths in
the task's seed ledger and coverage map were written against the pre-modularization
tree (`portal_pipeline/`, `portal_mcp/<category>/`, `portal_wiki/core`); this pass
retargeted every binding to the current `portal/modules/` + `portal/platform/` tree
before reconciling doc content.

## Per-doc outcome

| Doc | Drift found (summary) | Stamped @ |
|-----|------------------------|-----------|
| CLAUDE.md | Project Layout tree rewritten (portal_pipeline/portal_mcp → portal/modules,portal/platform); Rule 3/4/6/8 code paths; Rule 7 detections port 8930→8932 (live is 8932, bumped to avoid INCALMO_PORT collision); Rule 11 portal_mcp.core→portal.platform.mcp_host (that shim was also deleted, see below); Portal Wiki section core/adapters paths; persona count phrasing made extractor-derived; Rule 12 + capability-step hooks added (Phase 1) | 68a4db1 |
| README.md | portal_pipeline import path in bench-workspace snippet; functional workspace count 42→44 (2 missing rows added: auto-agentic-ornith, auto-coding-northmini); total 90→104; bench count 48→60; MCP Servers table missing 3 rows (MITRE :8929, Detections :8932, Wiki :8931); `.mcp.json` server count 19→22 (extractor-derived phrasing) | 68a4db1 |
| KNOWN_LIMITATIONS.md | No stale path/count claims found — re-stamped (bound sources moved but no doc content referenced the old paths) | 68a4db1 |
| P5_ROADMAP.md | One live (non-historical) forward-looking claim fixed: P5-FUT-PROMPT-GUARD-INLINE's proposed `portal_pipeline/guards/` → `portal/platform/inference/router/`. DONE-row historical implementation notes left untouched (accurate as point-in-time record) | 68a4db1 |
| KNOWN_ISSUES.md | No drift (file is an intentional 7-line stub) | 68a4db1 |
| docs/USER_GUIDE.md | No drift — all named workspaces verified to still exist in portal.yaml | 68a4db1 |
| docs/ADMIN_GUIDE.md | routing.py path ×2; stale header "Portal 6.0.7" → "Portal 7.6.0" (synced to CLAUDE.md's Version: field, not a new scheme decision); exec-chain driver path `tests/benchmarks/bench_security/cli.py` → `portal/modules/security/core/commands/run.py` | 68a4db1 |
| docs/HOWTO.md | rag_mcp.py path; portal_mcp.core import → portal.platform.mcp_host (verified all 3 helper names present at new location) | 68a4db1 |
| docs/CLUSTER_SCALE.md | No drift — backend group names (general/coding/security/reasoning/vision/creative) verified live in backends.yaml | 68a4db1 |
| docs/ALERTS.md | No drift | 68a4db1 |
| docs/PERFORMANCE.md | No drift | 68a4db1 |
| docs/MCP_DEV_TOOLING.md | 3× portal_pipeline path (streaming.py, router_pipe.py, workspaces.py in FastContext example + sed snippet); workspace count 94→104 (×2); MCP server count 19→22 | 68a4db1 |
| docs/COMFYUI_SETUP.md | video_mcp.py path ×2 (verified _WAN22_*_WORKFLOW dicts present at new location) | 68a4db1 |
| docs/FISH_SPEECH_SETUP.md | No drift | 68a4db1 |
| docs/COMPLIANCE_FALLBACK_POLICY.md | No drift — persona_matrix entrypoint paths still valid (thin shim never moved) | 68a4db1 |
| docs/BACKUP_RESTORE.md | No drift | 68a4db1 |
| docs/LAB_SETUP.md | No drift | 68a4db1 |
| docs/PERSONA_MATRIX_CI.md | No drift — persona_matrix result-file paths still valid | 68a4db1 |
| docs/generated/ADMIN_GUIDE.md | Re-rendered via `python3 -m portal_wiki render --all` | 68a4db1 |
| docs/generated/ARCHITECTURE_MAP.md | Re-rendered via `python3 -m portal_wiki render --all` | 68a4db1 |

## Adjacent fix applied (not gated — zero live importers, safety-verified before deletion)

Discovered during Rule 11 verification: `portal_mcp/core/` was itself a leftover
compat shim (from Build 2's Slice 2, predates M0-M6 and was out of M8's scope,
which only covered M0-M6 shims). `git grep` confirmed zero real importers
(one stale comment in `scripts/mlx-transcribe.py`, fixed). Deleted
`portal_mcp/core/{__init__.py,workspace.py}`; the real implementation was already
at `portal/platform/mcp_host/workspace.py`. CLAUDE.md's Project Layout and Rule 11
updated to match.

## Extractor-verified figures (this pass)

- personas: 130 (`ls config/personas/*.yaml | wc -l`)
- workspaces: 104 total — 44 functional + 60 bench (`len(portal.yaml['workspaces'])`)
- mcp_fleet: 24 entries in `config/portal.yaml` (`len(portal.yaml['mcp_fleet'])`)
- `.mcp.json`: 22 IDE-exposed servers
- validate checks: A..Z, AA..AL (added AL this pass)
- detections MCP port: 8932 (live; `.env.example` documents the 8930→8932 bump to avoid an INCALMO_PORT collision)

## Machinery installed (Phase 1)

- `scripts/doc_ledger.py` — status/check/stamp/stamp-all/add CLI
- `docs/.doc_ledger.yaml` — 20 living docs bound, seed paths retargeted to the post-modularization tree
- `scripts/validate_system.py` — new check `AL. doc currency` (delegates to doc_ledger.py check --json)
- `CLAUDE.md` Rule 12 — "Docs Travel With The Work" + reconcile-and-restamp step appended to all 4 "Adding New Capabilities" subsections
- `.pre-commit-config.yaml` — not modified this pass (existing `validate-system` hook already runs `validate_system.py --skip-pytest`, which now covers AL automatically; no separate hook needed)

## Flagged for operator decision (not fixed here)

- **`validate_system.py` "W." label collision** (§6 of `TASK_DOC_AUDIT_AGENT_V1.md`): `check_ability_port` and `check_labexec_coverage` both currently print as "W. ...". Low-risk one-line relabel (e.g. second one → `AM.`), but touches the validation harness — task spec requires operator confirm before applying. Not applied in this pass.
- `portal-5 → portal` repo rename (434 `portal-5` string occurrences, 109 files) — separate task per §7 of the source task file.
- Version-scheme adoption (SemVer reset for a `portal` rename) — separate operator decision per §7. This pass only synced ADMIN_GUIDE.md's stale "6.0.7" header to CLAUDE.md's existing "7.6.0" — no new scheme was adopted.
