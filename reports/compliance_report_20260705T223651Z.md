<!-- GENERATED FROM grounded results + coverage map — do not hand-edit, re-run `python3 -m bench_security compliance-report` -->
# Portal 5 — Compliance & Framework Posture Report

Results source: `tests/benchmarks/bench_security/results/e2e_system_20260705T091903Z.json`
Generated: 2026-07-05 22:36:51Z

## 1. Executive Summary

| Verdict | Count | % |
|---------|-------|---|
| PROVEN | 0 | 0.0% |
| FAILED | 0 | 0.0% |
| INDETERMINATE | 74 | 88.1% |
| UNAVAILABLE | 10 | 11.9% |

**Top gaps:** 32 technique(s) with no confirmed real-telemetry detection out of 32 in scope.

## 2. Coverage Posture

- **enterprise-attack**: 32 technique(s) tracked
- **ics-attack**: 0 technique(s) tracked

- Eligible: 32  |  Exercised (real episode ran): 29 (90.6%)  |  Detection rule exists: 30 (93.8%)
- **Confirmed detected (real, non-synthetic telemetry, this results file): 0/32 (0.0%)** — the honest number; a detection RULE existing is not the same as a CONFIRMED detection (see Findings below).

## 3. Framework Mapping

| Framework | Control/Tactic/Requirement | Mapped | Detected | % |
|-----------|------------------------------|--------|----------|---|
| mitre-attack | credential-access | 10 | 0 | 0.0% |
| mitre-attack | discovery | 2 | 0 | 0.0% |
| mitre-attack | execution | 5 | 0 | 0.0% |
| mitre-attack | initial-access | 2 | 0 | 0.0% |
| mitre-attack | lateral-movement | 3 | 0 | 0.0% |
| mitre-attack | persistence | 3 | 0 | 0.0% |
| mitre-attack | privilege-escalation | 3 | 0 | 0.0% |
| mitre-attack | reconnaissance | 2 | 0 | 0.0% |
| nerc-cip | CIP-005-6 R1 | 4 | 0 | 0.0% |
| nerc-cip | CIP-007-6 R4 | 23 | 0 | 0.0% |
| nerc-cip | CIP-007-6 R5 | 13 | 0 | 0.0% |
| nist-800-53 | AC-17 | 3 | 0 | 0.0% |
| nist-800-53 | AC-6 | 3 | 0 | 0.0% |
| nist-800-53 | AU-12 | 5 | 0 | 0.0% |
| nist-800-53 | CA-7 | 2 | 0 | 0.0% |
| nist-800-53 | CM-6 | 3 | 0 | 0.0% |
| nist-800-53 | IA-5 | 10 | 0 | 0.0% |
| nist-800-53 | RA-5 | 2 | 0 | 0.0% |
| nist-800-53 | SC-7 | 2 | 0 | 0.0% |

## 4. Findings

| Technique | Matrix | Verdict | Mapped Controls | Remediation |
|-----------|--------|---------|------------------|-------------|
| T1003.001 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1003.003 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1003.006 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1021.002 | enterprise | GAP | lateral-movement, AC-17, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1046 | enterprise | GAP | discovery, CA-7, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1047 | enterprise | GAP | execution, AU-12, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1053.005 | enterprise | GAP | persistence, CM-6, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1059 | enterprise | GAP | execution, AU-12, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1059.004 | enterprise | GAP | execution, AU-12, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1068 | enterprise | GAP | privilege-escalation, AC-6, CIP-007-6 R5 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1078 | enterprise | GAP | persistence, CM-6, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1078.004 | enterprise | GAP | — | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1083 | enterprise | GAP | discovery, CA-7, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1110.003 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1189 | enterprise | GAP | initial-access, SC-7, CIP-005-6 R1 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1190 | enterprise | GAP | initial-access, SC-7, CIP-005-6 R1 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1203 | enterprise | GAP | execution, AU-12, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1210 | enterprise | GAP | lateral-movement, AC-17, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1505.003 | enterprise | GAP | persistence, CM-6, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1537 | enterprise | GAP | — | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1548.001 | enterprise | GAP | privilege-escalation, AC-6, CIP-007-6 R5 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1550.002 | enterprise | GAP | lateral-movement, AC-17, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1552 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1552.005 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1557 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1557.001 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1558.003 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1558.004 | enterprise | GAP | credential-access, IA-5, CIP-007-6 R5, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1592 | enterprise | GAP | reconnaissance, RA-5, CIP-005-6 R1 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1595 | enterprise | GAP | reconnaissance, RA-5, CIP-005-6 R1 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1610 | enterprise | GAP | execution, AU-12, CIP-007-6 R4 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |
| T1611 | enterprise | GAP | privilege-escalation, AC-6, CIP-007-6 R5 | No confirmed detection — deploy/validate the SPL rule and confirm real (non-synthetic) telemetry lands for this technique. |

