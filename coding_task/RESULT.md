# RESULT — lane/cad-openscad-arm-image

Switch `Dockerfile.cad` from the openSUSE OBS `openscad-nightly` apt repo (repeated
mirror-sync build failures) to the official `openscad/openscad:dev` base image
(native `linux/arm64`, Debian 13 trixie, OpenSCAD 2026.11.16, Manifold built in).

## WHAT CHANGED

- `Dockerfile.cad` — `FROM openscad/openscad:dev`; OBS keyring/repo/`openscad-nightly`
  block and `gnupg` dropped; apt now installs `python3`+`python3-venv` (base ships no
  Python; trixie python is 3.13) plus the same GL/offscreen set (`libgl1`, `libegl1`,
  `libosmesa6`, `libglib2.0-0`, `libxrender1`, `libxt6`, `libx11-6`, `curl`,
  `ca-certificates`); clean venv at `/opt/venv` on `PATH` (PEP 668 system Python) so
  `python` in ENTRYPOINT CMD resolves; `ENV OPENSCAD_BIN=openscad
  CAD_OPENSCAD_BACKEND=manifold`; all pip pins byte-identical to before (incl.
  `starlette>=1.3.0` — `test_standalone_installers_require_safe_starlette` count kept);
  `ARG PORTAL_BUILD_SHA` + LABEL, arm64 `uname -m` guard, portal user,
  `/app/data/generated`, `mcp-entrypoint.sh`, ENTRYPOINT/CMD unchanged.
- `portal/modules/cad/PLATFORM.md` — OpenSCAD table row + branch paragraph rewritten
  (official base, lowercase `--backend=manifold` accepted, OBS superseded 2026-11-22);
  the dated 2026-10-06 verification block annotated as evidence from the superseded
  image.
- `portal_wiki/canonical/unit-module-cad.md` — Platform paragraph: OpenSCAD now the
  official `openscad/openscad:dev` base (OBS repo replaced, mirror sync failures).
- `tests/unit/test_dependency_drift.py` — new
  `test_cad_image_takes_openscad_from_official_base` (regression net: asserts official
  `FROM`, no `download.opensuse.org`, `ENV OPENSCAD_BIN=openscad
  CAD_OPENSCAD_BACKEND=manifold`).
- `coding_task/RESULT.md` — this file.

## EVIDENCE (all run in this worktree; UV env is the main checkout's synced venv)

- Official image probed directly on this host (`docker run --rm openscad/openscad:dev`):
  `aarch64` · Debian GNU/Linux 13 (trixie) · `/usr/local/bin/openscad` · `OpenSCAD
  version 2026.11.16` · `--backend arg … 'CGAL' (old/slow) or 'Manifold' (new/fast)`.
  `openscad --backend=manifold -o t.stl cube.scad` exits 0 and writes a valid STL
  (LOWERCASE accepted — `portal/modules/cad/tools/cad_render_mcp.py:325` sends exactly
  `--backend=manifold`); uppercase also accepted. No python3 in base (verified).
- Full CAD pip set installed in a throwaway container from that base (python3-venv +
  venv): `PIP_INSTALL_OK` — build123d 0.11.1, cadquery-ocp-novtk 7.9.3.1.1, vtk 9.7.2,
  numpy 2.5.5, scipy 1.18.1, matplotlib 3.11.2, pillow 13.0.0, quiddity 0.3.12;
  `import build123d` → `BUILD123D_IMPORT_OK 0.11.1` (Python 3.13.5).
- PyPI cross-check: build123d 0.11.1 `requires_python <3.15,>=3.10`, needs
  `cadquery-ocp-novtk<8.0,>=7.9`; 7.9.3.0 ships `cp313 manylinux_2_31_aarch64` wheels;
  build123d-mcp 0.3.90 `requires_python <3.15,>=3.11`, `vtk>=9.3`.
