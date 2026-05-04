# Matrix results archive

Files in this directory predate `TASK_MATRIX_DRIVER_REMEDIATION_V1`
(2026-05-04). They are preserved for postmortem and diff but **must not
be promoted to baseline**. The matrix driver methodology has changed
since these files were written:

- System prompt truncation cap raised from 1600 → 8000 chars
- `response_preview` and `http_status` now captured per scenario
- 7 compliance personas updated to mandate assertion-required structures

A new baseline must be run with the post-remediation driver before any
regression-diff CI gate is restored.

Tracking: `KNOWN_LIMITATIONS.md` → P5-MATRIX-001
