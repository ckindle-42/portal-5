# CAD gauntlet v2 — run register (TASK_CAD_ARM_REDEVELOP_V1)

Two instruments were used. Only the production-like runs are evidence.

**Invalid instrument** (`cad_gauntlet_v2_invalid_instrument/`): the first driver called Ollama's raw
`/v1/chat/completions`, which silently drops `think`, `top_k`, `min_p` and `repeat_penalty`
(KNOWN_LIMITATIONS P5-OLLAMA-V1-SAMPLING-001). Thinking models ran with thinking on and every arm ran off
its configured sampling. Kept as a record only; do not compare against them.

**Production-like** (this directory; driver commit "production-like gauntlet transport"): the driver
chats through `OllamaNativeTransport`, the exact adapter the pipeline uses, 14-turn cap, per-cell
`ended`/`last_text`, optional transcripts (`CAD_GAUNTLET_TRACE_DIR`).

| label | arm | tools / prompt | cells | mean | PASS | validity | note |
|---|---|---|---|---|---|---|---|
| B0N | qwen3-coder ctx16k, OLD toolset (generate_scad) | `cad_prompts/b0_workspace_override.json` | 24 | 0.667 | 9 | 1.00 | baseline for the gate |
| V2N | qwen3-coder ctx32k | 20 tools, prompt `v2_routing_by_outline.txt` | 24 | 0.760 | 10 | 1.00 | gate: mean >= B0N and validity >= B0N -> PASS |
| EB | same | six noise tools removed | 16 | 0.719 | 6 | 0.94 | ~2x faster (37 s vs 69 s median), accuracy unchanged |
| ES | same | script-only (no generate_part), `script_only_checklist.txt` | 16 | 0.469 | 2 | 0.62 | worse: verify loops hit the turn cap |
| Q36N | Qwen3.6-35B-A3B UD-Q4_K_XL ctx32k, think off | v2 prompt | 16 | 0.734 | 9 | 0.81 | best pass rate; first to pass flanged_bushing |
| GLMF | GLM-4.7-Flash ctx64k, think off | v2 prompt | 16 | 0.484 | 3 | 0.69 | thinking is where its quality comes from |
| GLMN | GLM-4.7-Flash, think ON | v2 prompt | 11 (partial, stopped) | 0.659 | 6 | 0.82 | ~174 s median; stopped for time |

Per-task PASS counts, ended reasons and measured geometry are in each JSON. The IR now also has `prism`,
`revolve` and `angle` bases (see `portal/modules/cad/tools/part_plan.py`), so every run above predates
the vocabulary that covers hex_standoff / flanged_bushing / l_bracket; prompts `v3_ir_bases.txt` targets it.
Next runs: `coding_task/TASK_CAD_ARM_REDEVELOP_V1_RESUME.md`.
