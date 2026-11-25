# Routing baseline re-bless audit — 2026-11-25

Lane `lane/rebless-audit` at `origin/main` (`5d2b44447`). Offline only. The live stack was not exercised.

## Scan

`git log --since=2026-11-18 origin/main -- tests/routing/baseline.json` names two commits. A second pass, `git log --since=2026-11-18 --diff-filter=M -- '*baseline*' '*golden*' '*expected*'`, finds no other modified expected-value artifact that rides with a behaviour change. The other hits are wiki prose, hunt-doc wording, and the 2026-11-18 test-trim deletions (`tests/data/cad_scad_golden/`, `tests/fixtures/wiki_search_baseline.json`). Commit subjects matching `re-bless|baseline|golden|expected` add no further gate re-bless.

`02383c16c` also updated two seat-window assertions in the same commit as the context upgrade. Those are listed after the corpus rows. They are not routing-baseline rows.

## Corpus rows

Resolver: `scripts/routing_regression.py` records `claim_pre_layer` (operator handoff, then specialist intent) and otherwise the keyword layer, then `model_hint` from `config/portal.yaml`. Classification uses the commit message, that config, and the seat text in `config/portal.yaml`.

| Row | Old | New (as blessed) | Behaviour that moved it | Class |
| --- | --- | --- | --- | --- |
| `fold_security_uncensored` | `base/served_model/variant` all null | `auto-daily`, `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k`, variant null | `0898e6009` added `_NETWORK_SECURITY_HANDOFF_KEYWORDS`. The prompt "Uncensored security analysis…" scores `security` weight 2, equal to `_ROUTER_HANDOFF_THRESHOLD`. Handoff returns `router_fallback` `auto-daily`. That tag was already `auto-daily`'s `model_hint` at `0898e6009`. Sibling security folds (`fold_redteam_deep`, `fold_purpleteam_exec`, `rr_s21_01_sqli_auto`) were already on this seat. | INTENDED |
| `rr_variant_security_base` | all null | same `auto-daily` / Nemotron ctx32k / variant null | Same commit. Prompt "What is a firewall and how does it filter traffic?" scores `firewall` weight 3. `tests/unit/test_auto_router_handoff.py` pins the TLS/firewall ask to `auto-daily` plus the note that names `auto-security`. `auto-security` is `router: false`. | INTENDED |
| `routing_examples[37]` | all null | `auto-reasoning`, `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k`, variant null | `0898e6009` added `_MATH_ROUTING_KEYWORDS` on the **base** keyword map and `detect_specialist_intent`, which at that commit returned bare `auto-reasoning`. The baseline runner called `detect_router_handoff` and `_detect_workspace` and skipped specialist intent, so the re-bless stored the base seat. `auto-reasoning::math` already existed at the parent, `model_hint` `glm-4.7-flash:Q4_K_M-ctx24k`, described as the calculus seat (`wfe_math_20261018d`). `6d34a0ec` then promoted specialist intent and Layer 1 to `auto-reasoning::math` because `s5-route-math-integral` received `auto-reasoning`. The baseline stayed on the base seat, so the gate stayed green. | REGRESSION |
| `routing_examples[19]` | `auto-compliance`, `…Qwen3.8-27B-GGUF:Q4_K_M-ctx32k`, variant null | same base and variant, `…Q4_K_M-ctx96k` | `02383c16c` moved `auto-compliance.model_hint` to the ctx96k twin and `context_limit` 32768 → 65536. Prompt "is my environment compliant with NERC CIP-007-6 R4?" still resolves to `auto-compliance`. Sampling, `think`, and tool caps were unchanged in that commit. | INTENDED |
| `routing_examples[20]` | same ctx32k triple | same ctx96k triple | Same seat upgrade. Prompt "map our patch management process to CIP-007 requirements". Base stayed `auto-compliance`. | INTENDED |
| `rr_s21_03_compliance_auto` | same ctx32k triple | same ctx96k triple | Same seat upgrade. Prompt "What are the requirements for NERC CIP-007 R2 patch management?". | INTENDED |

Current `auto-compliance.model_hint` is still `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k`. Current `auto-daily.model_hint` is still the Nemotron ctx32k tag.

## Companion assertion updates in `02383c16c`

INTENDED. They follow the same window upgrade and do not change a route.

- `tests/unit/test_owui_tool_merge_dedup.py`: `auto-general-uncensored` `context_limit` 8192 → 32768, fit budget 6144 → 24576. Config at that commit: `model_hint` `…q4_K_M-ctx32k`, `context_limit` 32768. The old 8k overflow is still pinned as `estimate_tokens(legacy) > 6144`.
- `tests/unit/test_transport_pipeline_dialect.py`: `workspace_context_limit("auto-compliance")` 32768 → 65536, matching `context_limit`.

`59df4111` (separate commit) updates the QAT expectation for `auto-coding::cad` `max_tool_hops` to 10 after `02383c16c` set that cap. It does not re-bless a baseline file.

## Fix for the regression row

Root cause: the baseline runner did not apply `detect_specialist_intent`, which production applies before the LLM and the keyword layer. The re-bless therefore stored the keyword-layer base.

- `claim_pre_layer` in `portal/platform/inference/router/routing.py` is the shared order: handoff, then specialist intent. `preinject._resolve_auto_routing` uses it and keeps the same metric labels and handoff note.
- `scripts/routing_regression.py` `deterministic_then_keywords` uses that claim, then `_detect_workspace`.
- `tests/routing/baseline.json` `routing_examples[37]` is now `auto-reasoning` / `glm-4.7-flash:Q4_K_M-ctx24k` / variant `math`.
- A dry diff of the resolver against the previous baseline changed that one row. `uv run python scripts/routing_regression.py --assert-baseline` then printed `PASS: 86 corpus prompts match tests/routing/baseline.json.`

## UNCLEAR

None. Every re-blessed row is classified above. No live probe is required to finish a classification. The orchestrator still runs the live route check below; this lane did not.
