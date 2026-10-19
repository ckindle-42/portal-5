# Decision: auto-council runs every role on the resident gemma-4-26B-A4B (2026-10-19)

**Operator:** "switch to gemma4 with early quorum if it warrants, think and research before
making that decision, be holistic not just symptom chasing."

**Decision:** every council role (Evidence, Challenger, Operator, synthesizer) runs on
`gemma-4-26b-a4b-it-QAT-4bit`, the MoE already resident on oMLX for auto-daily. Each role
keeps its own prompt and separate isolated call. **Thinking off, early_quorum off.**

## Why

The evidence is in `docs/COUNCIL_BENCH_20261019.md`: 20 fixed cases per configuration.

- **Speed (the operator's complaint).** Median 26 s per review vs 225 s for the dense roster
  (granite-30B / mistral-24B / DeepSeek-R1-8B, with a Qwen3.8-27B synthesizer). A live
  production review after the switch took 36 s.
- **Quality held.** 12/20 correct and 16/20 on the key issue, both equal to the old roster.
  Clear rejects went from 0/5 to 3/5. Run-to-run noise on this set is ±3/20, measured on a
  repeat run.
- **Memory and load time.** No new model loads: the four dense models no longer load for a
  council. Three different ~20 GB MoE seats do not fit together on the 64 GB host (oMLX 507;
  load_guard queue), so a mixed-MoE roster is not feasible here.
- **Research.** Mixed-model debate does not beat same-model self-consistency at a matched
  budget (Ferreira 2026, cited in the council landscape review), so one model in three roles
  is not inherently weaker than three models.

## Measured and not adopted

- **early_quorum.** It saves 21% time on slow dense seats but nothing at MoE speed (26 s vs
  27 s), while it drops a reviewer (participation 3.00 → 2.30), so the synthesis loses a view
  and the dissent record.
- **Thinking on.** 88 s, 13/20 key issue, clear rejects 1/5: three times slower and no better.
  It moves the bias toward leniency instead of improving calibration.
- **decompose.** 12/20, clear rejects 2/5: no help with this model.
- **Qwen3.8 in every seat.** The most accurate single run (16/20, 18/20) but 279 s, as slow as
  the problem being fixed.

## Known weakness

gemma4 says REVISE on some proposals that should simply pass (clear support 2/5, vs 5/5 for
the old roster, which never rejected). The next lever is the rubric's SUPPORT definition, not
the model; measure any change with `scripts/council_bench.py`.

## What changed

- `config/portal.yaml` `auto-council`:
  - `model_hint`, `synthesizer_model` and all three `council.members[].model` set to
    `gemma-4-26b-a4b-it-QAT-4bit`, the oMLX id. The council posts to whichever backend
    declares the model, so the oMLX id reaches the resident copy; the Ollama GGUF tag would
    load a second 17 GB copy.
  - Workspace sampling set to the gemma4 card (1.0 / 0.95 / 64). The seats read the card too
    (6ccfeb5d).
- The compliance council (`config/compliance/council.yaml`) is unchanged.
