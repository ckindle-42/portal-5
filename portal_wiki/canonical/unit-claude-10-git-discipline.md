---
id: unit-claude-10-git-discipline
kind: why
title: "CLAUDE.md \u2014 10 \u2014 Git Discipline"
sources:
- type: design
  path: CLAUDE.md
  section: "10 \u2014 Git Discipline"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.80879
updated_at: 1783195000.80879
---


Commit directly to `main` during stabilization. Run tests before every push: `pytest tests/ -q --tb=no`. Commit format: `type(scope): description`. Never force push. Never commit `.env` or cloud/external deps to `pyproject.toml`.
