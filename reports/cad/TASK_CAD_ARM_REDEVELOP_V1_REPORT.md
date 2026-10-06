# TASK_CAD_ARM_REDEVELOP_V1 — run report

## Phase table
| Phase | Status | Evidence |
|---|---|---|
| P0 | PASS | arch gate; build123d 0.11.1 arm64; 8/8 oracles PASS (arm64 Darwin); B0 baseline below |

## P0 evidence
- HEAD at start `3b9f9d8b` (task authored against `d4cac6ec`); all 9 anchors matched once.
- Host arm64; Docker arch arm64; ollama arm64; OCP `.so` Mach-O arm64; build123d-mcp 0.3.90.
- Deviation: cad extra pins carry `; python_version >= '3.11'` (build123d-mcp needs >=3.11; project floor is 3.10, so `uv lock` failed without it).
- `lib3mf` on macOS is a universal2 wheel (includes arm64); linux/aarch64 uses `py-lib3mf` by marker.
- Sync used `uv sync --all-extras` (repo norm per scripts/ci_local.sh); plain `--extra cad` would uninstall other extras.
- B0 `auto-cad` block (rollback target): `reports/cad/B0_auto-cad_block.yaml`.

## B0 (auto-cad, qwen3-coder:30b-a3b-q4_K_M-ctx16k, 3 reps x 8 tasks)
mean 0.688 · PASS rate 0.375 · validity 0.958 · median 34.0 s.
PASS 3/3: plate_4holes, grommet_plate, countersunk_plate. 0/3: enclosure, l_bracket, flanged_bushing, hex_standoff, spur_gear.
Artifacts: `tests/benchmarks/results/cad_gauntlet_v2_B0_20261006T160659Z.{json,md}`.

## P1 — dedicated arm64 CAD image: PASS
- OpenSCAD branch: **nightly-manifold**. OBS `home:t-paul/Debian_13/arm64/` serves `openscad-nightly_20261005T003339...arm64.deb`; installed via signed-by keyring. `openscad-nightly --version` = `2026.10.05.nightly`; `--backend` lists CGAL/Manifold (Manifold default).
- Arch: image `Architecture`=arm64; `uname -m`=aarch64; OCP `.so` = `OCP.cpython-311-aarch64-linux-gnu.so`; build123d 0.11.1, vtk 9.7.1, build123d-mcp 0.3.90.
- Oracles in container: 8/8 PASS (machine=aarch64 system=Linux).
- Manifold vs CGAL (64-sphere difference on 60x60x20 cube, same binary): CGAL 68.1 s, Manifold 0.53 s.
- `PYOPENGL_PLATFORM=osmesa` kept in compose; `VTK_DEFAULT_OPENGL_WINDOW` not added (no VTK render path exercised until P2).
- Dockerfile.mcp: removed `openscad`, `libosmesa6`, CAD pip layers, micromamba block. Grep of portal/portal_mcp/portal_channels outside portal/modules/cad for trimesh|pyrender|matplotlib|stl|numpy_stl|jsonschema imports: none.
- capabilities.py: conda hooks removed; probes added (`openscad_bin/version/backend`, `build123d_mcp`, `arch`; `platform` key renamed, nothing read it); `engine` added via uncached `cad_status()` (served by `/capabilities`).
- Fact unit `unit-fact-dockerfile-index` updated (8 Dockerfiles; check BS claim).
- Unit tests `-k "cad or scad or mesh"`: 77 passed.

## P2 — build123d engine bridge on :8926: PASS
- Payloads P2-A/B/C written (checksums match); fragment merged into the cad_render manifest (4 -> 10 entries) and deleted. `sync_cad_geometry_schema.py` preserves `cad_*` entries (no script change needed).
- Wired: 6 POST routes via factory, `start_engine` in `__main__`, `--backend=manifold` when `CAD_OPENSCAD_BACKEND=manifold`, docstring updated.
- Live: `/capabilities` -> engine:true, build123d:true, arch:aarch64, openscad_backend:manifold. Tools list shows the 6 cad_* tools.
- plate_4holes via cad_build -> cad_finalize: ok, printability 0 findings, step/stl/script/png URLs published through OWUI (`/api/v1/files/...`); STL graded PASS by `grade_mesh`.
- Pipeline `/admin/refresh-tools`: 153 tools registered, includes cad_build/execute/measure/find_holes/render/finalize.
- mypy: 161 pre-existing errors elsewhere in portal/, unchanged by this phase.

