#!/usr/bin/env python3
"""WFE campaign driver — arm-at-a-time fitness execution with offline rescore.

Shape follows the house pattern for long unattended runs
(tests/benchmarks/bench_judgment_probe_v6.py, scripts/run_hauhaucs_full_sweep.sh):

  one arm per invocation   a persistent connection failure or a leaked handle in
                           one model cannot poison the remaining 16. The shell
                           launcher loops; this process runs a single model.
  --debug-dir              one <arm>.debug.jsonl per arm, one line per task-run:
                           the exact request, the UNTRUNCATED response, every
                           tool call with its full output, the resulting sandbox
                           tree, the per-checker verdict, tokens and timing.
                           Enough to review WHY a run scored, or to re-score it.
  --rescore DIR            re-grade every recorded run with NO model calls —
                           seconds, not the 30-60 hours the campaign cost. The
                           checkers in this harness were wrong once already;
                           this is the difference between a one-line fix and
                           re-running the fleet.
  --notify                 start / per-arm / done through the Portal dispatcher,
                           gated on NOTIFICATIONS_ENABLED.
  --append                 add arms, suites or repeats to a live campaign
                           without disturbing a single completed row.

Interactive / targeted:
  --smoke                  one arm, one task, full debug record printed. This is
                           the end-to-end validation to run BEFORE launching a
                           multi-day sweep.
  --arm TAG                run exactly this model
  --all-suites             every suite, not just the arm's home + discovery —
                           "the variety of tasks it may actually need to do"
  --suite / --task         narrow further

Unattended:
  scripts/wfe_sweep_unattended.sh  the kickoff: preconditions, stack down, evict,
                           preflight, sweep, report, stack restored via trap
  scripts/wfe_campaign.sh  loops arms in fresh processes, skips completed arms,
                           checks Ollama between arms, appends to a progress log
  --watch                  live per-arm view of a sweep in flight — row counts,
                           the arm currently running, and an ETA from what rows
                           have actually cost. Read-only and Ctrl-C safe.
  --status                 the same numbers, once, without the refresh loop
  --health                 ONE verdict for an unattended supervisor checking in
                           on a schedule, with an exit code to branch on:
                           0 OK  1 DONE  2 STALLED  3 DEGRADED. Stall is judged
                           against the previous call (recorded in the campaign
                           dir), because "no row finished in an hour" is the only
                           honest signal when one row may take thirty minutes.

Usage:
  uv run python -m tests.wfe.campaign --plan tests/wfe/workloads.yaml --smoke
  uv run python -m tests.wfe.campaign --campaign-id wfe_full --arm <tag> --repeats 3 \\
      --debug-dir tests/wfe/results/debug --notify
  uv run python -m tests.wfe.campaign --campaign-id wfe_full --append --arm <new-tag>
  uv run python -m tests.wfe.campaign --rescore tests/wfe/results/debug --campaign-id wfe_full
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.runner import (
    OLLAMA,
    TOOL_NAMES,
    load_suite,
    make_sandbox,
    preflight_harness,
    run_task,
    think_policy,
    workspace_context,
)
from tests.wfe.schema import (
    INSTRUMENT_OUTCOMES,
    MANIFEST_SCHEMA_VERSION,
    Outcome,
    ResultRow,
    env_fingerprint,
    sha12,
)

REPO = Path(__file__).resolve().parents[2]
CAMPAIGNS = REPO / "tests" / "wfe" / "results" / "campaigns"
SUITE_DIR = REPO / "tests" / "wfe" / "suites"
DEFAULT_REPEATS = 3
#: Production fidelity base: the pipeline serves /v1 non-streaming, no forced
#: response format. `think` is filled in per workspace by campaign_harness().
CAMPAIGN_HARNESS = {"endpoint": "v1", "stream": False, "think": "default", "format": "none"}


def campaign_harness(wsc: dict) -> dict:
    """The harness dimensions for one workspace's runs. `think` is resolved the
    way production resolves it: the workspace's explicit `think` bool wins;
    otherwise the model card's harness_policy.think; otherwise the model's
    native default. A test of model X in workspace Y must run X the way Y is
    configured, including a misconfiguration — that is the signal Y needs
    fixing, or that X is not a fit."""
    h = dict(CAMPAIGN_HARNESS)
    ws_think = wsc.get("think")
    if ws_think is not None:
        h["think"] = "true" if ws_think else "false"
    else:
        h["think"] = think_policy(wsc.get("model") or "")
    return h


#: Cap on any single captured file in a debug record. Large enough for real
#: source files, small enough that a debug jsonl stays reviewable.
DEBUG_FILE_CAP = 100_000
DEBUG_TREE_CAP = 60

#: Prefix on a row note that marks the block as "preflight said REVIEW", which is
#: retryable, as opposed to a task-level block (offline `requires_network`), which
#: is not. execute_arm re-offers only rows carrying this prefix.
_PREFLIGHT_BLOCK = "preflight REVIEW: "


# --------------------------------------------------------------------------
# logging / notification
# --------------------------------------------------------------------------


def _log(campaign_dir: Path, msg: str) -> None:
    line = f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    print(line, flush=True)
    campaign_dir.mkdir(parents=True, exist_ok=True)
    with (campaign_dir / "progress.log").open("a") as fh:
        fh.write(line + "\n")


def _notify(event_type: str, message: str, metadata: dict | None = None) -> None:
    """Fire through the Portal notification dispatcher, gated on
    NOTIFICATIONS_ENABLED — same pattern as tests/uat/notify.py and the
    compliance seat sweep. Never raises into the campaign."""
    if os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() not in ("true", "1", "yes"):
        return
    try:
        import asyncio

        from portal.platform.inference.notifications.channels.pushover import PushoverChannel
        from portal.platform.inference.notifications.channels.slack import SlackChannel
        from portal.platform.inference.notifications.channels.telegram import TelegramChannel
        from portal.platform.inference.notifications.dispatcher import NotificationDispatcher
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        dispatcher = NotificationDispatcher()
        for ch in (SlackChannel, TelegramChannel, PushoverChannel):
            dispatcher.add_channel(ch())
        event = AlertEvent(
            type=EventType(event_type.lower()),
            message=message,
            workspace="wfe-campaign",
            metadata=metadata or {},
        )
        asyncio.run(dispatcher.dispatch(event))
    except Exception as e:
        print(f"  WARNING: notification failed: {e}")


def ollama_reachable() -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/version", timeout=5) as r:
            return bool(json.load(r))
    except Exception:
        return False


#: Ceiling on waiting for a model to leave memory. Reached only if Ollama never
#: reports the release; the normal path returns as soon as /api/ps is clean.
DRAIN_TIMEOUT_S = 180
_DRAIN_POLL_S = 2


def unload_model(tag: str) -> None:
    """Ask Ollama to release one model (`keep_alive: 0`). Fire and forget."""
    import urllib.request

    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=json.dumps({"model": tag, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with contextlib.suppress(Exception):
        urllib.request.urlopen(req, timeout=60).read()


def loaded_models() -> list[str]:
    """Tags Ollama currently holds resident, per /api/ps."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
            return [m["name"] for m in json.load(r).get("models") or []]
    except Exception:
        return []


