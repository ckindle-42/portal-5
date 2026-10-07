# CAD Module — Platform

## Standing rule: native means arm64

Anything executed natively on the Mac host (binaries, wheels, `.so`) or in Docker on it
(images built/pulled for `linux/arm64`) must be the ARM build. Verify with `uname -m` /
`platform.machine()` / `file` / `docker image inspect … --format '{{.Architecture}}'`.
x86_64 builds under Rosetta or emulation are not acceptable fallbacks — record a known
limitation instead. `Dockerfile.cad` enforces it at build time (`uname -m` must be
`aarch64`) and the compose service pins `platform: linux/arm64`.

## arm64 tier — the shipped image (`Dockerfile.cad`, service `mcp-cad-render`, :8926)

`mcp-cad-render` has its own image; OCP + VTK + scipy + OpenSCAD do not belong in the
shared `Dockerfile.mcp` that the other tool servers build from.

| Component | How it is installed | Why |
|---|---|---|
| build123d `0.11.1` | pip (`cadquery-ocp-novtk`, `manylinux_2_28_aarch64` wheel) | BREP kernel (OCCT) |
| build123d-mcp `0.3.90` `[http]` | pip | closed-loop CAD engine (execute / measure / validate / hole recognition / FDM printability / VTK render / STEP+STL export / per-handle sessions) |
| trimesh, pyrender, matplotlib, numpy-stl, jsonschema | pip | mesh validation + the CPU render fallback |
| OpenSCAD | `openscad-nightly` from the openSUSE OBS repo `home:t-paul/Debian_13` (arm64 build) | Manifold backend; Debian's own `openscad` is 2021.01, CGAL-only |

**Pins.** `build123d-mcp 0.3.90` requires `build123d>=0.10,<0.12`, so build123d is pinned
`0.11.1` (not 0.13). The same pins live in `pyproject.toml` (`cad` extra, with a
`python_version >= '3.11'` marker because build123d-mcp needs 3.11+) and in
`Dockerfile.cad`; keep them in sync. CadQuery is intentionally not installed: its OCP
variant conflicts with build123d's `cadquery-ocp-novtk`.

**The conda/micromamba layer is gone.** The old `P5-CAD-ARM64-001` limitation
("OCP has no arm64 wheels") was a pip-wheel artifact and is resolved: `cadquery-ocp`
now ships `manylinux_2_28_aarch64` and `macosx_11_0_arm64` wheels. The full dependency
closure resolves with arm64 wheels on both targets (on linux/aarch64 build123d swaps
`lib3mf` for `py-lib3mf` by marker; the macOS `lib3mf` wheel is universal2).

**OpenSCAD branch taken: nightly + Manifold.** The OBS repo publishes an arm64
`openscad-nightly`; the image sets `OPENSCAD_BIN=openscad-nightly` and
`CAD_OPENSCAD_BACKEND=manifold`, and `_compile_scad` adds `--backend=manifold`. Measured
in-container (same binary, 64-sphere boolean on a 60x60x20 cube): CGAL 68.1 s vs
Manifold 0.53 s. If a future image build finds no arm64 nightly, the fallback is Debian
`openscad` on CGAL with `P5-CAD-OPENSCAD-MANIFOLD-001` recorded — never an x86_64
AppImage or emulation.

### Verified in the container (2026-10-06)

```
image Architecture = arm64 · container uname -m = aarch64
build123d 0.11.1 · vtk 9.7.1 · OCP.cpython-311-aarch64-linux-gnu.so
build123d-mcp 0.3.90 · OpenSCAD 2026.10.05.nightly (--backend CGAL|Manifold)
tests/benchmarks/cad_gauntlet_v2_oracles.py: 8/8 oracle parts PASS (machine=aarch64)
```

## Tool surface

- **Primary (BREP):** `generate_part` (JSON IR -> build123d script -> build -> STEP+STL+PNG)
  and `cad_build` / `cad_execute` / `cad_measure` / `cad_find_holes` / `cad_render` /
  `cad_finalize` (free-form build123d with a measure-and-verify loop). Bridge:
  `tools/b123d_bridge.py`; one CAD session per pipeline request (LRU eviction, idle TTL).
- **Fallback:** `generate_scad` / `render_openscad` (OpenSCAD, Manifold), `render_mesh`,
  `convert_cad`.
- **IR:** `tools/part_plan.py` (`plan_part`) does all coordinate math once; `scad_emitter`
  and `b123d_emitter` are the two backends. SCAD output is pinned byte-for-byte by
  `tests/data/cad_scad_golden/`; the BREP backend is checked against the SCAD meshes
  (volume, genus, bbox) in `tests/unit/test_b123d_emitter.py`.

**Runtime wiring.** `capabilities.py` never hardcodes a platform -> capability mapping; it
probes what is actually there (`/capabilities`: `openscad_bin|version|backend`,
`build123d`, `ocp`, `build123d_mcp`, `engine` (live), `arch`, `step_read/write`).

## x86/CUDA tier (stub, UNBUILT)

`Dockerfile.mcp.x86` is a present-but-unbuilt placeholder for the later dual-platform
focus (the P40 box). It predates `Dockerfile.cad`, still describes the old shared-image
layout, and is not built or exercised by CI; it would need a `Dockerfile.cad`-style
split before use. Its genuine addition over the arm64 tier is CUDA-class model execution,
not OCP/build123d (pip wheels exist for both). Per the standing rule above, nothing x86
runs on the Mac.
