---
id: unit-SECURITY_BENCH_EXEC-lab-topology
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Lab Topology"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Lab Topology
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.8964942
updated_at: 1783195000.8964942
---


```
┌─────────────────────────────────────────────────────────┐
│ Proxmox 3 (10.0.0.203)                                  │
│                                                         │
│  vmid 110  portal-lab-dc01       10.10.11.21  (DC, Win2022)    │
│  vmid 111  portal-lab-srv01      10.10.11.33  (member server)  │
│  vmid 113  portal-lab-meta3-win2k8    10.10.11.10  (Metasploitable3 Win2k8) │
│  lxc  112  portal-lab-vulhub      10.10.11.50  (Docker: Redis/LFI/       │
│              Tomcat/Log4Shell/NFS/VulnerableApp)         │
│  lxc  300  portal-lab-mbptl   10.0.1.140   (MBPTL CTF lab)  │
└─────────────────────────────────────────────────────────┘
```
