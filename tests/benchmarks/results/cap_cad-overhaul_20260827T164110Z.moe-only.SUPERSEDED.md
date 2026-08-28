# Superseded CAD gauntlet partial

The adjacent `.moe-only.json` and `.moe-only.txt` are retained only as historical payload evidence. Their verdict is superseded because the run used an unconstrained `geometry` tool schema, silently ignored unknown feature keys, ran the MoE arm without a baked context tag, and did not gate PASS on bounding-box sanity. The real t1/t2 payloads remain regression fixtures in `test_cad_schema_parity.py`.

No model promotion decision may be based on this partial run.

## Fixup decision record

- Feature-relative placement occurred in one distinct observed part (t1 enclosure); t2 did not request it. This is below the task's threshold of two distinct parts, so `on_feature` was not added. Drilled standoffs remain directly expressible with `standoffs[].inner_diameter`.
- The replacement edge construction uses 2-D `offset()` profiles joined with `hull()` slices. The ten-part coverage corpus compiled and rendered watertight with intended bounding boxes, including selective top/bottom/all treatments, while avoiding sphere-Minkowski entirely. On the local OpenSCAD smoke run all ten corpus cases completed together in under ten seconds; no representative edge-treated part approached the 30-second fallback threshold.