def drain_model(tag: str, timeout_s: int = DRAIN_TIMEOUT_S) -> bool:
    """Release `tag` and WAIT until Ollama reports it actually gone.

    Fire-and-forget is not a drain. The release is asynchronous, so without the
    wait the next arm begins loading ~20GB while the previous model is still
    resident — which is how a 64GB box ends up 41GB into swap measuring paging
    instead of models. Event-driven (poll /api/ps) with a safety ceiling, per the
    house rule for waits: never a blind sleep."""
    unload_model(tag)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if tag not in loaded_models():
            return True
        time.sleep(_DRAIN_POLL_S)
    return False


def drain_others(keep: str, timeout_s: int = DRAIN_TIMEOUT_S) -> list[str]:
    """Evict every resident model that is not `keep`, and wait for each.

    The bench/UAT rule — evict unconditionally on model change, never on a
    memory-percentage heuristic — because OLLAMA_MAX_LOADED_MODELS (5 here) will
    happily stack arms until the machine, not the model, is what is measured.
    Also covers the case the arm's own release cannot: a previous arm's process
    that was killed and never got to clean up.

    A model some service pinned at keep_alive=-1 (the pipeline's intent
    classifier) is evicted too. That is deliberate — it is memory the arm needs,
    and the owning service reloads it on its next request."""
    evicted = []
    for tag in loaded_models():
        if tag == keep:
            continue
        drain_model(tag, timeout_s)
        evicted.append(tag)
    return evicted