- Regression net: test FAILS against HEAD's `Dockerfile.cad`
  (`assert 'FROM openscad/openscad:dev' in text` → FAILED), PASSES against the new one.
- `UV_PROJECT_ENVIRONMENT=/Users/chris/projects/portal-5/.venv uv run pytest -q
  tests/unit/ -k "cad"` → `64 passed, 3066 deselected`.
- Full per-commit gate: `3108 passed, 22 skipped` · ruff check `All checks passed!` ·
  ruff format `1737 files already formatted` · `mypy portal/` → `Success: no issues
  found in 733 source files` · complexity `GATE OK` (all totals within ceilings).

## ORCHESTRATOR RUNS (live)

```bash
./launch.sh rebuild && ./launch.sh up     # rebuilds portal5-mcp-cad-render from Dockerfile.cad
docker exec portal5-mcp-cad-render sh -lc \
  'uname -m; openscad --version; openscad --help 2>&1 | grep -i backend; python -V; python -c "import build123d, vtk; print(build123d.__version__, vtk.VTK_VERSION)"'
curl -sf http://localhost:8926/capabilities | python3 -m json.tool   # openscad_bin/version/backend keys
curl -sf http://localhost:8926/health
```

Worked = image Architecture `arm64`, container `aarch64`, `OpenSCAD version 2026.11.16`
with `--backend` offering CGAL/Manifold, venv python 3.13, build123d 0.11.1 importable
as the `portal` user, `/capabilities` reports `openscad_backend: manifold` and live
`engine`. Not worked = build fails on the pip layers (wheel gap), container starts with
`openscad binary not found` in capabilities (OPENSCAD_BIN/PATH wrong), or a render
rejecting `--backend=manifold`.

## UNPROVEN

- Full image build (`docker build -f Dockerfile.cad`) and service startup against the
  live stack — orchestrator-only; the throwaway container install + import prove the
  pip layer, not the built image.
- A real `render_openscad` / `generate_scad` render through the running MCP service
  (needs the live stack).
- VTK offscreen GL render (pyrender/VTK paths) inside the new image — never exercised;
  GL libs are installed per the keep-list but the headless render is proven only by the
  orchestrator's rebuild + a live render.
- `su`-dropped portal user resolving `/opt/venv/bin/python` via preserved `PATH` —
  reasoned from `scripts/mcp-entrypoint.sh` (non-login `su -s` preserves environment),
  not run in the built image.

## OPEN / RISK

- `openscad/openscad:dev` is a moving tag (like the nightly it replaces); it pins
  2026.11.16 today. If upstream breaks ABI later, pin by digest.
- PLATFORM.md still says `cadquery-ocp-novtk` ships a `manylinux_2_28_aarch64` wheel —
  build123d 0.11.1 resolves 7.9.x whose tag is `manylinux_2_31_aarch64`. Pre-existing
  imprecision, unrelated to this switch; left untouched (minimum change).
- The stale-`.mypy_cache` trap: the shared venv's editable install previously pointed at
  a deleted worktree (`portal-5-dflash-ab-mkdir-fix`), and a stale `.mypy_cache` produced
  650 phantom errors. `rm -rf .mypy_cache` in THIS worktree fixed it here; the MAIN
  checkout (`/Users/chris/projects/portal-5`) likely still carries that stale cache —
  `rm -rf .mypy_cache` there before trusting a mypy failure. Also note this lane's
  `uv sync` repointed the shared venv's `portal-5` editable install from that deleted
  tree to this worktree (the dispatcher's `UV_PROJECT_ENVIRONMENT` choice; only the
  project package changed — all libraries already matched the lock).
- Historical `reports/cad/TASK_CAD_ARM_REDEVELOP_V1_REPORT.md` still mentions
  `openscad-nightly` — dated run report, intentionally not rewritten.
- Complexity gate reported-not-gated drift (prose 61,560 vs baseline 60,282; god_funcs
  571 vs 546) predates this lane; ceilings not exceeded.
