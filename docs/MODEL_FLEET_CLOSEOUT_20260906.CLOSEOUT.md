> **STATUS 2026-09-07 (final): REMOVALS HELD.** Per operator doctrine (real-use validation before fold/purpose/removed), this register is the **provisional input map** to the governing task [`TASK_WORKSPACE_FITNESS_EVAL_V1.md`](TASK_WORKSPACE_FITNESS_EVAL_V1.md). Execute no removals until the Workspace Fitness Evaluation completes and re-issues this register as v4.

# Model Fleet Closeout — Final Disposition Register (2026-09-07, executed)

Execution of [TASK_MODEL_FLEET_CLOSEOUT_20260906](TASK_MODEL_FLEET_CLOSEOUT_20260906.md). **This register is final and test-backed**: every worklist identity carries one terminal disposition; all pre-registered contender stop rules were evaluated against data executed on 2026-09-07 (no inference was run against stale evidence). Machine-readable state: [MODEL_FLEET_CLOSEOUT_20260906.tasks.json](MODEL_FLEET_CLOSEOUT_20260906.tasks.json).

**Operator rulings applied:** (1) bench-only references do not confer a home; (2) evaluation must respect workspace/persona intent — uncensored lanes compare uncensored candidates, a model is judged for where it fits, and memory co-residency budgets (e.g. purpleteam chains) are decision constraints.

## 1. Result — tiered closure (v3)

