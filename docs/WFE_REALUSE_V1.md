# WFE real-use v1 — short multi-turn suites, a lean budget, a blind judge

The lean path through the WFE harness. It exists because the confirm tier's cost
(36 synthetic tasks x 3 repeats per arm) bought repetition, not coverage. This page is
the contract for a real-use suite; the harness itself is `tests/wfe/`.

## A multi-turn task

One JSONL line per task. A task with `turns` sends each scripted user turn on the SAME
conversation, in order: turn 1's tool loop runs to a final answer, then turn 2's user
message is sent, and so on.

```json
{"id": "realuse-01", "workspace": "auto-general", "category": "ops", "source": "operator",
 "fixtures": [],
 "rubric": ["answers the question that was asked", "does not invent a source"],
 "turns": [
   {"user": "Which services are down?",
    "checks": [{"type": "answer_contains", "patterns": ["pipeline"]}],
    "expect_tools": ["repo_search"]},
   {"user": "Do not mention the sandbox again. Write the summary to summary.md.",
    "checks": [{"type": "file_exists", "path": "summary.md"},
               {"type": "must_not_contain", "patterns": ["sandbox"]}]}
 ]}
```

- `checks` is the existing checker vocabulary (`answer_contains`, `tool_grounded`, file
  and office checks, ...) plus `must_not_contain`. A turn that carries only
  `must_not_contain` is refused: an empty answer satisfies it by construction.
- `expect_tools` names tools this turn must actually call. A tool the workspace is not
  offered BLOCKS the row (an instrument gap, never a model FAIL).
- A row PASSes only when every turn's objective checks pass. `evidence.turn_outcomes`
  records each turn's own verdict; a later failing turn cannot be hidden by an earlier
  passing one.
- `rubric` is the judge's copy of what "better" means. Without it the task is not judged.
- `fixtures` are repo-relative files the run needs (audio, office, pdf); production tool
  mode stages them in the run's `in/`, the sandbox mode copies them into the sandbox.
- `workspace`, `category` and `source` are provenance for the suite author. A task that
  names a `workspace` runs only there (a `::variant` lane counts as its base); a plan that
  does not include that workspace expands no row for it.

Single-turn tasks (`instruction` + `checkers`) are unchanged.

## Lean budget

```bash
uv run python -m tests.wfe.campaign --campaign-id realuse_20261030 \
    --plan <plan.yaml> --tier realuse
```

`--tier realuse` runs every task (no screen/confirm split, `screen` is ignored) once.
An arm gets a second draw only where a draw can differ: its served temperature is above
0 and the suite grades objectively. A temperature nobody has recorded is not assumed
deterministic. `screen` and `confirm` keep their existing behaviour.

## Blind pairwise judge

```bash
WFE_JUDGE_MODEL=<local tag> uv run python -m tests.wfe.judge --campaign realuse_20261030
WFE_JUDGE_MODEL=<tag> WFE_JUDGE_URL=http://p40:11434 uv run python -m tests.wfe.judge \
    --campaign realuse_20261030
# or, at the end of a campaign process:
uv run python -m tests.wfe.campaign ... --judge
```

- One pair is judged once both arms hold a row for the same task and repeat. The two
  conversations are rendered without arm, model or timing fields; the order is a stable
  per-pair coin and the model answers `A`, `B` or `tie` plus a reason.
- The endpoint defaults to this host's Ollama (`WFE_JUDGE_URL`) and must be loopback or
  LAN; a public host is refused unless `WFE_JUDGE_ALLOW_REMOTE=1`. There is no default
  model: set `WFE_JUDGE_MODEL` (or `--model`).
- Verdicts live in `<campaign>/judgements/`, are resumable, and are re-asked when the
  rubric or the judge model changes. A judge error is recorded and retried.
- The report shows the preferences beside the pass rates (`1W/0L/2T`). They are
  **reported, not gated**: `tests/wfe/decision.py` reads no judgement, and no
  disposition, curtailment or pass rate depends on one.
