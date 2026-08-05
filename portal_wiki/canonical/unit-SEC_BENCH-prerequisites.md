---
id: unit-SEC_BENCH-prerequisites
kind: what
title: 'Security bench prerequisites: lab VMs, attack image, env config'
sources:
- type: code
  path: .env.example
- type: code
  path: portal/modules/security/core/_data.py
last_generated_commit: 65958b7ff433a91759bbe4778df434a744fa802c
claims: []
confidence: high
tags:
- bench
- prerequisites
- security
- verified-v1
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

These must be present in the environment or `.env` for the lab-exec lane to activate; without `SANDBOX_LAB_EXEC=true` the bench silently falls back to synthetic results.

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

## Why

Every item here is a silent-failure precondition: the bench degrades to synthetic, unreachable, or wrong-model results rather than erroring when one is missing. `SANDBOX_LAB_EXEC` gates the entire lab-exec lane, the `LAB_TARGET_*` addresses are what the attack image actually reaches, and the model list is what the exec chain must have pulled locally before a run starts.
