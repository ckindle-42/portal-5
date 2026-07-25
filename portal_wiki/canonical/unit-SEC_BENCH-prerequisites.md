---
id: unit-SEC_BENCH-prerequisites
kind: what
title: 'Security bench prerequisites: lab VMs, attack image, env config'
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: ddb1cc61
- type: code
  path: .env.example
  commit: ddb1cc61
- type: code
  path: portal/modules/security/core/_data.py
  commit: ddb1cc61
last_generated_commit: ddb1cc61
confidence: high
tags:
- security
- bench
- prerequisites
created_at: 1784945192.2622862
updated_at: 1784945192.2622862
---

## Lab VMs must be running

```bash
docker exec portal5-dind docker run --rm --net bridge portal5-attack:latest \
  sh -c 'nxc smb 10.10.11.21 2>&1 | tail -2 && redis-cli -h 10.10.11.50 ping && \
         nxc smb 10.10.11.13 -u "" -p "" 2>&1 | head -3 && \
         curl -s -o /dev/null -w "%{http_code}" http://10.10.11.50:80/'
```

## attack image in DinD

```bash
docker exec portal5-dind docker images portal5-attack 2>/dev/null | grep latest
# If missing: ./launch.sh build-lab-attack
```

## .env configuration

Required in `.env`:
- `SANDBOX_LAB_EXEC=true`
- `SANDBOX_LAB_IMAGE=portal5-attack:latest`
- `LAB_TARGET_DC=10.10.11.21`
- `LAB_TARGET_SRV=10.10.11.33`
- `LAB_TARGET_WEB=10.10.11.50`

Optional — for Proxmox VM lifecycle (snapshot/restore):
- `PROXMOX_URL`, `PROXMOX_TOKEN_ID`, `PROXMOX_TOKEN_SECRET`
- `LAB_DC_VMID`, `LAB_SRV_VMID`, `LAB_CLEAN_SNAPSHOT`

## MCP sandbox running

```bash
./launch.sh status | grep sandbox
```

## Security models loaded

```
hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M
hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf
huihui_ai/baronllm-abliterated:latest
hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0
```
