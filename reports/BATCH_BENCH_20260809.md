# TASK-BATCH-BENCH-001 — Closeout Report (2026-08-09)

New-model fleet expansion + Serena MCP + Antares trigger. All parts isolated + confirm-only.
**No fleet routing changed** — `PROMOTE_POLICY=confirm` held throughout; every promotion decision
below is a recommendation for a separate operator task, not an automatic change.

## Ranked comparison

| Candidate | Path(s) benched | Intake (loaded/non-blank/tool-calls/fits) | Absolute score(s) | Delta vs incumbent/baseline | t/s (floor pass?) | Verdict |
|---|---|---|---|---|---|---|
| **XYZ-Aquila-mini** | GGUF (Ollama, imported via `hf_hub_download`+`ollama create`) — mlx-build exists but server won't serve unstaged models | Yes/Yes/Yes/Yes | C1 fmt=1.00 cap=0.00; C4 fmt=1.00 cap=0.89 | C1 tied; **C4 +0.67 cap vs auto-research** (0.89 vs 0.22) | 49.9 t/s (**pass**, ≥20) — oMLX: mlx-blocked, server-side, not scored | **promote-candidate** — clears floor, real C4 edge, AxisAgentic-proxy caveat noted |
| **Nanbeige4.2-3B** | none — arch `nanbeige` unsupported on this Ollama build (0.32.5) | No (load fails: `unknown model architecture`) | — | — | — | **stage-pending** (arch) |
| **Instella-MoE-16B-A3B** | none — arch `instella-moe` unsupported on this Ollama build | No (load fails: `unknown model architecture`) | — | — | — | **stage-pending** (arch) |
| **DavidAU Qwen3.6-27B Heretic** (RBP red EXPLOIT) | GGUF (Ollama, imported via `hf_hub_download`+`ollama create`) | Yes/Yes/Yes/Yes (--force, below floor) | 6-scenario candidate-eval gauntlet vs incumbent | **+0.000** unique_coverage, +0.042 accuracy (single scenario), +0 lab_success | 11.4 t/s (**below** 20 floor — scored anyway via `--force`, by design) | **pass** — does not out-generate the incumbent red generator enough for a corpus-lane slot |
| **Fara1.5-27B** (CUA preflight) | GGUF+mmproj (Ollama, imported via `hf_hub_download`+`ollama create`, vision projector confirmed loaded) | Yes/Yes(mostly)/Partial/Yes | Correct screenshot perception + correct CUA reasoning every sample; 1/4 raw samples well-formed tool call, 3/4 malformed XML tag closure | n/a (preflight gate, not a scored bench) | n/a | **follow-on** — clears the bar to schedule `TASK_FARA_MAGENTIC_BENCH_V1` (not built here) |
| **Serena MCP** | stdio (`uvx --from git+.../serena`), tools trimmed via `~/.serena/serena_config.yml` | Yes/Yes/n/a/Yes | Refactor bench: 4 steps/0 errors vs text-path's 10 steps/3 errors on a real cross-file rename with a genuine symbol-name collision | −60% steps, −3 errors | n/a | **promote-candidate** — first-try-correct on a collision that grep/sed structurally can't disambiguate |
| **Antares-1b** | GGUF (2 independent community quants, both ungated and pulled directly) | Yes/No(garbage via chat template)/No/N-A | `/api/chat`: `@@@@@@@@@@@@@@@@` on both quants, 0 tool calls. `/api/generate --raw`: perfectly coherent ("Paris. 2. The largest city...") | — | — | **blocked** — broken special-token (`<\|start_of_role\|>` etc.) handling in the GGUF conversion's chat template, isolated via raw-vs-chat A/B test; weights/arch are fine. NOT the Cisco access gate the task premise assumed, and NOT an arch-support gap (both wrong first-pass conclusions, corrected) |

## Per-question answers (from the task's "Report back" section)

