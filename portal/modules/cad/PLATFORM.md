# CAD Module — Platform Tiers

## arm64/OSX tier (built + verified here — the default)

OpenSCAD + trimesh + **CadQuery/build123d/OCP via conda-forge**. This is the fullest
geometry stack achievable on Apple Silicon and it is what `Dockerfile.mcp` builds by
default.

**The old limitation was a pip-wheel artifact, not a platform ceiling.**
`P5-CAD-ARM64-001` claimed "CadQuery/build123d require OCP which has no arm64
wheels — cannot install on arm64, use OpenSCAD only." That was true for *pip*
wheels of OCP as of early 2024. It is no longer true: conda-forge's `ocp` (the
OCCT pybind11 bindings CadQuery/build123d sit on) ships for `linux-aarch64` and
`osx-arm64` (also linux-64/osx-64/win-64), and conda-forge's `occt` kernel
package lists `macOS-arm64` and `linux-aarch64` as supported platforms.

**Empirical verification (2026-08-27, TASK_CAD_MODULE_OVERHAUL_V1 Phase 0):**
ran a standalone micromamba probe directly on this machine's osx-arm64 host
(not yet re-run inside the container image — see "residual verification" below):

```
micromamba create -y -n cadtest -c conda-forge python=3.11 cadquery build123d ocp
```

Resolved and installed cleanly: `occt-7.8.1`, `ocp-7.8.1.2`, `cadquery-2.7.0`,
`build123d-0.9.1`. Then:

```python
import cadquery as cq

r = cq.Workplane("XY").box(10, 10, 5)
from cadquery import exporters

exporters.export(r, "/tmp/_cq_smoke.stl")  # -> wrote a valid STL
import build123d  # -> imports clean
import OCP  # -> imports clean
```

All three passed. This overturns the stale claim: CadQuery/build123d/OCP **do**
run on arm64 via conda-forge. The real constraint was never "arm64 the
platform" — it was "pip-wheel install in a pip-only environment."

**Residual verification — do before relying on this in production.** The probe
above ran in a throwaway micromamba env on the macOS host, which proves the
package resolution and import path. `Dockerfile.mcp`'s conda layer (installing
the same trio into `/opt/conda/envs/cad` inside the `python:3.11-slim`
linux/arm64 image) has **not yet been rebuilt and independently re-verified in
this session** — that image build was not exercised here (it's a large, slow
image; doing so was out of scope for this pass). Before treating
`cad_capabilities()["ocp"]` as reliably True in the deployed MCP container, run:

```bash
./launch.sh rebuild   # or the equivalent MCP-image rebuild target
docker exec <cad-mcp-container> curl -s http://localhost:8926/capabilities
```

and confirm `cadquery`/`build123d`/`ocp`/`step_read` are all `true`. If that
rebuild surfaces a genuine dependency conflict with the rest of the shared MCP
image, record the specific failure here and fall back to OpenSCAD-primary —
but do not reinstate the "no arm64 wheels" wording, which is factually wrong
regardless of whether this particular image build succeeds.

**Runtime wiring.** `capabilities.py`'s `cad_capabilities()` never hardcodes a
platform → capability mapping — it probes what's actually importable, adding
`CAD_CONDA_ENV_SITE_PACKAGES` (set by `Dockerfile.mcp` to
`/opt/conda/envs/cad/lib/python3.11/site-packages`) to `sys.path` first so the
base pip interpreter can reach the conda-installed packages. `convert_cad`'s
STEP read/write path gates on `cad_capabilities()["step_read"]` rather than
asserting availability.

## x86/CUDA tier (stub, UNBUILT)

`Dockerfile.mcp.x86` is a present-but-unbuilt placeholder for the later
dual-platform focus (the P40 box). Its genuine addition over the arm64/OSX
tier is **CUDA-class model execution** (e.g. a Vicuna-13B VLM like
CAD-Coder(LLaVA) is comfortable on a P40 with CUDA, loadable-but-slower on
Apple Silicon Metal) — **not** OCP/CadQuery/build123d, which are already
available on both tiers via conda-forge. Not built, not exercised by CI.
