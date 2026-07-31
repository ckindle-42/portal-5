---
id: unit-blue-orchestration-v2-capture-gap
kind: why
title: 'Blue Orchestration V2: eleven lab capture gaps resolved'
sources:
- type: code
  path: portal/modules/security/core/siem/collect.py
- type: code
  path: portal/modules/security/core/siem/network_capture.py
- type: code
  path: portal/modules/security/core/siem/capture_enrichment.py
- type: code
  path: scripts/lab_targets.py
- type: code
  path: scripts/lab_ready.py
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: portal/modules/security/tools/proxmox_mcp.py
- type: code
  path: scripts/verify_attack_image.py
- type: config
  path: config/attack_image_contract.json
last_generated_commit: ''
confidence: high
tags:
- security
- blue-team
- resolved
- blue-orchestration-v2
- telemetry-capture
created_at: 1784366416.7372081
updated_at: 1785515010.0
---

## Resolution state

The eleven scenarios that lacked trustworthy replay data are resolved. Each
latest capture has schema-v2 episode scope, a real PCAP, embedded
`validity.valid=true`, and 100% scenario-specific technique coverage:

| Scenario | Required observed proof |
|---|---|
| `meta3_phpmyadmin_rce` | vulnerable phpMyAdmin 3.5.8, root login, reflected Windows service identity |
| `meta3_rails_console_rce` | exposed web-console request and reflected `nt authority\\system` |
| `meta3_rdp_standard_auth` | bounded Impacket credential validation and Windows 4624/NTLM evidence |
| `vuln_adminer_ssrf_recon` | server-side requests distinguishing two internal ports |
| `vuln_ajreport_rce` | bypass endpoint plus reflected `id` output |
| `vuln_docker_api_rce` | unauthenticated create/start/logs API flow plus reflected `id` output |
| `vuln_druid_rce` | sampler exploit plus reflected `id` output |
| `vuln_hugegraph_rce` | Gremlin exploit plus PCAP-decoded gzip response containing `id` output |
| `vuln_jimureport_rce` | FreeMarker endpoint plus reflected `id` output |
| `vuln_shellshock_rce` | Shellshock CGI request plus reflected `id` output |
| `vuln_spring4shell_rce` | class-loader binding, correctly named JSP, and reflected `id` output |

## Recurrence controls

- The lab-exercise image contract now requires 71 commands, 13 support files,
  and executable runtime checks for `nmap` and `impacket-rdp_check`. Presence
  on disk alone is not accepted. `nmap` capabilities are compatible with the
  default container bounding set.
- Theory remains separate: only the 33 `EXEC_SEQUENCES` lab exercises drive
  the image contract. Theory-only target-local exercises do not dispatch into
  the attack container.
- Meta3 is discovered by VM MAC after DHCP drift. Rails/web-console and the
  matching vulnerable phpMyAdmin 3.5.8 service are repaired idempotently and
  persisted across clean VM boots.
- Published ports must answer HTTP before readiness succeeds, including
  single-port services whose TCP listener opens before the application.
- Episode PCAP starts only after tcpdump is ready, drains before shutdown,
  retains both ends of long exchanges, and reconstructs gzip HTTP responses
  from TCP sequence data so reflected proof remains validator-visible.
- Technique validation uses scenario-specific evidence signatures. An exploit
  request by itself cannot certify command execution.

The broader `lab-ready` board still reports the DC, SRV, and Web static
connectivity checks as red from the nested sandbox. That is a separate lab
infrastructure-health item, not one of these eleven capture gaps.