- **Nanbeige-3B**: does not clear the floor question — never loads (arch unsupported). No GGUF-vs-oMLX comparison possible.
- **Aquila-mini**: real tool-chain edge shown via C4 (0.89 vs 0.22 cap); the AxisAgentic caveat is flagged — this is a proxy signal via in-fleet capability probes, not a deep-search-harness verdict. `bench_candidates_v10.py`'s `PROBE_PLAN` is fixed to an earlier candidate set with no generic per-workspace entry point, so it could not run for Aquila as the task assumed; recorded as a finding rather than worked around by extending that harness.
- **Instella-MoE**: doesn't hold up — no GGUF runs at all on this build (arch unsupported), so it's not even an open-MoE control candidate here.
- **Heretic**: does not out-generate the incumbent red corpus generator — aggregate coverage delta is flat.
- **Fara**: emits CUA-shaped actions with correct reasoning, but tag closure is unreliable (1/4 well-formed) under this ad-hoc import — green-lights the MagenticLite follow-on rather than a verdict on its own.
- **Serena**: cuts refactor steps and errors substantially (4 vs 10, 0 vs 3) on a realistic scenario — earns the standing-slot recommendation.
- **Antares**: not actually gated — two independent ungated community GGUF conversions were
  pulled and probed directly. Both are broken the same way: raw completion is perfectly
  coherent, chat-templated requests produce garbage (`@@@@@@@@@@@@@@@@`), isolated to the
  Granite-4 special-role tokens specifically. This required two corrected passes to reach —
  worth noting since the first "gated" conclusion was accepted without ever attempting a pull.

## What actually happened vs. what the task file assumed

Every part hit at least one place where the task file's literal commands didn't match live HEAD —
consistent with the task's own Global Invariant #3 ("never trust a string from this file verbatim
if HEAD has moved"):

- **Part A**: `ollama pull` on the Aquila-mini Q4_K_M GGUF hit a repeatable, root-caused server-side
  "context deadline exceeded" on the 21GB blob specifically (not network, not the repo — confirmed
  via direct HF CDN probing and blob-cache verification). Worked around with the repo's own
  documented gated-repo pattern. `bench_tps.py --mode direct --workspace X` silently ignores
  `--workspace` (it's `pipeline`-mode only) — the task's example command would have run a full
  121-model sweep instead of the single target; caught and corrected before it ran.
- **Part B**: `python3 -m bench_security candidate-eval` (the task's literal invocation) does
  nothing — `bench_security` is a backward-compat re-export shim with no subcommand dispatch. The
  real entry point is `python3 -m portal.modules.security.core candidate-eval`.
- **Part C**: Fara's full trained system prompt/tool schema isn't publicly published (Microsoft
  states it ships only with MagenticLite) — used the verbatim sentences that are published rather
  than fabricating the rest.
- **Part D**: `~/.serena/serena_config.yml` needs a `projects:` key or Serena's global config
  loader fails outright; GATE-D1's air-gap premise didn't hold on this box (confirmed live internet
  throughout).
- Also found and fixed (in scope, root-caused): `deploy/playwright-mcp/Dockerfile` was missing the
  `portal` package copy after an unrelated data-loader consolidation commit four days earlier —
  masked until this task's required stale-image rebuild surfaced the crash loop.

## Deferred items (folded into KNOWN_LIMITATIONS.md)

- **P5-FARA-CUA-001** — Fara XML tag-closure reliability; MagenticLite follow-on scoped, not built.
- **P5-SERENA-GATE-D1** — air-gap LSP staging; not applicable on this box, noted for a genuinely air-gapped deployment.
- **P5-ANTARES-GATE-E1** — gated Cisco HF download; Part E deferred until access clears.

## Verification

`python3 scripts/validate_system.py`: 72/72 pass at every commit boundary in this task.
`pytest tests/unit/`: 955 passed at every commit boundary. `ruff check . && ruff format --check .`:
clean throughout. `config/backends.yaml` `workspace_routing` changed only additively (one new
`bench-aquila-mini-35b-a3b` entry); no production primary was touched. Zero catalog deletions.