def model_sizes() -> dict[str, int]:
    """Installed tag -> on-disk bytes, for smallest-first arm ordering."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as r:
            return {m["name"]: m["size"] for m in json.load(r)["models"]}
    except Exception:
        return {}


def config_dirty() -> list[str]:
    """A campaign must not mutate production config."""
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain", "--", "config/"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return [ln for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


# --------------------------------------------------------------------------
# matrix
# --------------------------------------------------------------------------


def expand_matrix(
    plan_path: Path,
    repeats: int = DEFAULT_REPEATS,
    all_suites: bool = False,
    only_arm: str | None = None,
    only_suite: str | None = None,
    only_task: str | None = None,
) -> list[dict]:
    """Expand the plan into one row per (workspace, arm, suite, task, repeat).

    Full power up front — no screening tier. The operator's intent is to test the
    models themselves over a multi-day run, and a comparison that was never run
    at production sampling has not been made.

    Rows are keyed by run_id and carry their own state, which is what makes the
    campaign resumable, appendable and honest about what did not run."""
    plan = yaml.safe_load(plan_path.read_text()) or {}
    every = sorted(p.stem for p in SUITE_DIR.glob("*.jsonl") if not p.stem.endswith("_full"))
    rows: list[dict] = []
    for ws_id, wl in (plan.get("workloads") or {}).items():
        home = wl.get("home")
        suites = every if all_suites else [home] + list(wl.get("discovery") or [])
        arms = wl.get("arms") or {}
        ordered = [("incumbent", arms.get("incumbent"))] + [
            ("challenger", c) for c in (arms.get("challengers") or [])
        ]
        for role, tag in ordered:
            if not tag or (only_arm and tag != only_arm):
                continue
            for suite in dict.fromkeys(s for s in suites if s):
                if only_suite and suite != only_suite:
                    continue
                suite_path = SUITE_DIR / f"{suite}.jsonl"
                if not suite_path.exists():
                    rows.append(
                        _row_stub(ws_id, tag, role, suite, suite_path, "MISSING", 0, suite == home)
                        | {
                            "state": Outcome.HARNESS_ERROR.value,
                            "note": f"suite file not found: {suite_path}",
                        }
                    )
                    continue
                for task in load_suite(suite_path):
                    if only_task and task["id"] != only_task:
                        continue
                    for rep in range(repeats):
                        rows.append(
                            _row_stub(
                                ws_id, tag, role, suite, suite_path, task["id"], rep, suite == home
                            )
                        )
    # Arm-major: every task for a model runs while its weights are resident.
    rows.sort(key=lambda r: (r["arm"], r["workspace"], r["suite"], r["task_id"], r["repeat"]))
    return rows


def _row_stub(ws_id, tag, role, suite, suite_path, task_id, rep, is_home) -> dict:
    return {
        "run_id": f"{ws_id}|{tag}|{suite}|{task_id}|r{rep}",
        "workspace": ws_id,
        "arm": tag,
        "arm_role": role,
        "suite": suite,
        "suite_path": str(suite_path),
        "task_id": task_id,
        "repeat": rep,
        "is_home": is_home,
        "state": "PENDING",
    }


def open_campaign(cid: str, plan_path: Path, matrix: list[dict], append: bool) -> Path:
    """Create a campaign, or append rows to a live one.

    Append is additive only: an existing run_id keeps its recorded state. This is
    what lets a new challenger, a new suite or extra repeats join a sweep that is
    already 20 hours in without discarding any of it."""
    d = CAMPAIGNS / cid
    (d / "rows").mkdir(parents=True, exist_ok=True)
    (d / "preflight").mkdir(parents=True, exist_ok=True)
    mpath = d / "manifest.json"
    if mpath.exists():
        manifest = json.loads(mpath.read_text())
        if not append:
            return d
        known = {r["run_id"] for r in manifest["rows"]}
        added = [r for r in matrix if r["run_id"] not in known]
        manifest["rows"].extend(added)
        manifest["rows"].sort(
            key=lambda r: (r["arm"], r["workspace"], r["suite"], r["task_id"], r["repeat"])
        )
        manifest.setdefault("appends", []).append(
            {"utc": dt.datetime.now(dt.UTC).isoformat(), "added": len(added)}
        )
        mpath.write_text(json.dumps(manifest, indent=1))
        print(f"appended {len(added)} rows ({len(matrix) - len(added)} already present)")
        return d
    mpath.write_text(
        json.dumps(
            {
                "schema": MANIFEST_SCHEMA_VERSION,
                "campaign_id": cid,
                "plan": str(plan_path),
                "plan_sha": sha12(plan_path.read_text()),
                "created_utc": dt.datetime.now(dt.UTC).isoformat(),
                "env": env_fingerprint(OLLAMA),
                "config_dirty_at_start": config_dirty(),
                "rows": matrix,
            },
            indent=1,
        )
    )
    return d


def load_manifest(d: Path) -> dict:
    return json.loads((d / "manifest.json").read_text())


def save_manifest(d: Path, m: dict) -> None:
    (d / "manifest.json").write_text(json.dumps(m, indent=1))


def _row_path(d: Path, run_id: str) -> Path:
    return d / "rows" / (sha12(run_id) + ".json")


# --------------------------------------------------------------------------
# debug capture / offline rescore
# --------------------------------------------------------------------------


def capture_tree(root: Path) -> dict:
    """Snapshot the sandbox so file-based checkers can be re-graded offline.

    Without this, --rescore could only re-grade text checkers; hidden_pytest,
    file_exists, file_contains and immutable would all need the models re-run."""
    out: dict = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file() or len(out) >= DEBUG_TREE_CAP:
            continue
        rel = str(p.relative_to(root))
        if any(part in {"__pycache__", ".pytest_cache"} for part in p.parts):
            continue
        try:
            data = p.read_bytes()
        except Exception:
            continue
        if len(data) > DEBUG_FILE_CAP:
            out[rel] = {"truncated": True, "bytes": len(data)}
            continue
        try:
            out[rel] = data.decode()
        except UnicodeDecodeError:
            out[rel] = {"binary": True, "bytes": len(data)}
    return out


def rehydrate_tree(tree: dict) -> Path:
    d = Path(tempfile.mkdtemp(prefix="wfe_rescore_"))
    for rel, body in (tree or {}).items():
        if not isinstance(body, str):
            continue
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    return d


def write_debug(debug_dir: Path, arm: str, record: dict) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    f = debug_dir / (arm.replace("/", "_").replace(":", "_") + ".debug.jsonl")
    with f.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


#: Outcomes decided by run_task from RUN telemetry, not by a checker: a stall,
#: an exhausted turn budget, a blocked-offline task, an all-errored tool loop.
#: apply_checkers cannot re-derive these from a static record, so --rescore must
#: preserve them — unless the re-graded checker now says PASS, in which case a
#: too-strict checker was the real reason the run looked incomplete.
_RUN_TELEMETRY_OUTCOMES = frozenset(
    {
        Outcome.BUDGET_EXHAUSTED.value,
        Outcome.BLOCKED.value,
        Outcome.TOOL_ERROR.value,
        Outcome.HARNESS_ERROR.value,
    }
)


def _reconcile_offline(recorded: str | None, checker_outcome: str) -> tuple[str, str]:
    """Combine the recorded run-telemetry outcome with a fresh checker verdict,
    mirroring runner._classify's precedence. Returns (outcome, why)."""
    if recorded in _RUN_TELEMETRY_OUTCOMES and checker_outcome != Outcome.PASS.value:
        return (
            recorded,
            f"kept recorded {recorded} (run telemetry; checker re-grade: {checker_outcome})",
        )
    return checker_outcome, "checker re-grade"


def rescore_debug_dir(debug_dir: Path, campaign_dir: Path | None = None) -> list[dict]:
    """Re-grade every recorded task-run with no model calls.

    The checkers in this harness returned unearned PASSes once already. When a
    checker changes, this re-derives every verdict in the campaign in seconds
    instead of re-running the fleet for another 30-60 hours. A recorded outcome
    that came from run telemetry rather than a checker (a stall, an exhausted
    turn budget, a blocked-offline task) is preserved unless the re-grade
    upgrades it to PASS."""
    suites: dict[str, dict] = {}
    updated: list[dict] = []
    for f in sorted(Path(debug_dir).glob("*.debug.jsonl")):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            sp = rec.get("suite_path")
            if sp and sp not in suites:
                suites[sp] = {t["id"]: t for t in load_suite(sp)}
            task = (suites.get(sp) or {}).get(rec.get("task_id"))
            if task is None:
                rec["rescore"] = {"outcome": None, "note": "task not found in suite"}
                updated.append(rec)
                continue
            root = rehydrate_tree(rec.get("sandbox_tree") or {})
            try:
                cr = apply_checkers(
                    task,
                    CheckContext(
                        final_text=rec.get("final_text", ""),
                        assistant_texts=rec.get("assistant_texts") or [],
                        tool_calls=rec.get("tool_call_log") or [],
                        sandbox_root=root,
                        task=task,
                        finish_reason=rec.get("finish_reason"),
                    ),
                )
            finally:
                shutil.rmtree(root, ignore_errors=True)
            final_outcome, why = _reconcile_offline(rec.get("outcome"), cr.outcome.value)
            rec["rescore"] = {
                "outcome": final_outcome,
                "checker_outcome": cr.outcome.value,
                "notes": f"{cr.notes} [{why}]",
                "evidence": cr.evidence,
                "was": rec.get("outcome"),
                "changed": final_outcome != rec.get("outcome"),
            }
            updated.append(rec)
            if campaign_dir and rec.get("run_id"):
                p = _row_path(campaign_dir, rec["run_id"])
                if p.exists():
                    row = json.loads(p.read_text())
                    row["outcome"] = final_outcome
                    row["notes"] = f"{cr.notes} [{why}]"
                    row["evidence"] = cr.evidence
                    row["rescored_utc"] = dt.datetime.now(dt.UTC).isoformat()
                    p.write_text(json.dumps(row, indent=1))
    if campaign_dir and (campaign_dir / "manifest.json").exists():
        m = load_manifest(campaign_dir)
        by_id = {r["run_id"]: r for r in m["rows"]}
        for rec in updated:
            r = by_id.get(rec.get("run_id"))
            if r and rec.get("rescore", {}).get("outcome"):
                r["state"] = rec["rescore"]["outcome"]
        m.setdefault("rescores", []).append(
            {
                "utc": dt.datetime.now(dt.UTC).isoformat(),
                "debug_dir": str(debug_dir),
                "runs": len(updated),
                "changed": sum(1 for r in updated if r.get("rescore", {}).get("changed")),
            }
        )
        save_manifest(campaign_dir, m)
    return updated


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------


