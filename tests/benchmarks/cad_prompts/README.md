# CAD gauntlet prompts and arm overrides

Files here are inputs to `scripts/run_cad_gauntlet_arm.sh` / `tests/benchmarks/bench_cad_gauntlet_v2.py --override`.

- `v2_routing_by_outline.txt` — prompt used by the V2N/EB/Q36N/GLM runs (generate_part only for blocks/cylinders).
- `v3_ir_bases.txt` — prompt now committed in `auto-cad`; routes hex/stepped/L parts to the new `prism`/`revolve`/`angle` IR bases.
  UNTESTED against any model as of the handoff — evaluate first (resume task M0).
- `script_only_checklist.txt` — the ES experiment prompt (script-only; worse, kept for the record).
- `b0_workspace_override.json` — reproduces the original B0 auto-cad (old toolset) via `--override`.
- `override_*.json` — model/sampling/tool overrides merged into the `auto-cad` workspace for an arm. Model samplers follow each
  model's production seat (instruct: 0.7/0.8/20, repeat_penalty 1.05; thinking: 1.0/0.95/20, repeat 1.0).
