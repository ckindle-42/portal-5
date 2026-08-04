---
id: unit-HOWTO-testing
kind: why
title: "HOWTO \u2014 Testing"
sources:
- type: design
  path: docs/HOWTO.md
  section: Testing
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8661618
updated_at: 1783195000.8661618
---

./launch.sh test            # Run live smoke tests
pytest tests/ -v --tb=short # Run unit tests (no Docker needed)
```

---

*Last updated: 2026-05-21 | Portal 6.1.0*
