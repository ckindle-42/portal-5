---
id: unit-HOWTO-testing
historical: true
kind: why
title: "HOWTO \u2014 Testing"
sources:
- type: design
  path: docs/HOWTO.md
  section: Testing
confidence: high
tags:
- docs
- HOWTO

---

./launch.sh test            # Run live smoke tests
pytest tests/ -v --tb=short # Run unit tests (no Docker needed)
```

---

*Last updated: 2026-05-21 | Portal 6.1.0*
