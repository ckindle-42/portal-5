# SIMPLIFY_UNWIRED_DISPOSITION — C1 Step A, TASK_PORTAL_SIMPLIFY_V1

**Input:** `python3 scripts/complexity_report.py` census → 23 unwired scripts.
Each row: evidence (code refs, git history, docstring) and exactly one disposition.

## DELETE — superseded / completed one-shot, with positive evidence

| Script | Evidence | Disposition |
|---|---|---|
| `scripts/_archive/mlx-retired-3a0c58e/mlx-readiness.py` | MLX chat-inference tier retired at `3a0c58e`; file lives under the explicit `_archive/mlx-retired-3a0c58e/` marker dir; zero code refs; unit archived in R2 | **DELETE** |
| `scripts/_archive/mlx-retired-3a0c58e/mlx-switch-benchmark.py` | same — retired MLX proxy measurement, zero code refs | **DELETE** |
| `scripts/_archive/mlx-retired-3a0c58e/patch-mlx-templates.py` | same — retired MLX dependency patching, zero code refs | **DELETE** |
| `scripts/_archive/mlx-retired-3a0c58e/patch-mlx-threads.py` | same — retired MLX thread-patch burden, zero code refs | **DELETE** |
| `scripts/migrate_to_portal_yaml.py` | one-shot migration to `config/portal.yaml`; migration complete; referenced only by its own (archived) wiki unit; git history shows it ended at the portal.yaml landing | **DELETE** |
| `scripts/v2_corpus_baseline.py` | requires a detached checkout of the pre-V3 commit — a one-time baseline procedure, not a repeatable tool; zero code refs | **DELETE** |
| `scripts/check_docstrings.py` | unwired docstring-presence gate; C6 removes prose (incl. non-contract docstrings), so a gate *requiring* a docstring on every function would fight the program's own goal; the KEEP-contract half is enforced by the spine surface units | **DELETE** |

## OPERATOR-INVOKED — a human runs it; add to `scripts/OPERATOR_TOOLS.md`

| Script | Evidence | Disposition |
|---|---|---|
| `scripts/gen-image.py` | CLI for rapid image generation via the ComfyUI MCP; documented in canonical `unit-readme-image-generation…` and `unit-comfyui-setup-step-3-use` | **OPERATOR-INVOKED** |
| `scripts/gen-video.py` | CLI for video generation via the video MCP; referenced by `unit-comfyui-setup-step-3-use` | **OPERATOR-INVOKED** |
| `scripts/caldera_emulate.py` | live Caldera adversary-emulation lane; `git c26b84ad` wired it through collect→ship→wait; documented in the corpus-injection units | **OPERATOR-INVOKED** |
| `scripts/lab_splunkbase_install.py` | installs Splunkbase apps BOTS needs; referenced by `unit-corpus-injection-inside-lxc-301…` | **OPERATOR-INVOKED** |
| `scripts/lab_discover.py` | read-only lab host discovery (Phase 0 of live-lab execution); referenced by `unit-SEC_BENCH-execution-transport` | **OPERATOR-INVOKED** |
| `scripts/execute_preflight.py` | ground-truth preflight for bench/sec/acceptance sessions; referenced by five canonical bench-execute units (failure-playbook, non-negotiables, v4 ground-truth…) | **OPERATOR-INVOKED** |
| `scripts/security_capture_recipes.py` | capture-recipe tooling for the combined red corpus; referenced by `unit-security-combined-corpus-validation` | **OPERATOR-INVOKED** |
| `scripts/security_corpus_report.py` | combined-corpus readiness report; referenced by the same unit | **OPERATOR-INVOKED** |
| `scripts/security_replay_verify.py` | replay-into-Splunk verification gate; referenced by the same unit | **OPERATOR-INVOKED** |
| `scripts/update_grafana_acceptance.py` | updates `portal5_acceptance.json` Grafana dashboard; Step E consolidates it; referenced by the v9 results-dashboard unit | **OPERATOR-INVOKED** (kept through Step E) |
| `scripts/update_grafana_benchmarks.py` | updates `portal5_benchmarks.json`; Step E consolidates it; referenced by v4 your-role/results-dashboard units | **OPERATOR-INVOKED** (kept through Step E) |
| `scripts/update_grafana_uat.py` | updates `portal5_uat.json`; Step E consolidates it | **OPERATOR-INVOKED** (kept through Step E) |
| `scripts/blend_acceptance_results.py` | blends `ACCEPTANCE_RESULTS.md` from git history + live file — operator run after acceptance reruns | **OPERATOR-INVOKED** |
| `scripts/verify_proxmox_mcp.py` | quick Proxmox MCP verification (no Docker) | **OPERATOR-INVOKED** |
| `scripts/collapse_snapshot.py` | read-only surface snapshot for `BUILD_PROGRAM_COLLAPSE_V1.md`; still referenced by that sibling program's doc | **OPERATOR-INVOKED** |
| `scripts/spine_census.py` | the R0 census tool — this program's own instrument, used every phase | **OPERATOR-INVOKED** |

## WIRE — none this round

Every unwired script that a machine should invoke is either documented as an
operator workflow in the canonical bench/sec/corpus units (which is a real entry
point) or is one of the three Grafana updaters Step E consolidates into the
shared `scripts/lib/grafana_panels.py`. There is no script that *should* be
auto-wired into `validate_system.py` or a Makefile target but currently is not.

## Totals

- **DELETE:** 7 scripts
- **OPERATOR-INVOKED:** 16 scripts (→ `scripts/OPERATOR_TOOLS.md`)
- **WIRE:** 0

Effect on census: `unwired_scripts 23 → 0` after `OPERATOR_TOOLS.md` is written
(the manifest names every surviving script, making each referenced).
