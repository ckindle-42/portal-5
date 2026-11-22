# tests/qat — Portal 5 Release 1.0 QAT Suite

A self-contained, reusable Quality Acceptance Testing package for today's
architecture: Ollama + oMLX 0.8.1, MLX-native media, ARM64 CAD, Obscura
`browser-mcp`, native Open WebUI tool flow. It replaces the legacy
`tests/uat/` + `tests/acceptance/` suites (zero imports from them) once
proven live.

## Run it

```bash
# 1. Plan only — live discovery from config/portal.yaml + workspaces presets,
#    zero network/GPU. This is the first thing to check after any config change.
uv run python -m tests.qat --dry-run

# 2. Full cascade (stages 0→4) with the inter-phase gate between phases:
uv run python -m tests.qat

# Selectors
uv run python -m tests.qat --stage 2 --phase media_heavy
uv run python -m tests.qat --scenario s2-p6-auto-audio::music --api-only
uv run python -m tests.qat --browser-only          # only the Playwright UI layer
uv run python -m tests.qat --stage 4 --emit-worksheets   # rubric worksheets for the operator
uv run python -m tests.qat --stage 4 --ingest-worksheets # validate + freeze filled worksheets

# Re-runs
uv run python -m tests.qat --append       results/qat/release_1_0_<ts>
uv run python -m tests.qat --rerun-failed results/qat/release_1_0_<ts>

# Chat hygiene
uv run python -m tests.qat --cleanup-chats        # delete test chats (default: archive)
```

Exit code 1 when any scenario FAILs or the inter-phase gate BLOCKs.

## Stages

| Stage | What | Source |
|---|---|---|
| 0 | Ground truth: execute_preflight + retired-alias guard, routing baseline, `portal trace` (host/containers/pins/engines/platform), exposure-gap audit, lab_ready, security-sweep freshness | `preflight.py` |
| 1 | Hardening: `/health/all`, `/metrics` power+energy gauges, auth rejection, `bench-*` concurrency=1, negative probes (empty/oversized/invalid-slug/malformed-JSON — never 500), Obscura browser-mcp health + tools + SSRF blocklist + sensitive-field redaction | `hardening.py` |
| 2 | Phased E2E web journeys across all OWUI workspaces (7 phases + compliance smoke) | `scenarios.py` |
| 3 | Security, Hunt & adversarial: canonical `auto-security::<variant>`, Splunk Hunt (botsv1), MITRE/VulnIntel/ICS/OT/NetForensics MCPs, prompt-injection + refusal-preservation, lab-exec (gated on Stage 0 lab_ready) | `scenarios.py` |
| 4 | Adaptive deep multi-turn + rubric challenges per workspace contract; operator scores 1–5 via worksheets | `scenarios.py` |

Between phases `gate.py` runs the inter-phase gate: Pipeline `/health` with
`backends_checked=true`, Ollama + oMLX 0.8.1 health with **residency-checked
eviction** (never unload a cold model — oMLX answers HTTP 400 for those),
`vm_stat` memory guard (<80% used, nothing resident, 600 s cap), and the
retained MLX media services (`:8918/:8933/:8935`) reported as memory-pressure
sources only — never killed.

## Compliance honesty

`auto-compliance` / `auto-compliance::reading` run smoke turns and every row
carries the annotation `IN_SERVICE=False` pending the V6 ACME corpus sweep.
They are never silently skipped and never faked green.

## Browser UI layer

`browser_ui.py` drives Open WebUI on :8080 with Playwright (login, release
overlay dismissal, workspace roster check, real UI turn with stop-circle
completion, `<details>` toggle, file upload hook, screenshots, console error
capture). Playwright is a **lazy import**: without it, `tests.qat` still
imports and runs, and browser scenarios report `SKIP` with an actionable
note. Portal's tool-side browser automation is Obscura (`browser-mcp` :8923),
tested live in Stage 1.

## Outputs

`results/qat/release_1_0_<ts>/`

- `results.jsonl` — one row per scenario (status, defect class, chat id,
  served model, backend, artifacts, evidence)
- `QAT_REPORT.md` — capability-by-capability acceptance matrix, exposure
  gaps, categorized defects (PRODUCT_BUG / UX_RENDER_GAP / MODEL_QUALITY_GAP /
  INFRA_ENV_GAP), annotations
- `review.html` — operator [GATE] sign-off packet: per-scenario verdict
  selects, exportable verdicts JSON, screenshot gallery
- `worksheets/` + `worksheets_frozen.json` — Stage 4 rubric worksheets

## Configuration

Named `.env` keys only (never `source .env`): `OPENWEBUI_URL`,
`PIPELINE_URL`, `PIPELINE_API_KEY`, `OPENWEBUI_ADMIN_EMAIL`,
`OPENWEBUI_ADMIN_PASSWORD`, `OLLAMA_URL`, `OMLX_URL`, `OMLX_API_KEY`,
`AI_OUTPUT_DIR`, `PORTAL_ARM_APPROVAL_TTL_SECONDS`.

Counts and rosters are discovered at run time from `config/portal.yaml`,
`imports/openwebui/workspaces/workspaces_all.json`, `config/personas/*.yaml`
and `config/backends.yaml`. Nothing is hardcoded.

## Offline tests

```bash
uv run pytest tests/qat/tests/ -v   # all network + subprocess calls mocked
```
