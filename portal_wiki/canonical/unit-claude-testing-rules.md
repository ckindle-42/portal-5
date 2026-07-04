---
id: unit-claude-testing-rules
kind: why
title: "CLAUDE.md \u2014 Testing Rules"
sources:
- type: design
  path: CLAUDE.md
  section: Testing Rules
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.809301
updated_at: 1783195000.809301
---


- All tests in `tests/unit/` must pass with no network access (`pytest tests/unit/`)
- No test may call a real Ollama, real Open WebUI, or real Docker
- Use `tmp_path` fixtures for file I/O
- Mock `httpx.AsyncClient` for all HTTP calls
- Run before every commit: `pytest tests/unit/ -q && ruff check . && ruff format --check .`
- **The final verify step of any task is `bash scripts/ci_local.sh`**, not a narrow per-file pytest. This mirrors CI's `.github/workflows/unit-tests.yml` exactly (clean env, editable install, same pytest invocation) — it catches the "works locally, fails CI" gap before the push. A task isn't done until the ci-parity gate is green.
- Pre-commit hooks (`.pre-commit-config.yaml`) enforce: ruff lint+format, generated-artifact freshness (`sync-config` idempotent), no duplicate dep pins, **pytest unit suite**. Install once: `pip install pre-commit && pre-commit install`.
- Unit tests also run on every PR and push to `main` via `.github/workflows/unit-tests.yml`.
- **Any change touching `portal_pipeline/router/streaming.py` or the streaming paths of `router_pipe.py` MUST run `./scripts/smoke_stream.sh` against the live stack before commit** — unit mocks cannot detect dependency-contract mismatches (FX1, `34be1eb`). Also runs as part of `./launch.sh test`.