## 5. Provenance Appendix

| Claim | Source |
|-------|--------|
| T1003.001 coverage | coverage-map:gap-proc-ad_full_compromise-T1003.001 |
| T1003.001 -> mitre-attack | portal-mitre-mcp:T1003.001 |
| T1003.001 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1003.001 -> nerc-cip | NERC CIP standard (public) |
| T1003.001 -> nerc-cip | NERC CIP standard (public) |
| T1003.003 coverage | coverage-map:gap-proc-relay_to_shell-T1003.003 |
| T1003.003 -> mitre-attack | portal-mitre-mcp:T1003.003 |
| T1003.003 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1003.003 -> nerc-cip | NERC CIP standard (public) |
| T1003.003 -> nerc-cip | NERC CIP standard (public) |
| T1003.006 coverage | coverage-map:gap-proc-kerberoast_to_da-T1003.006 |
| T1003.006 -> mitre-attack | portal-mitre-mcp:T1003.006 |
| T1003.006 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1003.006 -> nerc-cip | NERC CIP standard (public) |
| T1003.006 -> nerc-cip | NERC CIP standard (public) |
| T1021.002 coverage | coverage-map:gap-proc-meta3_smb_exploit-T1021.002 |
| T1021.002 -> mitre-attack | portal-mitre-mcp:T1021.002 |
| T1021.002 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1021.002 -> nerc-cip | NERC CIP standard (public) |
| T1046 coverage | coverage-map:gap-proc-meta3_snmp_enum-T1046 |
| T1046 -> mitre-attack | portal-mitre-mcp:T1046 |
| T1046 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1046 -> nerc-cip | NERC CIP standard (public) |
| T1047 coverage | coverage-map:gap-proc-ad_full_compromise-T1047 |
| T1047 -> mitre-attack | portal-mitre-mcp:T1047 |
| T1047 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1047 -> nerc-cip | NERC CIP standard (public) |
| T1053.005 coverage | coverage-map:gap-proc-kerberoast_to_da-T1053.005 |
| T1053.005 -> mitre-attack | portal-mitre-mcp:T1053.005 |
| T1053.005 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1053.005 -> nerc-cip | NERC CIP standard (public) |
| T1059 coverage | coverage-map:gap-proc-vuln_supervisor_rce-T1059 |
| T1059 -> mitre-attack | portal-mitre-mcp:T1059 |
| T1059 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1059 -> nerc-cip | NERC CIP standard (public) |
| T1059.004 coverage | coverage-map:gap-proc-mbptl_ctf_full_chain-T1059.004 |
| T1059.004 -> mitre-attack | portal-mitre-mcp:T1059.004 |
| T1059.004 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1059.004 -> nerc-cip | NERC CIP standard (public) |
| T1068 coverage | coverage-map:gap-proc-meta3_linux_privesc-T1068 |
| T1068 -> mitre-attack | portal-mitre-mcp:T1068 |
| T1068 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1068 -> nerc-cip | NERC CIP standard (public) |
| T1078 coverage | coverage-map:gap-proc-web_nosql_inject-T1078 |
| T1078 -> mitre-attack | portal-mitre-mcp:T1078 |
| T1078 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1078 -> nerc-cip | NERC CIP standard (public) |
| T1078.004 coverage | coverage-map:gap-proc-cloud_breach-T1078.004 |
| T1083 coverage | coverage-map:gap-proc-vuln_nexus_rce-T1083 |
| T1083 -> mitre-attack | portal-mitre-mcp:T1083 |
| T1083 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1083 -> nerc-cip | NERC CIP standard (public) |
| T1110.003 coverage | coverage-map:gap-proc-asrep_to_lateral-T1110.003 |
| T1110.003 -> mitre-attack | portal-mitre-mcp:T1110.003 |
| T1110.003 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1110.003 -> nerc-cip | NERC CIP standard (public) |
| T1110.003 -> nerc-cip | NERC CIP standard (public) |
| T1189 coverage | coverage-map:gap-proc-web_reflected_xss-T1189 |
| T1189 -> mitre-attack | portal-mitre-mcp:T1189 |
| T1189 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1189 -> nerc-cip | NERC CIP standard (public) |
| T1190 coverage | coverage-map:gap-proc-vuln_jackson_deserial-T1190 |
| T1190 -> mitre-attack | portal-mitre-mcp:T1190 |
| T1190 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1190 -> nerc-cip | NERC CIP standard (public) |
| T1203 coverage | coverage-map:gap-proc-mbptl_ctf_full_chain-T1203 |
| T1203 -> mitre-attack | portal-mitre-mcp:T1203 |
| T1203 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1203 -> nerc-cip | NERC CIP standard (public) |
| T1210 coverage | coverage-map:gap-proc-meta3_smb_exploit-T1210 |
| T1210 -> mitre-attack | portal-mitre-mcp:T1210 |
| T1210 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1210 -> nerc-cip | NERC CIP standard (public) |
| T1505.003 coverage | coverage-map:gap-proc-mbptl_ctf_full_chain-T1505.003 |
| T1505.003 -> mitre-attack | portal-mitre-mcp:T1505.003 |
| T1505.003 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1505.003 -> nerc-cip | NERC CIP standard (public) |
| T1537 coverage | coverage-map:gap-proc-cloud_breach-T1537 |
| T1548.001 coverage | coverage-map:gap-proc-web_to_root-T1548.001 |
| T1548.001 -> mitre-attack | portal-mitre-mcp:T1548.001 |
| T1548.001 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1548.001 -> nerc-cip | NERC CIP standard (public) |
| T1550.002 coverage | coverage-map:gap-proc-relay_to_shell-T1550.002 |
| T1550.002 -> mitre-attack | portal-mitre-mcp:T1550.002 |
| T1550.002 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1550.002 -> nerc-cip | NERC CIP standard (public) |
| T1552 coverage | coverage-map:gap-proc-web_ssrf-T1552 |
| T1552 -> mitre-attack | portal-mitre-mcp:T1552 |
| T1552 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1552 -> nerc-cip | NERC CIP standard (public) |
| T1552 -> nerc-cip | NERC CIP standard (public) |
| T1552.005 coverage | coverage-map:gap-proc-cloud_breach-T1552.005 |
| T1552.005 -> mitre-attack | portal-mitre-mcp:T1552.005 |
| T1552.005 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1552.005 -> nerc-cip | NERC CIP standard (public) |
| T1552.005 -> nerc-cip | NERC CIP standard (public) |
| T1557 -> mitre-attack | portal-mitre-mcp:T1557 |
| T1557 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1557 -> nerc-cip | NERC CIP standard (public) |
| T1557 -> nerc-cip | NERC CIP standard (public) |
| T1557.001 coverage | coverage-map:gap-proc-relay_to_shell-T1557.001 |
| T1557.001 -> mitre-attack | portal-mitre-mcp:T1557.001 |
| T1557.001 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1557.001 -> nerc-cip | NERC CIP standard (public) |
| T1557.001 -> nerc-cip | NERC CIP standard (public) |
| T1558.003 coverage | coverage-map:gap-proc-kerberoast_to_da-T1558.003 |
| T1558.003 -> mitre-attack | portal-mitre-mcp:T1558.003 |
| T1558.003 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1558.003 -> nerc-cip | NERC CIP standard (public) |
| T1558.003 -> nerc-cip | NERC CIP standard (public) |
| T1558.004 coverage | coverage-map:gap-proc-asrep_to_lateral-T1558.004 |
| T1558.004 -> mitre-attack | portal-mitre-mcp:T1558.004 |
| T1558.004 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1558.004 -> nerc-cip | NERC CIP standard (public) |
| T1558.004 -> nerc-cip | NERC CIP standard (public) |
| T1592 coverage | coverage-map:gap-proc-web_graphql_introspect-T1592 |
| T1592 -> mitre-attack | portal-mitre-mcp:T1592 |
| T1592 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1592 -> nerc-cip | NERC CIP standard (public) |
| T1595 coverage | coverage-map:gap-proc-web_asset_discovery-T1595 |
| T1595 -> mitre-attack | portal-mitre-mcp:T1595 |
| T1595 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1595 -> nerc-cip | NERC CIP standard (public) |
| T1610 -> mitre-attack | portal-mitre-mcp:T1610 |
| T1610 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1610 -> nerc-cip | NERC CIP standard (public) |
| T1611 -> mitre-attack | portal-mitre-mcp:T1611 |
| T1611 -> nist-800-53 | NIST SP 800-53 Rev 5 |
| T1611 -> nerc-cip | NERC CIP standard (public) |