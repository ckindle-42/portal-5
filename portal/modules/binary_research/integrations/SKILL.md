---
name: binary-research
description: Start or resume a static binary-research project via the Portal 5 harness. Use when the operator wants to reverse-engineer, analyze, or research a binary, firmware image, malware sample, crash dump, or unknown file format. Triggers on requests like "research this firmware", "reverse this binary", "analyze this sample", "figure out this file format".
---

# Binary research intake

You are the RELAY for the Portal 5 binary research harness. The harness conducts
a question/answer intake session and owns all the logic — you surface its
questions to the operator and write their answers back. Do NOT invent the
questions yourself; the harness (via a fast MoE) generates them.

Invoke the harness with:
`python -m portal.modules.binary_research.harness <subcommand> --json`

## First use (install the trigger once)

If `/binresearch` isn't yet available, install it first — and DISCOVER the paths
for your own runtime rather than assuming them (see integrations/INSTALL.md):
identify whether you're in OpenCode or Claude Code / Pi, find that runtime's
skills and commands directories, then:
`python -m portal.modules.binary_research.harness install-trigger --skills-dir <found> --commands-dir <found>`

## Flow

1. **Begin.** Get a project name (ask the operator, or infer a short slug from
   their request). Start the session:
   `... intake --project <name> --json`
   The result is `{"state":"asking","question":"..."}`. Relay the `question` to
   the operator verbatim.

2. **Loop.** For each answer the operator gives, write it back:
   `... intake --project <name> --answer "<their answer>" --json`
   - `{"state":"asking","question":"..."}` → relay the new question, wait for the
     next answer, repeat.
   - `{"state":"ready", ...}` → intake is done. Stop asking questions.

3. **Pause at READY (do not run yet).** Tell the operator the scaffold is
   written, and ask them to:
   - place the binaries in `<root>/<name>/artifacts/`
   - review the verifier stubs in `<root>/<name>/verifiers/` and turn each into a
     real pass/fail oracle
   Then WAIT for the operator to explicitly confirm they are ready to run.
   You can check readiness any time with:
   `... status --project <name> --json`  → look for `"ready_to_run": true`.

4. **Run (only after the operator confirms).**
   `... run --project <name>`
   Relay progress lines and the final `Report:` path.

## Rules

- One question at a time. Relay questions verbatim; don't editorialize or answer
  on the operator's behalf.
- Never fabricate answers. If the operator hasn't answered, wait.
- NEVER start the analysis loop (`run`) until the operator confirms after READY.
- If any command reports the RE MCP is unreachable, tell the operator to run
  `./launch.sh build-binresearch && ./launch.sh restart-mcp` and try `preflight`.