### P2 security review (automated, post-commit) — dispositions
- Engine inherited the server env (incl. `OWUI_API_KEY`) while running model-authored code: **fixed** — engine now spawns with an explicit allowlist (`_ENGINE_ENV_ALLOWLIST`), unit-tested.
- `/tools/cad_*` routes unauthenticated: **acknowledged, unchanged** — same convention as every fleet MCP `/tools/*` route (host port bound to 127.0.0.1; reachable only from the compose network). The engine additionally rejects `os`/`subprocess`/socket/pathlib imports in executed code (verified live: `import os` -> SecurityError). Residual: the parent process still holds `OWUI_API_KEY` in its own environment.

## P3 — generate_part: same IR, BREP backend: PASS
- Goldens first: 82 IR inputs (the 10 CORPUS items + one per face/feature/edge/CSG/parameter variant, all 6 faces) captured from unchanged HEAD into `tests/data/cad_scad_golden/` (commit d4805a2e). After the split, **all 82 emit byte-identical SCAD** (`tests/unit/test_scad_golden.py`).
- Split: `part_plan.py` (EmitError, validation, parameters, face frames, pattern expansion, plan dataclasses, `plan_part`) — moved mechanically, not rewritten; `scad_emitter.py` is now a thin `render_scad` backend that re-exports the public names; `b123d_emitter.py` is the BREP backend. Pocket/rib/shell cutters and hole/standoff positions are resolved once in the plan.
- Parity (container, OpenSCAD nightly Manifold; volumes mm^3, genus b3d/scad):

| part | vol b3d | vol scad | dV % | genus |
|---|---|---|---|---|
| plain_plate | 6000.0 | 6000.0 | 0.00 | 0/0 |
| grommet_plate | 8607.9 | 8627.5 | -0.23 | 3/3 |
| drilled_standoff | 8345.4 | 8344.6 | 0.01 | 0/0 |
| open_enclosure | 13632.0 | 13632.0 | 0.00 | 0/0 |
| mounting_bracket | 2880.0 | 2880.0 | 0.00 | 0/0 |
| vented_panel | 3600.0 | 3600.0 | 0.00 | 5/5 |
| cylindrical_adapter | 7687.4 | 7668.7 | 0.24 | 1/1 |
| chamfered_block | 6926.5 | 6927.7 | -0.02 | 0/0 |
| filleted_block | 6942.9 | 6907.6 | 0.51 | 0/0 |
| gearish_disc | 5765.6 | 5751.5 | 0.24 | 8/8 |

  Extents match the corpus expectation within 0.05 mm; 96 emitter+golden tests pass inside the arm64 container too. Tolerances were not loosened.
