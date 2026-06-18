# Portal 5 Acceptance Test Results — V6

**Date:** 2026-06-17 22:14:34
**Git SHA:** 0f32f82
**Sections:** S6
**Runtime:** 192s (3m 12s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 7 |
| **Total** | **7** |

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S6 | S6-01 | auto-security routing | ✅ PASS | signals: ['sql', 'inject', 'parameter'] \| routed -> auto-security matches Ollam | 12.6s |
| S6 | S6-02 | auto-redteam routing | ✅ PASS | signals: ['recon', 'exploit', 'pentest'] \| routed -> auto-redteam matches Ollam | 9.0s |
| S6 | S6-03 | auto-blueteam routing | ✅ PASS | signals: ['contain', 'incident'] \| routed -> auto-blueteam matches Ollama:found | 43.3s |
| S6 | S6-04 | Content-aware security routing | ✅ PASS | routed to security workspace: True | 10.0s |
| S6 | S6-05 | auto-redteam-deep routing | ✅ PASS | signals: ['kerberoast', 'spn', 'service principal'] \| routed -> auto-redteam-de | 16.2s |
| S6 | S6-06 | auto-pentest routing (JANG-CRACK) | ✅ PASS | signals: ['impacket', 'getuserspns', 'kerberoast'] \| routed -> auto-pentest mat | 58.4s |
| S6 | S6-07 | auto-purpleteam-exec: routing + execute_ | ✅ PASS | signals: ['nmap', 'scan', 'open'] \| tool_called=True \| routed -> auto-purplete | 40.2s |