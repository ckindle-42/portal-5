# Seat–vendor fit v1 — reversion notes

**Date:** 2026-09-25  
**Status:** task stopped and task changes reverted  
**Reverted commit:** `d51dd29a5ff1e9ff39067e5c2cadb147083769af`

This note records the evidence gathered before the incomplete seat–vendor-fit
attempt was stopped. The partial implementation, routing change, card edits,
WFE harness edits, added suites, and added plans were reverted. The notes below
are observations and receipts, not an acceptance claim.

## Findings

### Routing intent and the security seat

Before the partial commit, plain `auto-security` was served by
`hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k`. The configuration also had
a separate `auto-security::uncensored` variant served by
`huihui_ai/baronllm-abliterated:latest-ctx8k`, plus distinct abliterated
red-team and pentest variants.

The partial commit moved only plain `auto-security` to
`glm-4.7-flash:Q4_K_M` and added `scan_code` as a VulnLLM specialist tool.
That replacement was premature: the task says VulnLLM leaves the chat seat,
but it also says the replacement must be chosen on evidence. No completed
uncensored-seat fit or `scan_code` tool-call comparison justified GLM for the
security role. The commit description also incorrectly called GLM “Granite.”
The routing change is reverted; no replacement model is endorsed by this note.

### S3 specialist-tool evidence

The live `scan_code` replay produced two materially different receipts:

* an unfavorable replay recorded 12/15 positive CWE hits with 0/3 clean-code
  false positives;
* after the caller-shortlist fix, the final replay recorded 15/15 positive
  CWE hits, 0/3 clean-code false positives, and 18/18 parsed rows.

The earlier unfavorable receipt remains important regression evidence. The
`scan_code` implementation and its routing/configuration changes were reverted,
so these measurements do not mean S3 is currently deployed or accepted.

### S2 WFE campaign and harness discovery

The corrected oMLX plan expanded to 192 rows across four model arms with
repeats set to three. Campaign `s2_seat_vendor_omlx_seat_v1` was intentionally
stopped after one completed row; 191 rows remain pending. Receipts and logs are
kept in the gitignored campaign directory and `/tmp/wfe_s2_seat_vendor_omlx_seat_v1`.

The completed row was:

* `auto-coding|Qwen3-Coder-30B-A3B-Instruct-4bit|coding|code-cli-args|r0`
* checker outcome: `PASS`; wall time: `900.5s`; turns: `2`; tool calls: `1`
* the second turn ended with `StreamStalledError` after the 885-second hard
  ceiling, with an empty final response and approximately 51 KB streamed
  output; the sandbox artifact made the checker report `PASS` anyway.

This is an important harness result: a coding row can appear to pass its
artifact checker while the run telemetry shows a long stall. It must not be
counted as healthy model fit without reconciling the stall/turn-cap signal.

The first kickoff also omitted the `PLAN=...` environment variable and
materialized the default workload map. Its blocked rows are setup evidence,
not model evidence.

### S4 artifact and credential evidence

The direct Ollama pull for the VulnLLM-R `i1` artifact was blocked by an
Ollama redirect policy on the Hugging Face CDN. The artifact was then obtained
with the Hugging Face CLI and locally built as `vulnllm-r-i1:q4_k_m` using an
explicit Modelfile. It was not benchmarked against the static GGUF before the
task was stopped.

The initial download command did not explicitly source the repository `.env`.
It succeeded through the existing Hugging Face CLI login. The artifact was
subsequently revalidated in a subshell that sourced `.env`; `hf auth whoami`
reported `bobblah`, and the SHA-256 was:

`4f788427c195357162cb50c4a05563031671116a03995f2a5f391f3f35490fd1`

This records credential provenance without recording the token value.

Granite 4.2 and the Qwen3.8 quant-build comparison were not completed.

## Remaining work

S1 card research was not completed as a committed result, S2 was not completed
for either A/B arm, and S4 was not completed. No production model or sampling
change should be inferred from the stopped run. Any restart should first make
the uncensored/guardrail requirement an explicit seat criterion, run the
candidate tool-call comparison, and make stall telemetry override a misleading
artifact-only `PASS` for agentic/coding fit decisions.
