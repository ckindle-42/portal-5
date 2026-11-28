# Model Seat Process

One page. Governs every model intake and seat change. Replaces open-ended evaluation campaigns.
Adopted 2026-11-07 after four independent reviews (Kimi K3.1 Pro, DeepSeek Flash, GLM 5.3, Codex Astra)
found the evaluation program had lost its decision boundary.

## Rules
1. **A run exists only for a named seat decision.** Before anything runs: the seat, the incumbent, the action
   if the candidate wins, and a budget (rows, hours). No decision, no run.
2. **Live, never simulated.** Tests go through the real product: Open WebUI → Pipeline → engine, with real uploads
   and real tasks from that seat's use. No harness imitation of Open WebUI behaviour, no generated test documents.
   This rule is not seat-specific — it governs the whole project (see `CLAUDE.md`): **live against the system,
   never synthetic and never a test.** Security work runs real lab telemetry through the real review service,
   compliance work uses the real store and corpus, a service change is exercised over real HTTP. A passing test
   suite is a merge gate, never evidence. "Could not be tested live" is a finding to report, not a licence to
   substitute anything else.
3. **Prove the setup live before it carries rows.** One real task per seat through the real UI; the request the
   Pipeline receives is captured as the reference. Judges approve that proof (setup and grading) before any row counts.
4. **Every row carries its own validity evidence:** its Pipeline-side request diffs clean against the live
   reference, and the incumbent reproduces its known result in the same run. Missing either → the row is void.
5. **Find and fix, then continue.** A bug seen live is fixed at its source (product, setup or grading), shown fixed,
   and the run continues. A problem noticed outside the task is fixed too, not logged and left.
6. **Void is not inconclusive.**
   - Grading void → regrade the stored rows after the fix; no rerun.
   - Setup void → fix the cause, prove it with the request diff, rerun. Doesn't count against the model.
   - Valid but inconclusive → counts. Two valid inconclusive runs → the incumbent stays; the question closes.
   - Two setup voids on one seat → the method is wrong: go to a live trial instead of a third run.
7. **A run is a filter; real use decides.** A clear winner goes live in the seat for a 2–3 day trial in real use,
   then kept or reverted (one config edit).
8. **Judges are independent frontier models,** briefed with the same evidence and no recommendation from the
   orchestrator. The orchestrator does not judge its own setup or results. The operator breaks ties and handles
   escalations only. Prefer free/prepaid judge tiers; metered only when those disagree.
9. **"Unproven — keep the incumbent" is a final answer.**

## Seat ledger
One row per open seat question. A row closes with a decision, never with "more testing".

| Seat | Incumbent | Candidate(s) | Question | Default if unproven | Status |
|---|---|---|---|---|---|
| `auto-compliance::reading` (128k) | gemma-4-26b plain | gemma-4-26b QAT; Qwen3.8-27B | Better long-document reading? | Keep plain | Closed 11-07: tie → keep plain (live OWUI 0.13.0, 4 real-corpus questions, full docs 20–38k tokens, trace-verified arms; blind judges GLM + Codex split per question: QAT q1, plain q3, q2/q4 split). Both arms overstate coverage — a reading-quality issue, not a quant one |
| `auto-compliance::reading` (128k) | Qwen3.6-35B-A3B (since 11-28) | — | Does Qwen3.6 beat gemma on the 6-case acceptance? | Qwen3.6 (staged 11-27, promoted 11-28) | Closed 11-28: Qwen3.6 14/18 vs gemma 12/18, 0 altered words vs deterministic `TS5`/`(35s)` garbles on parent+interval in 3/3 runs; ~232 s per ~100k-token turn. Seat moved (`READING_SEAT_SWAP_QWEN36`); 2–3 day real-use trial per rule 7 |
| Vision fallback | gemma-4-26b plain | gemma-4-26b QAT | Better image turns as fallback? | Keep plain | Closed 11-07: tie → keep plain (live OWUI 0.13.0, 3 real-use image tasks; blind judges GLM + Codex: equivalent). Revisit only as disk consolidation if 128k moves to QAT |
| Arm read/check bites | `auto-daily::gemma-fast` | Spark-X2.6 (shadow) | Agree on real arm work, no false accepts? | Keep gemma-fast | Closed 11-07: unproven → keep gemma-fast. All 76 shadow rows are two generated fixtures and the verdict is a format check (`Finding:` present), so they don't count. Shadow stays on passively; reopen at ≥20 real arm comparisons, judged on transcripts |
| `auto-daily` cold start | Nemotron 3.5 Lightning 30B-A3B Q4_K_M-ctx32k | Qwen3.5-9B (`q4_K_M` / oQ4e); Gemma 4 12B (`q4_K_M` / oQ4e) | Much faster cold first token with no quality loss on real auto-daily work? | Keep incumbent | Open 11-20: intake and screen staged (`coding_task/FINDING_AUTODAILY_COLDSTART_*`); live cold/quality run pending |
| `auto-overflow64` | — | gemma-4-26b QAT | — | — | Closed 11-06: QAT (job 108) |
| Bench seat | gemma-4-26b plain | gemma-4-26b QAT | — | — | Closed 11-06: QAT (job 106) |
