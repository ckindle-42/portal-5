---
id: unit-fact-dockerfile-index
kind: mixed
title: "Dockerfiles \u2014 the image-build index"
sources:
- type: code
  path: Dockerfile.pipeline
- type: code
  path: Dockerfile.mcp
- type: code
  path: Dockerfile.mcp.x86
- type: code
  path: Dockerfile.attack
- type: code
  path: Dockerfile.binresearch
- type: code
  path: Dockerfile.dind
- type: code
  path: Dockerfile.pwsh
claims:
- probe: dockerfiles
  pattern: '{value} Dockerfiles'
confidence: high
tags:
- fact
- operator
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Dockerfiles — the image-build index

7 Dockerfiles define the image surface; each builds a deliberately
different kind of image, and the split is intentional, not incidental.

- `Dockerfile.pipeline` — minimal (fastapi/uvicorn/httpx/pyyaml): the portal
  pipeline only, so it stays small and rebuilds fast.
- `Dockerfile.mcp` — the heavier MCP tool-server image (documents, sandbox,
  music, and the other Docker-based MCPs).
- `Dockerfile.mcp.x86` — the x86 variant of the MCP image for non-Apple-Silicon
  hosts.
- `Dockerfile.attack` — the arm64 lab attacker image (`portal5-attack`,
  Kali-derived) for the `-exec` lab-exec lane, loaded into DinD.
- `Dockerfile.binresearch` — the arm64 static reverse-engineering toolchain
  image (`portal5-binresearch`) for the binresearch MCP harness.
- `Dockerfile.dind` — the docker-in-docker daemon image that hosts the code
  sandbox's throwaway containers.
- `Dockerfile.pwsh` — the PowerShell sandbox image (pwsh on Ubuntu arm64) for
  the `execute_powershell` tool.

## Why

The split is a size-versus-rebuild trade: the pipeline rides on a minimal base
so a hotfix rebuilds in seconds, while the tool servers that carry heavy
dependencies live in the heavier image. The attack, RE, dind, and pwsh images
are purpose-built envelopes — each one gives one tool a hermetic, versioned
runtime without polluting any other surface.