def preflight_arm(campaign_dir: Path, arm: str, force: bool = False) -> dict:
    """Probe an arm's transport before spending an arm's worth of wall clock.

    Only an OK verdict is cached. A REVIEW is written to `<sha>.review.json` for
    the record but never short-circuits a later attempt: in an unattended sweep a
    single flaky probe — Ollama mid-eviction, a transient connection reset — would
    otherwise block that arm's rows permanently across every resume."""
    cache = campaign_dir / "preflight" / (sha12(arm) + ".json")
    if cache.exists() and not force:
        return json.loads(cache.read_text())
    _log(campaign_dir, f"preflight {arm}")
    try:
        res = preflight_harness(arm)
    except Exception as e:
        res = {"model": arm, "verdict": "REVIEW", "findings": [f"preflight raised: {e}"]}
    target = cache if res.get("verdict") == "OK" else cache.with_suffix(".review.json")
    target.write_text(json.dumps(res, indent=1))
    return res


def _sampling_for(wsc: dict, repeat: int) -> dict:
    """The workspace's OWN sampling block, with a distinct seed per repeat.

    Dimension 8: a temperature-0 pass is not evidence about a product served at
    the lane's declared temperature, and repeats must be three real draws rather
    than three copies of one. All 81 workspaces in portal.yaml declare a
    sampling block; the campaign serves each arm at its workspace's settings.

    The default output cap is 4096, not 2048: a reasoning-heavy 30B model doing
    multi-step tool work exhausts 2048 tokens inside its <think> block and never
    reaches an answer. A workspace with its own predict_limit still wins."""
    s = {"max_tokens": 4096, **(wsc.get("sampling") or {})}
    s["seed"] = 1000 + repeat
    return s


def degenerate_repeats(wsc: dict) -> str | None:
    """A workspace pinned to temperature 0 (or to a fixed seed) produces
    identical repeats. Recorded so the report never presents n=3 as three
    independent draws when it was one draw counted three times."""
    if wsc.get("pinned_seed") is not None:
        return f"workspace pins seed={wsc['pinned_seed']}"
    t = wsc.get("declared_temperature")
    if t is not None and float(t) == 0.0:
        return "workspace declares temperature 0 — repeats are deterministic"
    return None


def run_row(
    campaign_dir: Path,
    manifest: dict,
    r: dict,
    wsc: dict,
    task: dict,
    max_turns: int,
    budget_s: int,
    debug_dir: Path | None,
    cold: bool,
) -> dict:
    sandbox = make_sandbox(
        Path("/tmp/wfe") / manifest["campaign_id"] / sha12(r["run_id"]), r["task_id"], r["repeat"]
    )
    sampling = _sampling_for(wsc, r["repeat"])
    harness = campaign_harness(wsc)
    t0 = time.monotonic()
    try:
        out = run_task(
            r["arm"],
            wsc["system_prompt"],
            task,
            sandbox,
            max_turns,
            budget_s,
            use_tools=True,
            harness=dict(harness),
            sampling=sampling,
            tool_surface=wsc.get("tool_surface"),
        )
    except Exception as e:
        _log(campaign_dir, f"  runner raised: {type(e).__name__}: {e}")
        out = {
            "outcome": Outcome.HARNESS_ERROR.value,
            "notes": f"runner raised: {type(e).__name__}: {e}",
            "evidence": {},
            "turns": 0,
            "tool_calls": 0,
            "tool_errors": 0,
            "finish_reason": None,
            "economics": {},
            "final_text": "",
            "final_text_head": "",
            "transcript": [],
            "tool_call_log": [],
        }
    econ = dict(out.get("economics") or {})
    econ["cold_load"] = cold
    row = ResultRow(
        run_id=r["run_id"],
        campaign_id=manifest["campaign_id"],
        stage="full",
        workspace=r["workspace"],
        arm=r["arm"],
        arm_role=r["arm_role"],
        suite=r["suite"],
        task_id=r["task_id"],
        repeat=r["repeat"],
        outcome=out["outcome"],
        notes=out["notes"],
        evidence=out["evidence"],
        persona_slug=wsc.get("persona_slug"),
        prompt_sha=sha12(wsc["system_prompt"]),
        tool_surface=wsc.get("tool_surface") or TOOL_NAMES,
        tool_surface_proxy=bool(wsc.get("tool_surface_proxy", True)),
        harness=dict(harness),
        sampling=sampling,
        seed=sampling.get("seed"),
        turns=out["turns"],
        tool_calls=out["tool_calls"],
        tool_errors=out["tool_errors"],
        finish_reason=out["finish_reason"],
        economics=econ,
        env=manifest["env"],
        final_text_head=out["final_text_head"],
        transcript=out["transcript"],
        tool_call_log=out["tool_call_log"],
    ).to_dict()
    row["final_text"] = out.get("final_text", "")
    row["repeat_degeneracy"] = degenerate_repeats(wsc)
    _row_path(campaign_dir, r["run_id"]).write_text(json.dumps(row, indent=1))

    if debug_dir:
        write_debug(
            debug_dir,
            r["arm"],
            {
                "run_id": r["run_id"],
                "campaign_id": manifest["campaign_id"],
                "utc": dt.datetime.now(dt.UTC).isoformat(),
                "arm": r["arm"],
                "workspace": r["workspace"],
                "suite": r["suite"],
                "suite_path": r["suite_path"],
                "task_id": r["task_id"],
                "repeat": r["repeat"],
                "system_prompt": wsc["system_prompt"],
                "persona_slug": wsc.get("persona_slug"),
                "instruction": task["instruction"],
                "harness": dict(harness),
                "sampling": sampling,
                "tool_surface": wsc.get("tool_surface"),
                "outcome": out["outcome"],
                "notes": out["notes"],
                "evidence": out["evidence"],
                "final_text": out.get("final_text", ""),
                "transcript": out["transcript"],
                "tool_call_log": out["tool_call_log"],
                "sandbox_tree": capture_tree(sandbox.root),
                "finish_reason": out["finish_reason"],
                "economics": econ,
                "wall_s": round(time.monotonic() - t0, 1),
                "env": manifest["env"],
            },
        )
    return row