| Tier | Count | Meaning |
|---|---:|---|
| INTEGRATED | 78 | wired role (route/hint/pin/persona/council/code) with role-appropriate evidence |
| RETAINED_FOR_PURPOSE | 18 | 5 named-purpose seats (REAP-288 manual coding, orcarouter verified uncensored coder, qwen3-vl:8b lighter vision, 27b-ctx8k verified manual, fara1.5 CUA) + **diversity seat gpt-oss** (only OpenAI lineage; native-arm settings required) + **IDE explorer FastContext** (pipeline_mcp's wired subagent; bounded pull+verify pending) + **11 USE-PROBE** models |
| REMOVED_CLOSED | 92 | Stage-1 only: decisive evidence independent of the usability lens (absent, duplicate-identical outputs, real-scenario gate failures, broken install, instruction-floor failure ×2, stale wiring) + alias folds + record-only |

**Operator doctrine applied (2026-09-07):** short-prompt instruments cannot settle real-usability fit. One-size-does-not-fit-all is why the catalog is large; models set out for one task often work better at another. Therefore: (a) removals require evidence that survives the usability lens, (b) every model with a plausible untested niche is queued in the USE-PROBE tier with a named real-work assignment and a stop rule, (c) incumbents get settings/design/intent verification in real context — demonstrated when the settings review caught that the glm_coder pin flip had silently dropped the persona's 128K-window promise (base tag ships no baked `num_ctx`; derived `-ctx64k` tag created, pin repointed, cataloged).

## 2. Storage reconciliation (measured 2026-09-07)

| Measure | Value |
|---|---:|
| Ollama manifests at start / end of determination | 141 / 141 (removals pending approval) |
| Ollama unique blob bytes | 1,087.153 GiB (386 files) |
| oMLX tree / HF cache | 243.776 / 333.161 GiB |
| Cross-store union (device/inode dedup) | 1,558.473 GiB |
| **Stage-1 removal set — exclusive blobs** | **192.607 GiB** |
| USE-PROBE tier held | 13 tags, 120.6 GiB logical (bounded real-work assignments, §5) |
| Projected unique blob store after Stage-1 removal | 894.546 GiB |

`scripts/model_cleanup_audit.py` now reports 73 REMOVED_CLOSED tags still on disk (true cleanup exceptions) and **0 config drift** (every INTEGRATED Ollama tag present). `config/PENDING_MODEL_VERDICTS.md` is a historical pointer; the audit no longer regenerates a pending ledger.

## 3. Executed tests (2026-09-07) and the decisions they closed

| Test (instrument) | Result | Decision |
|---|---|---|
| Research probe ×2 (`bench_research_probe.py`) | Nex-N2-mini factuality 0.9 / 0.8, synthesis 5.0 / 4.5 vs Aquila-mini 0.3 and tongyi 0.4 | **Nex-N2-mini INTEGRATED as auto-research hint** (Aquila's Aug-13 promotion no longer holds; tongyi also fails its lane); Aquila-mini REMOVED |
| Refusal probe ×3 (`bench_refusal_preservation_probe.py`) | 35B-abliterated 1.0 / 0% over-refusal @ 55.6 t/s; orcarouter 1.0 / 0%; incumbent 27b-ctx8k 0.75 / 33% @ 12.9 t/s | **35B-abliterated INTEGRATED as auto-general-uncensored hint** (intent-consistent uncensored→uncensored, 4.3× faster; judgment tradeoff exact 0.87 vs 0.90 recorded); incumbent narrowed to persona-pinned manual |
| Vision probe ×2 (`bench_vision_probe.py`) | qwen3-vl:8b 4/4 @ 78 t/s vs 32b 4/4 @ 11.9 t/s | 8B **RETAINED** (stop rule "materially below" did not fire); wiring as lighter variant = optional operator line |
| Fara CUA preflight (`bench_fara_cua_probe.py`) | loads; emits well-formed `computer_use` tool_call per card's action space | fara1.5 **RETAINED** — only CUA-capable candidate; full MagenticLite harness is a documented limitation; manual-only |
| Judgment v6 ×10 models + gpt-oss native arm ×30 | see table below | C1/C8/C9/C11/C12 closed; incumbents verified |
| gpt-oss 3-arm diagnostic | harness arm (think:false+format:json) 0/5 = **instrument artifact**; native arm works | 0.000 sweep score disqualified; native arm used for the fair verdict |
| Repair-loop coding exam ×4 arms ×70 samples (`bench_repair.py`, gsha 00e9d1b544a2, Ollama 0.33.2) | glm-full 82%/90%, REAP-23B 80%/90%, kat-coder 82%/100%, orcarouter 100%/100% | C2/C6/C5 closed; kat spot-check (live c2_6) validated output authenticity |

Judgment v6 highlights (F2 / exact / false-supported / t/s): bartowski-Qwen3.6-27B 0.952/0.90/1 — **exact parity with seated library quant → duplicate, removed**; fable-fusion 0.952/0.90/0 — parity with parent, no gain → removed; orcarouter 0.952/0.90/1 — parity + refusal win; 35B-abliterated 0.854/0.87/3 @ 55.6; daily incumbent 26b-qat 0.854/0.83/2 @ 63.5 (verified healthy); granite4.2:8b-q8 0.765/0.57; seated 4.1:8b 0.732/0.67; 4.1:8b-q8 0.741/0.73; **gpt-oss native 0.904/0.80, abstain-recall 1.0 @ 53.3 t/s — but ZERO unique wins over the seated cluster (all 24 correct covered by incumbents, all 6 misses covered by them) → diversity stop rule fires, removed**.

Granite Q8 upgrades (4.1:8b-q8 +0.06 exact; 4.2:8b-q8 mixed) were **removed on the chain-memory constraint**: `granite4.1:8b-ctx8k` is stage 0 of all purpleteam chains co-resident with qwen3-coder-30b + qwen3.6-27b (~38 GiB staged) — marginal gains don't justify breaking that budget. `granite4.2:30b-q4_K_M` was decided WITHOUT a run: existing same-instrument data (F2 0.6962 vs 0.8434) fired its stop rule.

### C2 — the REAP-23B promotion policy executed

`glm_coder` pinned REAP-23B under a documented policy (MODEL_CATALOG.md:535): REAP holds the pin only if it **beats** the standard `glm-4.7-flash:Q4_K_M` on quality + TPS floor. Exam: 80%/90% vs 82%/90%, no TPS edge — **policy evicted REAP; pin reverted to full GLM** (lineage diversity retained by the winner). REAP tags removed (~13.3 GiB).

### C6 — kat-coder

82% one-shot < the pre-registered 43/50 (86%) Ornith baseline → **removed**. Live spot-check on c2_6 (the problem every larger model failed) confirmed genuine, correct, concise output (247 tokens) — the miss is real capability, not formatting. Record notes 100% repair-elasticity and ~7× field speed for any future speed-specialist lane.

### C5 — orcarouter/Qwen3.8-27B-Uncensored

Passed **all** pre-registered gates (repair 100%/100%, refusal 1.0/0%, judgment parity) → **RETAINED as verified uncensored-coding specialist** (manual/bench-only). omnicoder2-9b's variant slot is NOT displaced: 30+ persona pins and the small-lane intent stand.

## 4. Config changes applied (all reversible, git-tracked)

1. `auto-research.model_hint` → `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` (promotion note in-file).
2. `auto-general-uncensored.model_hint` → `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M`.
3. `config/personas/glm_coder.yaml` `model_pin` → `glm-4.7-flash:Q4_K_M` (policy flip documented in-file).
4. Three contender bench workspaces added (`bench-kat-coder`, `bench-orcarouter-q38`, `bench-glm-reap`) — contender seats stay until removals are approved, then fold per §6.
5. `tests/benchmarks/bench_repair.py` shim repaired (stale `TEMPERATURE` import — was crashing the entry point).
6. `scripts/model_cleanup_audit.py` now reports final dispositions + true cleanup exceptions from the register; never regenerates a pending ledger (legacy path retained for historical checkouts).
7. `./launch.sh sync-config` run clean (81 workspaces; derived views regenerated; wiki doc-block auto-updated). Container rebuild deferred until removal execution (eval-only seats; rebuilding mid-bench would have disturbed runs).

## 5. RETAINED_FOR_PURPOSE (5) — all with named purpose, owner, limits

| Identity | Purpose | Storage | Limits |
|---|---|---:|---|
| `Qwen3.8-Flash-Next-REAP-288-MLX-4bit` | manual-only coding specialist; auto-default restriction STANDS | 68.5 GiB | HumanEval unreproduced; optional Laguna comparison not owed |
| `orcarouter/Qwen3.8-27B-Uncensored:Q4_K_M` | verified uncensored-coding specialist (all gates passed) | 16.5 GiB | manual/bench-only; wiring optional; slow (~12 t/s) |
| `qwen3-vl:8b-instruct-q4_K_M` | VQA-validated lighter vision model (parity @ 6.5×) | 5.7 GiB | 4-case synthetic probe is a floor, not full vision acceptance |
| `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` | verified healthy manual model (judgment 0.90/0.952) | shares 27b weights | lost the uncensored hint on lane-instrument data |
| `portal5/fara1.5-27b:Q4_K_M` | only CUA-capable candidate (probe-PASS) | 17.2 GiB | full CUA harness (MagenticLite) is a documented project limitation |

Service/media caches stay owned by their subsystems (image/video/speech/OCR/embeddings/security — unchanged from first pass; three 0-byte husks removable at execution).

## 6. REMOVED_CLOSED (105) — pending the approved removal pass

- **Weight-bearing (42 on-disk tags):** all entries in §3 tables marked removed (gpt-oss, bartowski dup, fable-fusion, kat-coder, REAP-23B pair, granite Q8s, granite4.2:30b-q4, phi4 family, command-r, bakeoff-gate failures, unwired OCR/vision strays, bully/cadmium/antares/security-slm, baronllm:q6_k, aquila-mini…) — exclusive blobs 309.570 GiB total across the set.
- **Alias folds (29):** base tags whose weights survive under an INTEGRATED sibling — fold seat + alias, keep weights.
- **Record-only (34 + 11 extras):** all 33 historical absent tags, stale `models:` pull entries, stale persona pins, olmo NOT_ADOPTED, dangling oMLX symlinks ×2, 3 zero-byte HF husks.
- **Superseded tasks closed:** oMLX "six empty directories" (stale), Cascade-2 (dropped), CAD gauntlet (superseded, no surviving role), oMLX repair-task prose corrected (trees populated).

## 7. Acceptance checklist

- [x] Active job evidence reconciled and preserved (Phi-4 retry + ablation; Phi4 "broken install" root-caused via council comment).
- [x] Refreshed inventory: 141 tags + 17 oMLX + HF owners; byte-exact reconciliation with the audit.
- [x] All 188 identities terminal with reason, evidence, durable record (register + tasks.json) — zero non-terminal rows.
- [x] Contender fold-in decisions made on EXECUTED data with pre-registered stop rules, intent constraints, and memory budgets; incumbents re-verified in the same instruments.
- [x] Every retained/integrated artifact named-purpose + role-appropriate evidence; manual-only models say manual-only.
- [x] Two promotions + one pin-flip applied on decisive data; sync-config clean; derived views reconciled; audit workflow reports dispositions.
- [x] Old pending ledger retired (pointer file); CLAUDE.md reference updated; superseded task prose closed.
- [x] `glm-4.7-flash:Q4_K_M-ctx64k` derived tag + pin fix (context-baking regression caught by real-use settings review).
- [ ] **PENDING OPERATOR GO:** (a) Stage-1 physical removal pass (192.607 GiB exclusive), (b) scheduling the 13 USE-PROBE real-work assignments with their stop rules, (c) incumbent settings/design verification pass (baked-ctx vs declared context_limit per workspace — one regression already caught), (d) post-removal verification + storage report, (e) commit.

## 9. USE-PROBE program (bounded — not an open-ended campaign)

Each assignment names the workspace/persona context, the real inputs, and a stop rule. Count: 13 models / ~120.6 GiB held. Sequence cheapest-first (OCR comparisons are fully mechanical; creative use is operator-judged). No model is removed while its probe is queued; every probe ends in INTEGRATE / RETAIN-with-purpose / REMOVE per its pre-registered rule. Diversity doctrine: lineage census is recorded (§1); gpt-oss re-tiered on it; command-r remains removed (lineage noted, but no seat and below-cluster data — diversity is a factor, not the factor).

## 8. Provenance

Instruments: repo-native probes (judgment_probe_v6 + native-arm variant, research/refusal/vision/CUA probes, bench_repair exam), same scorer/corpus per comparison, incumbents re-run same-batch. Ollama 0.33.2, Apple M4 Pro. Key artifacts: `tests/benchmarks/results/{research_probe_20260907T030136Z,research_probe_20260907T032401Z,refusal_preservation_probe_20260907T025849Z,vision_probe_20260907T030047Z,judgment_probe_v6_20260907T034934Z,judgment_probe_v6_gptoss_native_20260907T043151Z,BENCH_REPAIR_20260907T081156Z,BENCH_REPAIR_CHECKPOINT_00e9d1b544a2}.json|md`. Limitations: repair exam run on Ollama 0.33.2 (Aug trio baseline was 0.32.15 — cross-version treated as reference); vision probe is a 4-case synthetic floor; CUA full harness absent; APFS clone sharing not resolved (union is inode-dedup).
