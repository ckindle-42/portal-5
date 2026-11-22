# RESULT — lane/hq-inkling-tools-dind

Three config/Docker fixes from `coding_task/BRIEF_HQ_INKLING_TOOLS_DIND.md`. All gates run;
the live settings audit was run read-only (GET `/api/tags`, GET `/v1/models`, `~/.omlx` file
reads — no model calls, no writes) as the brief explicitly directed.

## 1. `HQ` Inkling card expectation — `config/model_card_expectations.yaml`

Added one family entry `inkling-2-mini` (resolves `Inkling-2-Mini-oQ4e-mtp` via
`_norm_key` substring match, longest-match-wins, shared with the runner through
`card_entry`; also covers the sibling oQ3e/4-bit builds). Values:

- `recommended_sampling: {temperature: 1.0, top_p: 0.95}` — temperature 1.0 is the
  card's `generation_config.json` (`do_sample: true`); **top_p 0.95 is honestly labelled
  in a comment as oMLX's global default, NOT a vendor value** (per
  `FINDING_OMLX081_INTAKE.md` §1.5 "do not present it as a card row"), pinned in
  `~/.omlx/model_settings.json` and served by `bench-inkling-2-mini`. Including it makes
  `served_vs_card` pin both served keys so drift on either side now warns.
- `max_context: 262144` — `~/.omlx/model_settings.json` `max_context_window` (the card's
  1M window is not what the deployment serves).
- `harness_policy` deliberately OMITTED: adding `think: "true"` would flip
  `_is_reasoning_model` to true and fire a NEW `reasoning_uncontrolled` WARN on
  `bench-inkling-2-mini` (no `think` pin on the seat), breaking the 0-warn goal. The seat
  records `emits_reasoning: true`; the think-pin decision belongs to the operator.

Audit: `0 FAIL / 2 warn` before → **`0 FAIL / 0 warn`** after (both old warnings on
`bench-inkling-2-mini`: `sampling_hot` became the INFO `sampling_card_over_lane`;
`card_no_ground_truth` gone; no `served_vs_card` on the seat).

## 2. `supports_tools: true` on the two live-probed C1 models

`config/backends.yaml` `omlx-general`: `Qwen3.5-9B-oQ4e-mtp` and
`gemma-4-12B-it-oQ4e-mtp` flipped false→true with the 2026-11-22 live typed tool-call
probe recorded in the inline comment. `config/MODEL_CATALOG.md`: both paragraphs updated
to cite the probe (`finish_reason="tool_calls"`, `get_weather({"location": "Little Rock,
AR"})`) and keep the "documentation is not a probe" history.

## 3. `Dockerfile.dind` Alpine CVE bump

`FROM docker:27-dind` → `FROM docker:28-dind` (tag verified on Docker Hub, arm64 variant
present — Rule 14) and `RUN apk upgrade --no-cache && apk add --no-cache tcpdump`.
No test, script or doc asserts `docker:27-dind` (grep-verified: only a prose mention in
`deploy/portal-5/docker-compose.yml` and CHANGELOG history, left alone). `Dockerfile.mcp`
still uses `docker:27-cli` — outside this brief's scope (the sweep flagged `portal5-dind`
only); flagged for the orchestrator.

## Verification run

- `uv run python -m tests.wfe.settings_audit` (OMLX_API_KEY loaded, oMLX :8085 live) →
  `0 FAIL / 0 warn`.
- `uv run pytest -q tests/unit/ -k "routing or variant or config or workspace or
  settings_audit or dind or dependency_drift"` → 291 passed, 1 skipped.
- Full unit suite → 3113 passed, 22 skipped; `ruff check .` clean; `ruff format --check .`
  clean (1737 files); `ruff check portal/ tests/` clean; complexity `--gate` OK.
- `uv run mypy portal/`: 650 errors from this worktree vs clean on the live checkout —
  investigated to root cause, see UNPROVEN/OPEN. Not caused by this diff (contains no
  Python). The canonical gate is `bash scripts/ci_local.sh` (isolated venv, line 79 uses
  `mypy --exclude "portal/modules/compliance/"`), which the orchestrator runs post-merge.