- Sweep of all 82 golden inputs through the BREP backend: 80 build to one valid solid. The 2 exceptions are declared **kernel_gap** (error points the model at `cad_build`): Tier-B `linear_extrude`/`rotate_extrude` (IR has no 2D primitives, so the SCAD form is also degenerate) and a base carrying both fillets and chamfers (second op would target the first op's blended edges). To record in KNOWN_LIMITATIONS (P6).
- Semantics note: the SCAD fillet envelope always rounds a box's vertical edges (any `edges` value); the BREP backend matches that for fillets, not for chamfers. The schema's `edges` enum is `all|top|bottom` (no `vertical`).
- Mesh artifact: OCC tessellation of an all-edges-filleted box leaves 8 zero-area sliver triangles in the STL, so trimesh reports it non-watertight although the BREP solid is valid. The parity test drops degenerate faces; the sealed grader does not, so a fillet-all part could grade INVALID from the engine's STL. Watch in P5.
- `generate_part` tool + route + manifest entry; `sync_cad_geometry_schema.py` now keeps one schema for `generate_scad` and `generate_part` (parity test extended). Live: `grommet_plate` IR -> `/tools/generate_part` -> step/stl/png/script URLs, graded by `grade_mesh` = **PASS** (volume 8609.7, genus 3).

### P3 security review (automated, post-commit) — disposition
- Parameter names / part name were interpolated into the generated build123d script: **fixed** — parameter names must match `^[A-Za-z_][A-Za-z0-9_]{0,63}$` (schema `propertyNames` + enforced in `resolve_parameters`, so both backends reject it), and comment text goes through an escaping helper (`repr`) so newlines/CR/U+2028 cannot end the comment. Tests: `test_user_strings_cannot_inject_script_lines`, `test_parameter_names_must_be_identifiers`. (Not a new privilege — `cad_build` already runs model-authored code in the import-restricted engine — but the IR path should not be a bypass of the structured-input contract.)
- Test change: `test_auto_cad_prompt_example_validates_against_schema` extracted a JSON example from the old prompt; the P4-A prompt has none, so it now validates the schema's own `examples`.

## P4 — rewire auto-cad + challenger seat (config part)
- **Context decision (measured via Ollama `prompt_eval_count`, qwen3-coder tokenizer):** system prompt 566 tok + 20 tool schemas 4627 tok = **5193 tok fixed = 31.7 % of 16384** (the old toolset: 2775 tok total). Over the 25 % rule -> created `qwen3-coder:30b-a3b-q4_K_M-ctx32k` via `apply-params` (`ollama show` -> `num_ctx 32768`), registered in `config/backends.yaml` (group + oMLX alias, mirroring ctx16k); `context_limit: 32768`, `predict_limit` kept 16384.
  - Side effect handled: `apply-params` also re-tagged 3 unrelated workspaces (security council members); I reverted those 3 `model_hint` edits and `ollama rm`'d the 3 derived tags it had created (bases untouched).
- **auto-cad preflight (pipeline, request-level `tool_choice:auto`, 6 identical requests "40x20x5 plate, two 4 mm holes"):** 6/6 delivered through real tool calls with STEP+STL URLs (5/6 also PNG in the reply text); no hallucinated tool names. 2 of the first 6 attempts were aborted by oMLX's memory guard (`process memory limit exceeded`) before any tool call and were re-run. Decision: **kept `tool_choice: required`** (B0-comparable; gauntlet relaxes to auto after the first artifact); `tool_choice_verified: true` retained with a dated comment.
- **bench-qwen38-cad** (module eval): clone of the new auto-cad tools/prompt/sampling on `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (present in `ollama list`; compliance seat tag), `context_limit 32768`, `think:false`, `tool_choice:auto`. Preflight 6/6 valid tool names, 2/6 built-and-delivered, 4/6 opened with `cad_find_holes` on an empty session — recorded as a behaviour risk for the gauntlet to measure. Third arm `bench-deepwen-cad` **skipped**: `portal5/deepwen-3.6:q4.5-moq-ctx32k` is not in `ollama list` (and not named in the closeout register) — the task makes it conditional on presence; nothing pulled or re-added.
- `description`, `tools` (generate_scad removed from auto-cad only; +generate_part, +6 cad_*), `system_prompt_append` = P4-A verbatim (sha256 verified). `./launch.sh sync-config` run; pipeline image rebuilt (it bakes `config/`) and `/admin/refresh-tools` -> 154 tools.
- Personas `caddesigner` / `printabilityengineer`: build123d-first guidance (generate_part -> cad_build -> verify -> cad_finalize; OpenSCAD only on explicit request; cad_finalize printability findings quoted). `preferred_models` moved to the ctx32k tag. Persona snapshot (`owui_persona_presets_snapshot.json`) had no generator, only the test's builder; regenerated the two entries with that builder (8 lines changed). `preset_resolution_snapshot.json`: 3 tool lists updated (auto-cad + the two personas).
- Tests/docs touched by the rewire: `tests/acceptance/s17_cad_render.py` (manifest expectation + S17-13 `generate_part`, S17-14 `cad_build`; the two `generate_scad` cases kept as the SCAD-fallback), `tests/data/uat_catalog_g_auto_cad.json` (WS-CAD-02, P-CAD-01, P-CAD-02 accept build123d/BREP evidence; WS-CAD-01 stays an explicit-OpenSCAD fallback case), `bench_prompts_workspace_prompt_map.json`, `config/MODEL_CATALOG.md` (ctx32k entry, stale ctx16k/auto-cad statement), readme wiki units' workspace counts (22->23 bench, 57 total).
- `generate_part` is also an `@mcp.tool()` (S17 drives tools through the MCP protocol); the `cad_*` bridge tools are HTTP-only by design.
- Live: S17 (live stack) passes incl. S17-13/14.
- **End-to-end `flanged_bushing` via the pipeline (`auto-cad`, OWUI path): 0/3 delivered** — outputs: a malformed script as text; "Let me try again" text; a raw `<function>` block as text. No artifact, so nothing to grade. This is a model/tool-loop finding (after a failed `cad_build` the incumbent narrates instead of re-calling; the oMLX qwen3_coder parser also leaks text-written calls, cf. KNOWN_LIMITATIONS P5-OMLX-QWEN3CODER-TOOLTEXT-001), not an infra fault: B0 also scored 0/3 on this part. The task's "confirm STL grades PASS" acceptance sub-check is therefore **not met for the incumbent** — recorded as measured; P5's gauntlet quantifies it per task. Note the gauntlet driver calls Ollama directly while the pipeline routes this tag through oMLX, so the two paths can differ.
