---
id: unit-mcp-host-workspace
kind: mixed
title: "mcp_host workspace \u2014 canonical path resolution + upload safety"
sources:
- type: code
  path: portal/platform/mcp_host/workspace.py
  commit: ee7ca08a
last_generated_commit: ee7ca08a
claims: []
confidence: high
tags:
- authored-v1
- mcp
- platform
- workspace
created_at: 1785795758.3679879
updated_at: 1785795758.3679879
---

`workspace.py` is the canonical workspace-path resolver for the MCP fleet. It
defines the one place user files live: the workspace root, with `uploads/` and
`generated/<category>/` beneath it, and it resolves that root across the
container and host worlds. It also validates upload paths against path
traversal and asserted public HTTP URLs for the media generation servers.

## Why

Rule 11 makes the shared workspace the only path for user files — a
container-local volume that other services cannot see would strand generated
artifacts. The resolution order (`WORKSPACE_DIR`, then `AI_OUTPUT_DIR`, then
the `/workspace` container default, then `~/AI_Output` host fallback) is the
contract that lets the same code run as a Docker MCP and as a host-native
service. The category whitelist (`transcripts`, `documents`, `images`,
`videos`, `music`, `speech`, `models3d`) is the source of truth `launch.sh
workspace-init` and the docker-compose mounts derive from — adding a category
is editing this set, nothing else. The `resolve_upload_path` traversal guard
exists because an MCP that accepted `../../etc/passwd` from a persona would be
an arbitrary file read; the assert-public-URL check is the counterpart for the
generation servers, which take a remote `image_url` and must not be pointed at
internal addresses.

## Interfaces

`get_workspace_root` resolves the root per the order above;
`get_uploads_dir` and `get_generated_dir(category)` materialise the
subdirectories (the latter raising `ValueError` on an unknown category);
`resolve_upload_path` returns a validated path inside the uploads tree;
`assert_public_http_url` rejects non-public URLs.

## Gotchas

`get_uploads_dir` and `get_generated_dir` create their directories as a side
effect — they are not pure readers, so callers that only want to *know* the
path should not be surprised by the mkdir. The category set is enforced by
raises, not by silent fallback, so a typo in a category surfaces immediately.
