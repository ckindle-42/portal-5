# Auto-daily cold-start screen — real-use prompts and judge criteria

Date: 2026-11-20
Source: `tests/wfe/suites/realuse_v1.jsonl` (WFE real-use suite; 7 base `auto-daily` conversations, 6 selected).
Plan: `tests/wfe/plans/autodaily_coldstart_screen_20261120.yaml`
Quality arms: incumbent `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k` vs `qwen3.5:9b-q4_K_M-ctx16k` vs `gemma4:12b-it-q4_K_M-ctx16k`, `tool_mode: production`, one repeat.

## Why these six

All six are base `auto-daily` rows with an objective checker and a `rubric`, so a row is decided by the product's own checks first and the judges second. They cover the seat's daily work — PDF/Word reading, grounded writing, grounded advice, a Python tool loop, and document creation — and every row has a tool requirement or a no-fabrication constraint. `ru-v1-007/063/064/065/066/067/068/069` are `auto-daily::fast`/`::deep` variants and are excluded: the question is the base seat, not its escalation lanes. `ru-v1-008` is `::deep`. The seventh base row, `ru-v1-006`, is dropped to keep the screen at six and to avoid a second four-document read; `ru-v1-032` already exercises file creation.

## The six conversations

### ru-v1-001 — writing, invoice grounding, no second-turn file

1. `I need a short thank-you note for the client. The invoice is final_invoice.pdf. Mention that the timeline slipped by 3 days, and list every charge that is on the invoice.`
2. `Don't make a file. Just tell me which invoice line is the misc supplies charge, and the amount.`

Rubric: read the invoice and write the note in the reply; do not create a document on the second turn; the note is warm and brief.
Objective checks: turn 1 `tool_grounded` on `read_pdf` and `answer_contains` the 3-day slip plus every charge (2400/890/340/180/210); turn 2 `answer_contains` `misc supplies` + 340 and `must_not_contain` any download URL.

### ru-v1-002 — practical guidance, Word grounding

1. `Read drive_notes.docx and give me the drive plan. I need each leg's time and where to eat.`
2. `The day is tight. What does the note say to do, and what should I pack for I-70?`

Rubric: a customized drive plan taken only from the notes; no live weather lookup.
Objective checks: both turns `tool_grounded` on `read_word_document`; turn 1 contains The Kitchen / Sweet Basil / Bin 707 / 45 minutes / 2 hours / 3 hours; turn 2 contains 90 minutes / tire chains.

### ru-v1-003 — practical guidance, no-tool first turn then Word grounding

1. `I'm a new manager. Weekly 1:1s have to stay at 30 minutes. Give me practical advice for running them.`
2. `Read manager_notes.docx and fit the advice to what I wrote down.`

Rubric: how-to advice for a new manager, then grounded in the user's notes; the advice is practical.
Objective checks: turn 1 contains 30 and 1:1 language and must not contain OKR/SMART/Radical Candor or the prompt echoed back; turn 2 `tool_grounded` on `read_word_document` and contains `30 min` + Lisbon or Tokyo.

### ru-v1-004 — writing, long PDF, exact format

1. `Summarize remote_work_handbook_2025.pdf. What changed from last year, and what are the hours?`
2. `Give me exactly three lines I can paste, each starting with a hyphen. Keep the stipend figure.`

Rubric: summarize the handbook in the reply (no new file); do not invent a rule for people outside the country (saying the handbook is silent is fine); exactly three hyphen lines, one carrying the stipend.
Objective checks: turn 1 `tool_grounded` on `read_pdf` and contains Tuesday/Wednesday/Thursday/10am-2pm ET/$500; turn 2 contains $500.

### ru-v1-005 — technical help, execute_python loop, no host write

1. `count_active.py is short one person. Run it with execute_python and tell me why the active count is wrong. The files are under /workspace/uploads/realuse_v1/ru-v1-005/.`
2. `Run a corrected count in execute_python that includes every row, including the last one, and print the total once as active=<number>. Don't try to save a file. This sandbox cannot write back to the host.`

Rubric: the fix is shown by rerunning in the sandbox, not by writing a file; do not claim a file was saved on the host.
Objective checks: both turns `tool_grounded` on `execute_python` (`expect_tools` names it); turn 1 contains the `rows[:-1]`/last-row diagnosis; turn 2 contains `active=5`.

### ru-v1-032 — doing, two Word files with constraints

1. `Make a Word file titled Week Plan. Monday meeting prep. Tuesday coding project, and Tuesday is only 9 to 12. Wednesday travel admin, and I leave by 8am. Thursday research. Friday wrap-up, and Friday ends at 1pm.`
2. `Make a second Word file titled Week Plan Revised. Keep the same days, add an 11am break on Tuesday, and add a Wednesday travel calendar note.`

Rubric: the constraints are in the user message; two Word files.
Objective checks: `office_contains` on both turns; `expect_tools` names `create_word_document`.

## Judge criteria

Two independent judges, neither a candidate nor the incumbent: `mistral-small3.2:24b` (Mistral lineage) and `granite4.1:30b-ctx16k` (IBM lineage). Run the blind pairwise judge twice, once per judge model. The judges see A/B transcripts and the row's `rubric`, never the arm names and never a recommendation.

A candidate **does not lose** a task only when all of these hold:

1. Every objective check on the row passes — `tool_grounded`, `answer_contains`, `must_not_contain`, `office_contains`, and `expect_tools`. A missing tool call, malformed arguments, a failed tool execution, a fabricated tool result, or a claimed file that was not created fails the row regardless of prose quality.
2. The captured trace shows a native structured call for every required tool: correct tool name, correctly typed arguments, and a final answer grounded in that tool's output.
3. Each rubric line is satisfied. A judge preference for the candidate is `win`; for the incumbent is `loss`; `tie` is allowed. Two judges calling `loss` on the same task is a candidate loss. One `loss` and one `tie` is a risk the orchestrator reads, not a pass.
4. No row regresses against the incumbent's own run in the same campaign. The incumbent must reproduce its known result; a row where the incumbent fails the same check is void for that check, not a candidate win.

A candidate is a quality **pass** when it has zero objective-check failures and no judge-recorded loss on the six tasks. It is a quality **fail** on any objective-check failure or on the same task being called a loss by both judges. Anything else is **inconclusive**, which under `docs/MODEL_SEAT_PROCESS.md` keeps the incumbent.

Cold-start and quality are separate gates. The seat changes only when the cold-start pass bar (candidate median first visible content ≤ ½ the incumbent's) and the quality pass both hold in the same campaign.

## Exact commands

```bash
CAMPAIGN=autodaily_coldstart_20261120
uv run python -m tests.wfe.campaign --campaign-id "$CAMPAIGN" \
  --plan tests/wfe/plans/autodaily_coldstart_screen_20261120.yaml --tier realuse
WFE_JUDGE_MODEL=mistral-small3.2:24b uv run python -m tests.wfe.judge --campaign "$CAMPAIGN"
WFE_JUDGE_MODEL=granite4.1:30b-ctx16k uv run python -m tests.wfe.judge --campaign "$CAMPAIGN"
```

The campaign is resumable; do not clear its checkpoint between arms.

## Unproven here

- That all six prompts fit the 16k window with production tool results on both candidates (the derived tag is built at preflight; the preflight records the working window).
- That either candidate emits native tool calls on either engine (the intake probe gates this before any row counts).
- Judge agreement or any preference direction; no judge has seen these arms.
