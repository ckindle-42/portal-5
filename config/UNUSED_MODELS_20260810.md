**EXECUTED 2026-08-10:** 4 Ollama models + 6 oMLX models deleted (0 failures).
`/Volumes/data01` went from 66GB free (97% full) to 206GB free (89% full)
(~140GB reclaimed across both engines, including a ~64GB bonus from Ollama
0.32.7's own blob-prune on first start — see the ollama-service fix commit
for that story). Follows the same review discipline as
`config/UNUSED_MODELS_20260721.md`.

**ADDENDUM 2026-08-10 (bench-cleanup review):** 1 more Ollama model deleted,
2.5GB. `hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M` — `config/backends.yaml`
hard-errors this tag as tool-call-incapable (no `{% if tools %}` block in its
shipped ChatML template); the tool-call blocker was fixed 2026-07-04 via the
`cybersecqwen-4b-toolfix` derivative (kept, still in the `security` group,
`supports_tools: true`), but the base tag's detection quality stayed
inconclusive and it was never adopted — see
`unit-model-catalog-hf-co-mradermacher-cybersecqwen-4b-gguf-q4-k-m-dropped-tool-call-blocker-fixed-2026-07-04-detection-quality-inconclusive-not-adopted.md`.
Not covered by either prior audit's exclusion list; independently verified
before deletion (confirmed unloaded, confirmed the toolfix derivative is a
distinct on-disk tag that survives).

This review surfaced 67 further non-production models (~851GB) not yet
adjudicated by any prior audit — a mix of bench-tied candidates with real
eval evidence sitting in unresolved `PROMOTE_POLICY=confirm` limbo, and a
smaller set with zero eval evidence at all. Deferred pending a proper
workspace-slug-aware audit tool (raw model-tag substring matching proved
unreliable — missed results keyed by workspace slug rather than model tag,
`-ctxNk` derivative tags, and `config/portal.yaml` workspace `variants`
fields serving production traffic under a non-primary `model_hint`).

# Unused models — confirmed safe to delete (2026-08-10)

Found during the RBP-arm oMLX coverage review (disk was flagged as tight,
97% full, while auditing what to promote vs leave on Ollama). Cross-referenced
against every `backends.yaml` model id/alias, every `config/portal.yaml`
`model_hint`/variant, hardcoded defaults in application code (e.g.
`tool_preselect/config.py`), and the existing `UNUSED_MODELS_20260721.md`'s
explicit exclusion list.

## Ollama — 4 models, ~31.9GB

| Model | Size | Reason |
|---|---|---|
| `portal5/qwen36-27b-fable-fusion-heretic:Q4_K_M` | 18.0GB | Evaluated as an RBP EXPLOIT-slot candidate, verdict NEUTRAL, not promoted — see `unit-model-catalog-portal5-qwen36-27b-fable-fusion-heretic-q4-k-m-dropped.md`. Distinct from `qwen36-fable-fusion-711:Q4_K_M` (kept — different blob, separate untested candidate). |
| `hf.co/DevQuasar/amd.Instella-MoE-16B-A3B-Think-GGUF:Q4_K_M` | 10.5GB | Arch-blocked — fails to load on this Ollama build with "unknown model architecture" (confirmed in the XYZ-Aquila-mini intake commit, 63cbca4c). Cannot run regardless of promotion decisions. |
| `hf.co/owao/Nanbeige4.2-3B-GGUF:Q4_K_M` | 2.6GB | Same arch-blocked family as above. |
| `hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M` | 0.8GB | No reference anywhere in the repo (checked config, code, docs, CHANGELOG); a retired-era MLX-draft-model leftover, unrelated to the still-live `mlx-community/Llama-3.2-1B-Instruct-4bit` mentions in CHANGELOG.md/test results. |

**Explicitly kept** (verified individually, do not delete): `kat-coder-v2.5-dev` (pending future eval), `qwen36-fable-fusion-711` (pending future eval, distinct blob from the dropped heretic variant), `portal5/fara1.5-27b` (open investigation, P5-FARA-CUA-001), `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF` (the production Layer-1 router model, `LLM_ROUTER_MODEL`), `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` (registered in `backends.yaml`'s `general` group — the orphan scan's exact-string match missed the implicit `:latest` tag), `hf.co/DevQuasar/fdtn-ai.antares-1b-GGUF` (open investigation, P5-ANTARES-GATE-E1), both MiniCPM5-1B variants and `nomic-embed-text` (already covered by `UNUSED_MODELS_20260721.md`'s exclusion list — tool-preselect default + RAG embedding fallback). `granite4.1:8b-q8_0` (the un-suffixed base tag) shares its blob with the live `-ctx16k` derivative — deleting it reclaims ~0 bytes, so left in place.

## oMLX — 6 models, ~73.5GB

All six lived only in `backends.yaml`'s `omlx-local` holding group, which
receives zero production traffic (confirmed: no `workspace_routing` entry
references group `omlx`) — the broader vision/VLM/MTP evaluation set this
group used to hold for a future bake-off (`TASK_OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V1`).

| Model | Size | Reason |
|---|---|---|
| `Qwen3.6-27B-oQ8-mtp` | 28GB | Phase-4 MTP-enablement reference artifact, no consumer yet — measured speedup numbers preserved in the DROPPED catalog entry if that plan is revisited. |
| `Qwen3-VL-32B-Instruct-4bit` | 18GB | Vision is served by `ollama-vision` in production; this was an unpromoted eval candidate, already flagged in `docs/PERSONA_MATRIX_CI.md` as unreferenced by any routing chain. |
| `supergemma4-26b-abliterated-multimodal-mlx-4bit` | 15GB | Was eyed as an RBP redteam-deep/purpleteam-exec candidate, but is a checkpoint mismatch — a *different* repo (`abliterated-multimodal`) from what those variants actually need (`-uncensored`), confirmed via each repo's own README `base_model` field. Not usable for that purpose as-is; deleting loses nothing. |
| `Phi-4-reasoning-plus-MLX-4bit` | 7.7GB | Already flagged do-not-migrate in the surrounding config comment — degenerate tool-call output, template issue never resolved. |
| `gemma-4-e4b-it-4bit` | 4.8GB | Duplicate of what `ollama-vision`'s `gemma4:e4b-it-q4_K_M` already serves. |
| `Llama-3.2-3B-Instruct-8bit` | ~3GB | Eval-continuity model only (cross-bake-off tracking), tool-calling already FAILs (Llama-family oMLX parser gap), no workspace consumer. |

`config/backends.yaml`'s `omlx-local` entry trimmed to the two models still
resident (`Qwen3-Coder-30B-A3B-Instruct-4bit`, `Laguna-XS.2-4bit` — both
shared with the live `omlx-coding` group, so no disk cost either way).
`config/MODEL_CATALOG.md` sections for all 6 marked DROPPED in place
(additive-only discipline — content preserved, not deleted) rather than
removed, so the institutional Phase-0 probe numbers stay available.

To delete additional models later: `curl -X DELETE http://localhost:11434/api/delete -d '{"model":"<name>"}'`
for Ollama, `rm -rf /Volumes/data01/omlx-models/<name>` for oMLX. Re-verify
none are loaded and none overlap any in-progress bench/ablation run first.