def _rows_to_run(
    campaign_dir: Path,
    manifest: dict,
    arm: str,
    retry_states: set,
    force_preflight: bool,
    notify: bool,
) -> tuple[list[dict], dict | None]:
    """The arm's runnable rows, or (…, early-return dict) if preflight blocks it.

    Rows a PREVIOUS run blocked on preflight are re-offered here rather than left
    dead: a flaky probe must not cost an arm its whole row budget for the rest of
    a multi-day sweep."""
    arm_rows = [r for r in manifest["rows"] if r["arm"] == arm]
    todo = [r for r in arm_rows if r.get("state") == "PENDING" or r.get("state") in retry_states]
    offered = {r["run_id"] for r in todo}
    stale_block = [
        r
        for r in arm_rows
        if r["run_id"] not in offered
        and r.get("state") == Outcome.BLOCKED.value
        and str(r.get("note") or "").startswith(_PREFLIGHT_BLOCK)
    ]
    if not todo and not stale_block:
        _log(campaign_dir, f"arm {arm}: nothing pending")
        return [], {"arm": arm, "ran": 0}

    pf = preflight_arm(campaign_dir, arm, force_preflight)
    findings = "; ".join(pf.get("findings") or [])
    if pf.get("verdict") != "OK" and not force_preflight:
        for r in todo:
            r["state"] = Outcome.BLOCKED.value
            r["note"] = _PREFLIGHT_BLOCK + findings
        save_manifest(campaign_dir, manifest)
        _log(campaign_dir, f"arm {arm}: BLOCKED — {findings}")
        if notify:
            _notify("test_summary", f"WFE arm BLOCKED: {arm}\n{findings}")
        return [], {"arm": arm, "ran": 0, "blocked": len(todo) + len(stale_block)}

    if stale_block:
        for r in stale_block:
            r["state"] = "PENDING"
            r.pop("note", None)
        todo.extend(stale_block)
        save_manifest(campaign_dir, manifest)
        _log(campaign_dir, f"arm {arm}: preflight now OK — un-blocked {len(stale_block)} row(s)")
    return todo, None


def execute_arm(
    campaign_dir: Path,
    arm: str,
    max_turns: int,
    budget_s: int,
    debug_dir: Path | None,
    force_preflight: bool,
    notify: bool,
    rerun_failed: bool = False,
) -> dict:
    """Run every pending row for ONE arm. Fresh process per arm is the house
    pattern for long sweeps: a leaked handle or a wedged connection in one model
    must not poison the remaining arms."""
    manifest = load_manifest(campaign_dir)
    retry_states = (
        {Outcome.HARNESS_ERROR.value, Outcome.TOOL_ERROR.value, Outcome.BLOCKED.value}
        if rerun_failed
        else set()
    )
    todo, early = _rows_to_run(campaign_dir, manifest, arm, retry_states, force_preflight, notify)
    if early is not None:
        return early

    # Evict on model change, before the first row rather than after the last: the
    # previous arm's process may have been killed without cleaning up, and the
    # pipeline may have pinned a classifier since. Both are memory this arm needs.
    evicted = drain_others(arm)
    if evicted:
        _log(campaign_dir, f"arm {arm}: drained {len(evicted)} resident model(s): {evicted}")

    _log(campaign_dir, f"arm {arm}: {len(todo)} runs pending")
    if notify:
        _notify("test_start", f"WFE arm started: {arm}\n{len(todo)} task-runs")

    ws_cache: dict[str, dict] = {}
    suite_cache: dict[str, dict] = {}
    tally: dict = {}
    t_arm = time.monotonic()
    for i, r in enumerate(todo, 1):
        if r["workspace"] not in ws_cache:
            ws_cache[r["workspace"]] = workspace_context(r["workspace"])
        if r["suite_path"] not in suite_cache:
            suite_cache[r["suite_path"]] = {t["id"]: t for t in load_suite(r["suite_path"])}
        task = suite_cache[r["suite_path"]].get(r["task_id"])
        if task is None:
            r["state"] = Outcome.HARNESS_ERROR.value
            r["note"] = "task id not present in suite"
            save_manifest(campaign_dir, manifest)
            continue
        _log(campaign_dir, f"  [{i}/{len(todo)}] {r['run_id']}")
        row = run_row(
            campaign_dir,
            manifest,
            r,
            ws_cache[r["workspace"]],
            task,
            max_turns,
            budget_s,
            debug_dir,
            cold=(i == 1),
        )
        r["state"] = row["outcome"]
        tally[row["outcome"]] = tally.get(row["outcome"], 0) + 1
        save_manifest(campaign_dir, manifest)
        _log(
            campaign_dir,
            f"      -> {row['outcome']} turns={row['turns']} tools={row['tool_calls']} "
            f"errs={row['tool_errors']} {row['economics'].get('wall_s')}s",
        )

    if not drain_model(arm):
        _log(campaign_dir, f"arm {arm}: WARNING — still resident after {DRAIN_TIMEOUT_S}s")
    elapsed = round(time.monotonic() - t_arm)
    summary = f"{arm}: {tally} in {elapsed}s"
    _log(campaign_dir, f"arm complete — {summary}")
    if notify:
        _notify("test_summary", f"WFE arm done ({elapsed}s)\n{arm}\n{tally}", {"arm": arm})
    return {"arm": arm, "ran": len(todo), "tally": tally, "elapsed_s": elapsed}


