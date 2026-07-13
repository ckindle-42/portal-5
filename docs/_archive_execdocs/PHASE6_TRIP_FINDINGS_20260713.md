# Phase 6 deprecation-trip gate — findings (2026-07-13)

**Program:** `coding_task/cleanup/BUILD_PROGRAM_ALIAS_RETIRE_V1.md`

## Result

`PORTAL_ALIAS_TRIP=1` armed across `scripts/validate_system.py` (45/45 checks
pass, 0 warn) and `pytest tests/` (721 passed, 1 pre-existing failure —
`tests/frontend/test_reasoning_display.py::test_pipeline_reasoning_response`
requires a live pipeline with a real API key, unrelated to this program,
confirmed present before any alias-retirement work started).

**`grep -c ALIAS_RESOLVED /tmp/trip-validate.log /tmp/trip-pytest.log` → 0.**

## What this does and does not prove

The trip fires inside `_resolve_legacy_workspace_alias` — server-side code in
`portal/platform/inference/router/preinject.py`, only reachable when a real
HTTP request is handled by the running pipeline (`handlers.py`'s request
path). `validate_system.py` and the pytest suite exercise routing logic
directly or mock the HTTP boundary, so they alone can't prove the trip is
silent against real traffic.

**Correction:** an earlier draft of this document said "no live Ollama/
pipeline stack available in this environment" — that was wrong. This is the
operator's own running Portal 5 instance; `docker ps` showed `portal5-
pipeline` and the full MCP fleet already up and healthy. The container was
just running a **stale image** (built 2026-07-12 17:38, predating the Phase 0
commit at 20:01 that added the trip). Corrected by actually using the live
stack:

1. `./launch.sh rebuild` — rebuilt the pipeline image against current HEAD
   (`fc0477d`), confirmed fresh build timestamp (21:45) postdates all six
   merged phase commits.
2. `docker exec portal5-pipeline python3 -c '...'` — confirmed the
   deprecation-trip code path itself fires correctly inside the rebuilt
   container: `_resolve_legacy_workspace_alias("auto-redteam")` logs
   `ALIAS_RESOLVED alias=auto-redteam base=('auto-security', 'redteam')` and
   returns the correct tuple.
3. Real `/v1/chat/completions` requests against the rebuilt, running
   pipeline for `auto-coding`, `auto-security`, `auto-redteam`, and
   `auto-blueteam` — all four returned HTTP 200. Confirms the alias shim and
   canonical addressing both still route correctly end-to-end after every
   phase of this program's edits, on the real running service.
4. `docker logs portal5-pipeline --since 2m | grep -i alias` — no
   `ALIAS_RESOLVED` lines, confirming the trip is silent under real traffic
   *when off* (its correct default state — `PORTAL_ALIAS_TRIP` isn't
   declared in `docker-compose.yml`'s `portal-pipeline` environment block,
   so it defaults to unset/off in production, exactly as designed).

**Not yet done:** actually arming the trip (`PORTAL_ALIAS_TRIP=1`) on the
*running server process* itself (not just a one-off `docker exec`) and
re-running real traffic through every known call path (Slack/Telegram bots,
blue-triage, the security bench harness) to get a true end-to-end zero-count
against live traffic. That needs `PORTAL_ALIAS_TRIP` added to `docker-
compose.yml`'s `portal-pipeline` environment block (temporarily, for the
test) plus actually driving the Slack/Telegram/blue-triage paths — not done
in this pass. The known holdouts below (§ Known holdouts) are exactly the
paths where this matters most, since they're the ones still sending alias
ids as their literal `model` value.

## Known, documented holdouts (not missed callers — deliberate deferrals)

These will trip the alias resolver if and when they're actually exercised
against a live pipeline. Each was evaluated during Phases 5 and 6 and
deliberately left on the legacy alias rather than force-migrated:

1. **Incalmo's `OPENAI_MODEL` default** (`deploy/portal-5/docker-compose.lab.yml`)
   — third-party OpenAI-compatible client, no verified way to attach a
   `?variant=` query param without risking a silent downgrade from the
   permissive redteam posture to generic security.
2. **`opencode.jsonc`'s entire model picker** + **`pipeline_mcp.py`'s
   `get_workspace_recommendation()` defaults** — same unverified-query-param-
   support constraint, kept in sync with each other.
3. **`portal/modules/security/core/_data.py`'s `EXECUTION_WORKSPACES` /
   `PER_WORKSPACE_TIMEOUT`**, and their downstream consumers in `cli.py`,
   `commands/run.py`, `chain.py`, `matrix.py`, `blue.py`, `exec_chain.py` —
   the security bench harness's own workspace-string vocabulary is the alias
   ids natively; `workspace: str` is threaded bare through
   `call_pipeline()`/`call_pipeline_exec()` (`portal/modules/security/core/
   __init__.py`) as the literal `model` field with no variant-carrying
   mechanism, and that threading fans out across an estimated 100+ call
   sites in the bench execution engine. This is the same category of
   deeply-coupled, execution-engine-internal code that `bench_router.py`
   and `test_routing.py` were correctly left untouched in Phases 3/4 (they
   test/drive the router's *current* real behavior, which still legitimately
   speaks the alias vocabulary pre-Phase-7). Migrating this harness safely
   needs its own dedicated pass — attempting it as a rushed addendum to
   Phase 6 risks exactly the kind of half-done, broken migration this
   program's non-negotiables warn against ("no faked-green").

## Consequence for the rest of the program

- **Phase 7** (router two-layer output canonicalization) is independent of
  this gap — it changes what the router *emits*, not what these known
  holdouts *send directly*. Proceeding to Phase 7 is safe.
- **Phase 8** (shim removal) is explicitly gated on zero live callers. As
  long as items 1-3 above remain unmigrated, the shim **cannot** be safely
  removed — doing so would break Incalmo, opencode's default model, and the
  entire security bench harness. Phase 8 in this pass will keep the shim in
  place and scope the "no alias ratchet" to the code this program *did*
  migrate, explicitly allowlisting the three documented holdouts, rather
  than faking a "zero refs" state that isn't true.

## Follow-on work (not in this program's scope)

- Verify (or build a small wrapper for) Incalmo's / opencode's HTTP client
  query-param support, then migrate both together.
- A dedicated task to thread `variant`/`role` through the security bench
  harness's `call_pipeline()`/`call_pipeline_exec()` and re-key
  `EXECUTION_WORKSPACES`/`PER_WORKSPACE_TIMEOUT` to (base, variant) — this is
  comparable in size to Phases 3+4 combined and should be scoped as its own
  build program, not a Phase 6 addendum.
