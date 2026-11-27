# FINDING — sandbox session persistence + QAT leak false-FAIL (BRIEF_SANDBOX_SESSION_PERSISTENCE_20261127)

Lane: `lane/sandbox-session` · base `bc66578fb` · commits `56988bacb` (sandbox), `c4f3c40ed` (QAT grader).

## Defect 1 — /session exists but is not writable, so session_id persisted nothing

**Root cause (verified against the live volume, not reasoned).** `mcp-sandbox` runs as the
non-root `portal` user (docker-compose entrypoint `su portal`, uid 999). `_session_dir()`
created `data/sandbox/sessions/v2/<sha256>` with the default umask mode (0755/0775, owner 999).
The session dir is bind-mounted into the exec container (`-v …:/session`), which runs as root
but with `--cap-drop ALL` — root there has no `CAP_DAC_OVERRIDE` and lands in the "other"
permission class (`r-x`), so every write under `/session` raised `PermissionError`. This is the
exact bug class already fixed for `/out` (`out_dir.chmod(0o777)` in `_run_in_docker`, with the
same rationale comment). `/tmp` is a per-run tmpfs — nothing there was ever going to persist.

**Live evidence** (read-only inspection of `portal-5_sandbox-work`, the QAT session included):

```
$ docker run --rm -v portal-5_sandbox-work:/x:ro alpine ls -lan /x/sessions/v2 | grep c952d7
drwxrwxr-x 2 999 999 4096 Nov 27 17:45 c952d7b5949ad90f5fe496b325a00428442d006210d69c38dc39832d14ebad31
$ docker run --rm -v portal-5_sandbox-work:/x:ro alpine cat /x/sessions/v2/c952….owner
fetchall-demo
$ docker run --rm -v portal-5_sandbox-work:/x:ro alpine ls -la /x/sessions/v2/c952…/
total 8        # empty — every write the model attempted had failed
```

**Fix** (`56988bacb`): `_session_dir()` now `chmod 0o777`s the session leaf on every call —
matches `/out`'s existing treatment and repairs already-broken sessions (incl. `fetchall-demo`)
on next use. Regression test: mode assertion added to the existing
`test_session_directories_keep_distinct_ids_separate` (fails 0755 before, passes after).

**/session vs /tmp decision:** the MCP's own manifest (`config/inference/tools_manifest_code_sandbox_mcp.json`,
published via `align_native_tools`) documents "Optional session_id persists /session files and
packages", and the code mounts `/session` — code and schema already agreed; only the permission
was broken. No schema change needed.

## Defect 2 — QAT "raw tool error leaked: Traceback" was a grader false-FAIL

The `<details><summary>Tool results</summary>` block is **Pipeline product design, not a leak**:
`portal/platform/inference/router/tools.py:format_tool_result_carry` builds it, both routers
append it to the final answer (`streaming.py:1191,2070`, `non_streaming.py:669,750`), it is on
by default (`PORTAL_TOOL_RESULT_CARRY=true`), `tests/unit/test_pipeline_hardening.py:1814`
asserts the exact prefix, and Portal's own trace CLI (`cli/trace/owui.py:33`) partitions the
model's answer from the receipt on this same marker. Its 220-char tool-result excerpts are
HTML-escaped but `Traceback (most recent call last):` contains no escapable characters, so the
grader's marker scan matched the Pipeline's receipt and failed an honest model answer.

**Fix** (`c4f3c40ed`): `tests/qat/artifacts.py:raw_tool_error_leak` strips the Pipeline carry
block (closed or truncated-unclosed) before marker matching. Single choke point — all four call
sites (runner.py ×2, uat_behavioral.py ×2, owui_client.py) inherit it. Verified offline:
model answer + carry containing a Traceback → `None`; model-authored Traceback → still flagged.

## The prior GGUF pass (2,023 s) — reasoned only, receipts unreachable

No `fetchall-demo`/2026-11-27 QAT receipt exists under `/Users/chris/projects/portal-5/results/qat`
(newest is Nov 24) or any worktree, so this cannot be evidenced from transcripts here. From the
code: the PermissionError hits **any** engine whose calls pass `session_id` and write `/session`
across calls — nothing in the path is engine-specific. The GGUF pass therefore most likely used
a different tool-use strategy: no `session_id`, or script-write-and-run inside one call, or
`/out` — no cross-call file dependency, so it never touched the broken mount. Unverified.

## Second defect found — NOT fixed (out of brief scope)

`_workspace_mount_args` creates the per-run `work_dir/workspace` the same way (portal-owned
0755) and mounts it `rw` at `/workspace`, which the live probe also found non-writable — the
code comment says "Writable per-run /workspace". Same root cause and same one-line fix if the
orchestrator wants it; the brief's property list covers only session persistence, so it is
reported, not changed.

## Orchestrator live proof

1. `./launch.sh rebuild && ./launch.sh up` (mcp-sandbox image carries the fix), then:
2. Two-call probe against :8914 (host port):

```bash
uv run python - <<'EOF'
from portal.platform.inference.cli.trace.mcps import mcp_call
url = "http://127.0.0.1:8914"
sid = "session-persist-probe-20261127"
print("reset :", mcp_call(url, "reset_session", {"session_id": sid}))
print("call1 :", mcp_call(url, "execute_python", {
    "code": "open('/session/probe.txt','w').write('persisted'); print('wrote')",
    "session_id": sid}))
print("call2 :", mcp_call(url, "execute_python", {
    "code": "print(open('/session/probe.txt').read())",
    "session_id": sid}))
print("reset :", mcp_call(url, "reset_session", {"session_id": sid}))
EOF
```

   Worked: call1 `success: True, stdout 'wrote'`; call2 `success: True, stdout 'persisted'`.
   Didn't: call1 stderr `PermissionError … /session/probe.txt` (old image) or call2
   `FileNotFoundError` (mount missing).
3. `uv run --extra dev python -m tests.qat --scenario s4-auto-coding-core` — the row passes on
   the model's own answer; a `raw tool error leaked: Traceback` FAIL can now only come from
   model-authored text outside the Pipeline's details block.

## Gates (worktree, synced venv)

`uv run pytest tests/unit/ -q` → 4143 passed, 46 skipped · `uv run ruff check .` → All checks
passed · `uv run ruff format --check .` → 1725 files already formatted · `uv run mypy portal/`
→ Success: no issues in 738 files · `complexity_report.py --gate` → all gated totals under
ceiling (unwired_scripts at 25/25 — no scripts added).