def build_review_queue(campaign_dir: Path) -> int:
    """Blinded queue for the creative lane: arm identity replaced by a hash so
    the operator scores text, not tags. report.py joins it back."""
    rows = []
    for f in sorted((campaign_dir / "rows").glob("*.json")):
        with contextlib.suppress(Exception):
            d = json.loads(f.read_text())
            if d.get("outcome") == Outcome.PENDING_REVIEW.value:
                rows.append(d)
    scored = {}
    q = campaign_dir / "review_queue.jsonl"
    if q.exists():
        for line in q.read_text().splitlines():
            with contextlib.suppress(Exception):
                d = json.loads(line)
                if d.get("score") is not None:
                    scored[d["blind_id"]] = d
    with q.open("w") as fh:
        for r in sorted(rows, key=lambda x: sha12(x["run_id"])):
            bid = sha12(r["run_id"])
            prev = scored.get(bid, {})
            fh.write(
                json.dumps(
                    {
                        "blind_id": bid,
                        "task_id": r["task_id"],
                        "suite": r["suite"],
                        "rubric": (r.get("evidence") or {}).get("rubric", []),
                        "response": r.get("final_text") or r.get("final_text_head"),
                        "score": prev.get("score"),
                        "reviewer_notes": prev.get("reviewer_notes", ""),
                    }
                )
                + "\n"
            )
    return len(rows)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(REPO / "tests/wfe/workloads.yaml"))
    ap.add_argument("--campaign-id", help="create or continue this campaign")
    ap.add_argument("--arm", help="run exactly one model tag (one arm per process)")
    ap.add_argument("--workspace", help="restrict to one workspace")
    ap.add_argument("--suite", help="restrict to one suite")
    ap.add_argument("--task", help="restrict to one task id")
    ap.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    ap.add_argument(
        "--all-suites",
        action="store_true",
        help="every suite, not just home + discovery — the variety of work a model may face",
    )
    ap.add_argument("--append", action="store_true", help="add rows to a live campaign")
    ap.add_argument(
        "--rerun-failed", action="store_true", help="also redo HARNESS_ERROR/TOOL_ERROR rows"
    )
    ap.add_argument("--max-turns", type=int, default=16)
    ap.add_argument("--budget-s", type=int, default=1800, help="per task-run wall budget")
    ap.add_argument("--debug-dir", type=Path, help="write a full per-run .debug.jsonl per arm")
    ap.add_argument("--rescore", type=Path, help="re-grade a debug dir; no model calls")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="one task end to end, full record printed")
    ap.add_argument("--list-arms", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--watch", action="store_true", help="live view of a running campaign")
    ap.add_argument(
        "--health",
        action="store_true",
        help="one deterministic verdict for an unattended supervisor; "
        "exit 0=OK 1=DONE 2=STALLED 3=DEGRADED",
    )
    ap.add_argument("--stale-after-s", type=int, default=STALL_AFTER_S)
    ap.add_argument("--watch-interval", type=int, default=10)
    ap.add_argument(
        "--preflight",
        action="store_true",
        help="probe every arm and stop; exit 1 if any needs review",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="run an arm whose preflight says REVIEW")
    return ap, ap.parse_args(argv)


def _cmd_status(campaign_dir: Path) -> int:
    import collections

    m = load_manifest(campaign_dir)
    states = collections.Counter(r.get("state") for r in m["rows"])
    print(f"campaign {m['campaign_id']}  env {m['env'].get('fingerprint')}")
    print(f"  rows {len(m['rows'])}  states {dict(states)}")
    per = collections.defaultdict(collections.Counter)
    for r in m["rows"]:
        per[r["arm"]][r.get("state")] += 1
    for arm in sorted(per):
        done = sum(v for k, v in per[arm].items() if k != "PENDING")
        print(f"  {done:>4}/{sum(per[arm].values()):<4} {arm}  {dict(per[arm])}")
    return 0


def _row_walls(campaign_dir: Path, cache: dict) -> dict:
    """wall_s per completed run, read incrementally.

    A finished 513-row sweep is 513 files; re-reading all of them every refresh
    to print one ETA would be the monitor competing with the thing it monitors."""
    for f in (campaign_dir / "rows").glob("*.json"):
        if f.name in cache:
            continue
        with contextlib.suppress(Exception):
            cache[f.name] = float(json.loads(f.read_text())["economics"]["wall_s"])
    return cache


def _hms(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600}h{(s % 3600) // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def _watch_frame(campaign_dir: Path, walls: dict, started: float) -> str:
    import collections

    m = load_manifest(campaign_dir)
    rows = m["rows"]
    states = collections.Counter(r.get("state") for r in rows)
    pending = states.get("PENDING", 0)
    done = len(rows) - pending
    walls = _row_walls(campaign_dir, walls)
    mean = (sum(walls.values()) / len(walls)) if walls else 0.0

    out = [
        f"campaign {m['campaign_id']}   env {m['env'].get('fingerprint')}",
        f"watching {_hms(time.monotonic() - started)}   {dt.datetime.now().strftime('%H:%M:%S')}",
        "",
        f"  {done}/{len(rows)} rows   " + "  ".join(f"{k}={v}" for k, v in sorted(states.items())),
    ]
    if mean and pending:
        # Arms run one at a time, so remaining wall clock is simply the rows left
        # times what a row has actually cost so far. No model is run in parallel.
        out.append(f"  mean row {mean:.0f}s   ~{_hms(pending * mean)} left at this rate")
    out.append("")

    per: dict = collections.defaultdict(collections.Counter)
    for r in rows:
        per[r["arm"]][r.get("state")] += 1
    for arm in sorted(per, key=lambda a: (per[a].get("PENDING", 0) == sum(per[a].values()), a)):
        c = per[arm]
        tot = sum(c.values())
        d = tot - c.get("PENDING", 0)
        bar = "█" * int(20 * d / tot) + "·" * (20 - int(20 * d / tot))
        mark = "▶" if 0 < d < tot else " "
        detail = "  ".join(f"{k}={v}" for k, v in sorted(c.items()) if k != "PENDING")
        out.append(f" {mark} {bar} {d:>3}/{tot:<3} {arm[:52]:52s} {detail}")

    log = campaign_dir / "progress.log"
    if log.exists():
        out += ["", "recent:"]
        with contextlib.suppress(Exception):
            out += ["  " + ln for ln in log.read_text().splitlines()[-8:]]
    return "\n".join(out)


#: A row may legitimately run to the full --budget-s (1800s). Anything past twice
#: that with no completed row is not a slow model, it is a stuck sweep.
STALL_AFTER_S = 3600


def health(campaign_dir: Path, stale_after_s: int = STALL_AFTER_S) -> dict:
    """One deterministic verdict on a sweep in flight.

    Built for an unattended supervisor checking in on a schedule: the answer has
    to be the same whoever asks, and cheap enough to ask every hour for two days.
    Progress is judged against the previous call, recorded in the campaign dir,
    because "no row finished in the last hour" is the only honest stall signal
    when a single row is allowed thirty minutes."""
    import collections

    m = load_manifest(campaign_dir)
    rows = m["rows"]
    states = collections.Counter(r.get("state") for r in rows)
    pending = states.get("PENDING", 0)
    done = len(rows) - pending
    now = time.time()

    state_f = campaign_dir / "health_state.json"
    prev = {}
    with contextlib.suppress(Exception):
        prev = json.loads(state_f.read_text())
    since = now - float(prev.get("ts", now))
    advanced = done - int(prev.get("done", done))
    with contextlib.suppress(Exception):
        state_f.write_text(json.dumps({"ts": now, "done": done}))

    instrument = sum(states.get(o.value, 0) for o in INSTRUMENT_OUTCOMES)
    checks, problems = {}, []

    checks["ollama"] = "up" if ollama_reachable() else "UNREACHABLE"
    if checks["ollama"] != "up":
        problems.append("Ollama is not answering — the sweep cannot make progress")

    with contextlib.suppress(Exception):
        # Parse the DATA line's Available column by position within that line.
        # Splitting the whole of stdout instead lands on `1G-blocks` (total size),
        # which is always large — a disk check that could never fire.
        df = subprocess.run(
            ["df", "-g", str(REPO)], capture_output=True, text=True, timeout=20
        ).stdout.splitlines()
        free_gb = int(df[1].split()[3])
        checks["disk_free_gb"] = free_gb
        if free_gb < 10:
            problems.append(f"only {free_gb}GB disk free — the debug capture will fail")

    # An instrument failure is the harness breaking, not a model being bad. A
    # rising count means the run is producing unusable rows and is worth stopping.
    checks["instrument_failures"] = instrument
    if done and instrument / done > 0.25:
        problems.append(
            f"{instrument}/{done} rows are instrument failures — the harness is at fault, not the models"
        )

    if pending == 0:
        verdict, code = "DONE", 1
    elif problems:
        verdict, code = "DEGRADED", 3
    elif prev and since >= stale_after_s and advanced == 0:
        verdict, code = "STALLED", 2
        problems.append(
            f"no row completed in {_hms(since)} (a row's own ceiling is {STALL_AFTER_S // 2}s)"
        )
    else:
        verdict, code = "OK", 0

    return {
        "verdict": verdict,
        "exit_code": code,
        "campaign": m["campaign_id"],
        "done": done,
        "total": len(rows),
        "pending": pending,
        "advanced_since_last_check": advanced if prev else None,
        "since_last_check": round(since) if prev else None,
        "states": dict(states),
        "checks": checks,
        "problems": problems,
    }


def _cmd_health(campaign_dir: Path, stale_after_s: int) -> int:
    """Terse by design: an hourly supervisor should read four lines, not a page."""
    h = health(campaign_dir, stale_after_s)
    print(f"{h['verdict']}  {h['campaign']}  {h['done']}/{h['total']} rows  pending={h['pending']}")
    print("  states  " + "  ".join(f"{k}={v}" for k, v in sorted(h["states"].items())))
    print("  checks  " + "  ".join(f"{k}={v}" for k, v in h["checks"].items()))
    if h["advanced_since_last_check"] is not None:
        print(
            f"  since last check  +{h['advanced_since_last_check']} rows in {_hms(h['since_last_check'])}"
        )
    for p in h["problems"]:
        print(f"  ! {p}")
    return h["exit_code"]


def _cmd_watch(campaign_dir: Path, interval: int) -> int:
    """Live view of a sweep in flight. Read-only — it touches nothing the
    campaign writes, so it is safe to start, stop and restart at any time."""
    walls: dict = {}
    started = time.monotonic()
    try:
        while True:
            with contextlib.suppress(Exception):
                print("\033[2J\033[H" + _watch_frame(campaign_dir, walls, started), flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n(watch stopped — the campaign is unaffected)")
    return 0


def _cmd_smoke(args, plan: Path) -> int:
    matrix = expand_matrix(plan, 1, args.all_suites, args.arm, args.suite, args.task)
    if not matrix:
        print("smoke: no matching row", file=sys.stderr)
        return 2
    r = matrix[0]
    d = CAMPAIGNS / (args.campaign_id or "wfe_smoke")
    (d / "rows").mkdir(parents=True, exist_ok=True)
    (d / "preflight").mkdir(parents=True, exist_ok=True)
    manifest = {"campaign_id": d.name, "env": env_fingerprint(OLLAMA), "rows": [r]}
    save_manifest(d, manifest)
    pf = preflight_arm(d, r["arm"], force=True)
    print(json.dumps(pf, indent=1))
    if pf.get("verdict") != "OK" and not args.force:
        print("\nsmoke: preflight REVIEW — fix or pass --force", file=sys.stderr)
        return 1
    wsc = workspace_context(r["workspace"])
    task = {t["id"]: t for t in load_suite(r["suite_path"])}[r["task_id"]]
    debug = args.debug_dir or (d / "debug")
    row = run_row(d, manifest, r, wsc, task, args.max_turns, args.budget_s, debug, cold=True)
    print("\n=== SMOKE RESULT ===")
    print(json.dumps({k: v for k, v in row.items() if k != "transcript"}, indent=1)[:4000])
    print(f"\ndebug record: {debug}")
    print(f"outcome: {row['outcome']}  ({row['notes'][:200]})")
    return 0 if row["outcome"] in (Outcome.PASS.value, Outcome.FAIL.value) else 1


def _cmd_dry_run(matrix: list[dict], repeats: int) -> int:
    import collections

    c = collections.Counter(r["arm"] for r in matrix)
    print(f"matrix rows: {len(matrix)}   arms: {len(c)}   repeats: {repeats}")
    for a, n in sorted(c.items()):
        print(f"  {n:>4}  {a}")
    return 0


def _cmd_list_arms(plan: Path, all_suites: bool) -> int:
    import collections

    c = collections.Counter(r["arm"] for r in expand_matrix(plan, 1, all_suites))
    for a, n in sorted(c.items()):
        print(f"{n:>4}  {a}")
    return 0


def _cmd_preflight(campaign_dir: Path, force: bool) -> int:
    """Probe every arm's transport before the sweep starts.

    An arm the harness cannot talk to yields no rows at all — and in an
    unattended sweep that is discovered at hour forty, not hour zero. Twenty
    minutes up front clears the whole roster, and every OK verdict is cached, so
    the sweep does not pay for the probe twice. Exit 1 if any arm needs review."""
    drain_others("")
    sizes = model_sizes()
    arms = sorted(
        {r["arm"] for r in load_manifest(campaign_dir)["rows"]},
        key=lambda a: (sizes.get(a, 0), a),
    )
    missing = [a for a in arms if a not in sizes] if sizes else []
    bad = []
    for i, a in enumerate(arms, 1):
        t0 = time.monotonic()
        res = preflight_arm(campaign_dir, a, force)
        verdict = str(res.get("verdict"))
        print(f"[{i}/{len(arms)}] {verdict:6s} {round(time.monotonic() - t0, 1):7.1f}s  {a}")
        for f in res.get("findings") or []:
            print(f"          FINDING: {f}")
        for n in res.get("notes") or []:
            print(f"          note: {n}")
        if verdict != "OK":
            bad.append(a)
        drain_model(a)
        sys.stdout.flush()
    print(f"\npreflight: {len(arms) - len(bad)}/{len(arms)} OK")
    if missing:
        print("NOT INSTALLED: " + ", ".join(missing))
    if bad:
        print("REVIEW (these arms will be BLOCKED): " + ", ".join(bad))
    return 1 if (bad or missing) else 0


def _cmd_rescore(args) -> int:
    cd = CAMPAIGNS / args.campaign_id if args.campaign_id else None
    recs = rescore_debug_dir(args.rescore, cd)
    changed = [r for r in recs if r.get("rescore", {}).get("changed")]
    print(f"re-scored {len(recs)} runs from {args.rescore}; {len(changed)} verdicts changed")
    for r in changed[:40]:
        print(f"  {r['rescore']['was']} -> {r['rescore']['outcome']}  {r['run_id']}")
    return 0


def _inspect_command(args, campaign_dir: Path) -> int | None:
    """The read-only views of a campaign. Separated from main() so a sweep in
    flight can be inspected without any code path that could write to it."""
    if args.status:
        return _cmd_status(campaign_dir)
    if args.watch:
        return _cmd_watch(campaign_dir, args.watch_interval)
    if args.health:
        return _cmd_health(campaign_dir, args.stale_after_s)
    return None


def main() -> int:
    ap, args = _parse_args()
    plan = Path(args.plan)

    if args.list_arms:
        return _cmd_list_arms(plan, args.all_suites)
    if args.rescore:
        return _cmd_rescore(args)
    if args.smoke:
        return _cmd_smoke(args, plan)

    if not args.campaign_id:
        ap.error("--campaign-id is required (or use --smoke / --rescore / --list-arms)")
    matrix = expand_matrix(plan, args.repeats, args.all_suites, args.arm, args.suite, args.task)
    if args.dry_run:
        return _cmd_dry_run(matrix, args.repeats)

    campaign_dir = open_campaign(args.campaign_id, plan, matrix, args.append)
    rc = _inspect_command(args, campaign_dir)
    if rc is not None:
        return rc
    if args.preflight:
        if not ollama_reachable():
            _log(campaign_dir, "ABORT: Ollama unreachable")
            return 3
        return _cmd_preflight(campaign_dir, args.force)
    if not ollama_reachable():
        _log(campaign_dir, "ABORT: Ollama unreachable")
        return 3
    manifest = load_manifest(campaign_dir)
    arms = [args.arm] if args.arm else sorted({r["arm"] for r in manifest["rows"]})
    for arm in arms:
        if not ollama_reachable():
            _log(campaign_dir, f"ABORT before {arm}: Ollama unreachable")
            return 3
        execute_arm(
            campaign_dir,
            arm,
            args.max_turns,
            args.budget_s,
            args.debug_dir,
            args.force,
            args.notify,
            args.rerun_failed,
        )
    n = build_review_queue(campaign_dir)
    dirty = config_dirty()
    manifest = load_manifest(campaign_dir)
    manifest["config_dirty_at_end"] = dirty
    save_manifest(campaign_dir, manifest)
    if dirty != (manifest.get("config_dirty_at_start") or []):
        _log(campaign_dir, f"WARNING: config/ changed during the campaign: {dirty}")
    print(f"\ncampaign dir: {campaign_dir}   creative queue: {n} item(s)")
    print(f"next: uv run python -m tests.wfe.report --campaign {campaign_dir.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
