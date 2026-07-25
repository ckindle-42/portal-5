---
id: unit-known-limitations-pytest-portal-leaves-real-write-through-test-artifacts
kind: what
title: "KNOWN_LIMITATIONS \u2014 `pytest portal` Leaves Real Write-Through Test Artifacts"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: '`pytest portal` Leaves Real Write-Through Test Artifacts'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.664905
updated_at: 1784946220.664905
---

- **Description**: Some `portal/modules/security/tests/` tests write through the real goal/playbook journal path (`portal/modules/security/core/field_journal/`) and checkpoint path (`portal/modules/security/core/results/checkpoints/`) instead of a `tmp_path`-redirected one, violating the `tmp_path` testing rule (`CLAUDE.md` Testing Rules).
- **Impact**: Running `pytest portal` locally dirties the working tree — new dated entries under `field_journal/` and a modified `field_journal/_index.json`, plus files under `results/checkpoints/`.
- **Mitigation**: `results/checkpoints/` is gitignored. `field_journal/` holds real committed history so it is intentionally *not* gitignored — run `git status` after `pytest portal` and `git checkout -- portal/modules/security/core/field_journal/_index.json` (plus `git clean` any new dated entries) before staging a commit. See `CLAUDE.md` Testing Rules.
- **Fix (open)**: Route the journal writer through a fixture-injected path in the offending tests so `pytest portal` is side-effect-free like `pytest tests/unit`.
