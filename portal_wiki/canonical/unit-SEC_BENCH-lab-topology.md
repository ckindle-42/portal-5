---
id: unit-SEC_BENCH-lab-topology
kind: what
title: 'Lab topology: Proxmox VMs and LXC containers'
sources:
- type: code
  path: config/lab_targets.yaml
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- bench
- lab
- security
- topology
- verified-v1
created_at: 1784941806.377922
updated_at: 1784941806.377922
---

Proxmox 3 (10.0.0.203) hosts the lab:

| ID | Name | IP | Role |
|---|---|---|---|
| vmid 110 | portal-lab-dc01 | 10.10.11.21 | Domain controller (Windows) |
| vmid 111 | portal-lab-srv01 | 10.10.11.33 | Member server |
| vmid 113 | portal-lab-meta3-win2k8 | 10.10.11.13 | Metasploitable3 Win2k8 |
| lxc 112 | portal-lab-vulhub | 10.10.11.50 | Docker: Redis/LFI/Tomcat/Log4Shell/NFS/VulnerableApp |
| lxc 300 | portal-lab-mbptl | 10.0.1.140 | MBPTL CTF lab |

The vmids, names, and IPs above are pinned in `config/lab_targets.yaml` (host identities) and `.env.example` (`LAB_MBPTL_HOST`/`LAB_MBPTL_LXC_VMID`, `LAB_META3_VMID`, `LAB_VULHUB_VMID`). Metasploitable3 Win2k8 runs FTP, SSH, IIS, SMB, MySQL, RDP, GlassFish, and Elasticsearch per its documented service fleet; the bench probes it on ports 445/3306/80/8282/21 (the `meta3_*` entries in `_LAB_SERVICE_PROBES`). **Its IP is DHCP-assigned, not static** -- it has drifted twice and was last corrected to 10.10.11.13 via MAC-based identification rather than a port-probe guess.

VulnerableApp (lxc 112, 10.10.11.50:80): OWASP project, Docker-native, exposing a broad set of vulnerability classes (SQLi, XSS, XXE, SSRF, command injection, path traversal, IDOR, JWT, and more).

## Why

The topology is recorded here because the bench's lab-exec tier addresses these exact IPs and vmids, and each one has already drifted or been mis-identified at least once (see the correction history in `lab_targets.yaml`). Pinning the identities in one place — and noting which are DHCP-assigned — tells an operator which failure mode to suspect first when a scenario starts failing with connection-refused, and which file to edit when a host moves.
