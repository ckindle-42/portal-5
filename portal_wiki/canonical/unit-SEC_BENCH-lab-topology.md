---
id: unit-SEC_BENCH-lab-topology
kind: what
title: 'Lab topology: Proxmox VMs and LXC containers'
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: d869257b
- type: code
  path: config/lab_targets.yaml
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- security
- bench
- lab
- topology
created_at: 1784941806.377922
updated_at: 1784941806.377922
---

Proxmox 3 (10.0.0.203) hosts the lab:

| ID | Name | IP | Role |
|---|---|---|---|
| vmid 110 | portal-lab-dc01 | 10.10.11.21 | DC, Win2022 |
| vmid 111 | portal-lab-srv01 | 10.10.11.33 | Member server |
| vmid 113 | portal-lab-meta3-win2k8 | 10.10.11.13 | Metasploitable3 Win2k8 |
| lxc 112 | portal-lab-vulhub | 10.10.11.50 | Docker: Redis/LFI/Tomcat/Log4Shell/NFS/VulnerableApp |
| lxc 300 | portal-lab-mbptl | 10.0.1.140 | MBPTL CTF lab |

Metasploitable3 Win2k8 (vmid 113): 2 CPU, 4 GB RAM, 60 GB disk. Open ports: 21 (FTP), 22 (SSH), 80 (IIS), 135 (RPC), 139 (NetBIOS), 445 (SMB/AD), 3306 (MySQL), 3389 (RDP), 4848 (GlassFish), 8080 (Tomcat), 8383, 8484 (Java), 9200 (Elasticsearch). **IP is DHCP-assigned, not static** -- has drifted twice.

VulnerableApp (lxc 112, 10.10.11.50:80): OWASP project, Docker-native, 14 vulnerability types (SQLi, XSS, XXE, SSRF, Command Injection, File Upload, Path Traversal, JWT, Open Redirect, IDOR, LDAP Injection, Clickjacking, Crypto failures, Authentication).
