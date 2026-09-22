---
id: unit-capability-auk
kind: mixed
title: "AuK MCP — MLX-native speech editing"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/media/tools/auk_mcp.py
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- capability
- mcp
- media
created_at: 1788234000
updated_at: 1788234000
---

# AuK MCP — MLX-native speech editing

## What

The AuK MCP (`portal/modules/media/tools/auk_mcp.py`, port 8940) is a
headless host wrapper over Tencent AuK's Apple Silicon backend. It is
installed by `./launch.sh install-auk` and started as a launchd service.
The tools are `synthesize`, `edit_content`, `edit_paralinguistic`,
`enhance`, and `separate`. Heavy work is a subprocess into the AuK
virtualenv, so the portal package tree does not import the MLX stack.

## How it's used

An operator runs `./launch.sh pull-auk-models` once. That downloads the
base checkpoint, the Flash checkpoint, and the Qwen encoder, then converts
them into the MLX layout the CLI expects. The server defaults to the Flash
variant at 8-bit with sequential loading so the job fits beside the seated
speech stack. Callers pass an upload filename or a public audio URL. The
seated Kokoro and Qwen3 speech server on port 8918 is unchanged, and no
workspace tool list includes these tools.

## Why it exists

The seated speech stack generates and transcribes. It does not rewrite a
word inside a take, shift emotion, denoise a mix, or pull a voice out of
noise. AuK's MLX branch covers those edits. This server exists so that
coverage can be probed on the same machine without swapping the speech
workspace or pinning a persona to a new model.

## Value

Speech editing that the seated stack cannot do runs on the local Metal
accelerator, beside the existing speech server, and stays out of the
workspace defaults until an operator promotes it. The subprocess boundary
keeps the MLX and transformer wheels in the AuK virtualenv.
