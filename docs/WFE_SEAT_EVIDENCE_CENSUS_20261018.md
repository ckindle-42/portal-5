# Seat evidence census (2026-10-18)

Each production seat in `config/portal.yaml` (35 workspaces with a `model_hint`, `bench-*` excluded),
checked against the decision-grade WFE cells in `tests/wfe/fitness_ledger.yaml`. Benches from before
the 2026-10-13 instrument audit don't count as evidence: in that audit, 3 of the 4 historical
verdicts re-tested on the right instrument flipped.

## Measured (4) — the seat lost in 3 of them

| Workspace | Seat | Result |
|---|---|---|
| auto-compliance | Qwen3.8-27B | held (granite-30b NOT_SEPARATED) |
| auto-data | Qwen3.6-35B-A3B | granite4.1:30b BETTER — G3 HOLD |
| auto-documents | granite4.1:8b | gemma4-26b and Qwen3.8 BETTER — G1 head-to-head next |
| auto-math | phi4-mini-reasoning | all 3 challengers BETTER — moving to glm-4.7-flash |

## Suite and plan already built, campaign not yet run (13)

| Plan | Workspaces (seat) |
|---|---|
| reasoning_math | auto-reasoning (DeepSeek-R1-0528-Qwen3-8B) |
| cad | auto-cad (qwen3-coder-30b) |
| tools_specialist | tools-specialist (granite4.1:8b) |
| reading | compliance-reading (gemma4-26b ctx128k) |
| extract | auto-extract-uncensored (LFM2.5-8B) |
| routing | auto (qwen3.5-abliterated 9b) |
| research (S5) | auto-research (Nex-N2-mini) |
| general (S6) | general-fast (Qwen3.6-35B), general-deep (Qwen3.8), auto-daily (gemma4-26b qat), auto-general-uncensored, auto-uncensored-throwaway |
| coding (S7) | auto-coding (qwen3-coder-30b) |

## No instrument yet (18)

auto-security, auto-spl, auto-bigfix (deferred), auto-creative (blinded-review lane), auto-vision,
auto-audio, auto-music, auto-image, auto-video, auto-nemotron, auto-council, the three
compliance-council seats, compliance-mapping, compliance-reading-overflow, security-reviewer,
task-router.

## Signals worth a look first

- **granite4.1:8b holds four seats** (auto-image, auto-video, security-reviewer, tools-specialist)
  and lost auto-documents to two challengers. On documents it also did table arithmetic wrong.
  tools-specialist is in the built set.
- **qwen3-coder-30b holds three seats** (auto-coding, auto-cad, auto-bigfix), each with its own
  context tag. It has not been measured in any of them.
- An unmeasured seat that is a bench winner from before the audit is a description-based seat by
  this census's rule.

## Synthesis after the seat prior (docs/WFE_SEAT_PRIOR_20261018.md)

Independent public evidence is thin. Most numbers are vendor cards, though same-card or
same-harness tables (e.g. NVIDIA's run of Nemotron, Qwen3.6 and Gemma) at least compare like with like.

| Group | Seats | Next step |
|---|---|---|
| Decide from evidence on hand, no campaign | auto-reasoning | Our math rows already have DeepSeek-R1-8B, GLM-4.7-Flash and Qwen3.8 on the same suite: 105 / 104 / 107 of 108. The suite is at its ceiling; median time 52 s / 24 s / 8 s. Vendor GPQA/AIME favour GLM and Qwen3.8 by 14–28 points. |
| Screen worth running | auto-research (Nex-N2.5-mini, +9 BrowseComp / +21 Toolathlon same-vendor; one download) | research suite built |
| Same-family upgrade, no instrument | auto-council synthesizer qwen3.6:27b → Qwen3.8-27B (+10 IFBench same card, weights on disk) | operator call |
| Held for diversity (operator) | auto-nemotron (G5), compliance-council-deepseek-r1 (its point is a non-Qwen voice), auto-data (G3 HOLD) | no action |
| KEEP-LIKELY | general-fast, general-deep, auto-music, auto-image, auto-video, compliance-reading (+overflow), council granite41 / qwen38 | no action |
| UNKNOWN, cheap existing instrument | auto-coding (bench_repair 40 tasks), auto-cad (bench-qwen38/36-cad gauntlets), compliance-mapping (mapping-v3 sweep, 75 readings) | run those, not WFE |
| UNKNOWN, no public data or instrument | tools-specialist, security-reviewer, auto-security, auto-spl, auto-bigfix, auto, task-router, auto-extract-uncensored, auto-vision, auto-audio, the 3 uncensored/creative seats | build only where usage justifies it |

**Suite ceiling.** documents_production (gemma and Qwen3.8 both 108/108) and reasoning_math
(96–99 % for every challenger) can't rank strong models. When the incumbent or the challengers
pass ≥ 95 % at the screen, the confirm can only show "worse". Decide on speed and lineage, or
harden the suite, before spending a confirm.
