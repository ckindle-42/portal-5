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
                           checks Ollama between arms, appends to a progress log.
                           Exits 10 when every row is BLOCKED, PENDING, or MISSING.
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
import functools
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import yaml

from portal.platform.inference import identity as _omlx_identity
from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.config import effective_workspace
from tests.wfe import decision, eval_mode
from tests.wfe.checkers import CheckContext, CheckResult, apply_checkers, expect_tools_verdict
from tests.wfe.runner import (
    CHAT_BASE,
    ENGINE,
    OLLAMA,
    TOOL_NAMES,
    _combined_turn_result,
    card_sampling,
    chat,
    load_suite,
    make_sandbox,
    preflight_harness,
    required_tools,
    run_task,
    undeliverable_keys,
    workspace_context,
)
from tests.wfe.schema import (
    INSTRUMENT_OUTCOMES,
    MANIFEST_SCHEMA_VERSION,
    MODEL_QUALITY_OUTCOMES,
    Outcome,
    ResultRow,
    env_fingerprint,
    sha12,
)
from tests.wfe.upload_fidelity import row_instrument

REPO = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data")))
CAMPAIGNS = DATA_ROOT / "tests" / "wfe" / "results" / "campaigns"
SUITE_DIR = REPO / "tests" / "wfe" / "suites"
DEFAULT_REPEATS = 3
#: Production fidelity base: the pipeline serves /v1 non-streaming, no forced
#: response format. `think` is filled in per workspace by campaign_harness().
CAMPAIGN_HARNESS = {"endpoint": "v1", "stream": False, "think": "default", "format": "none"}


def campaign_harness(wsc: dict, overrides: dict | None = None) -> dict:
    """The harness dimensions for one workspace's runs. `think` is resolved the
    way production resolves it: the workspace's explicit `think` bool, else
    nothing at all (the model's native default). A test of model X in workspace Y must run X the way Y is
    configured, including a misconfiguration — that is the signal Y needs
    fixing, or that X is not a fit."""
    h = dict(CAMPAIGN_HARNESS)
    ws_think = None if ENGINE == "pipeline" else wsc.get("think")  # pipeline applies it
    # A `think` override is an explicit experiment arm (e.g. "how does this seat
    # score with reasoning off?"). It lives on the ROW (see arm_spec), and is
    # stamped in every row's harness record, so an override row can't pass for a
    # production-resolved one.
    forced = (overrides or {}).get("think")
    if forced in ("true", "false"):
        h["think"] = forced
    elif ws_think is not None:
        h["think"] = "true" if ws_think else "false"
    else:
        # Production sends NO think field when the workspace sets none
        # (router/validation.py reads only the workspace's `think`; nothing in
        # portal/ reads the card's harness_policy), so the model runs at its
        # native default. "native" sends nothing too. Resolving the card policy
        # here ran auto-coding::laguna / ::uncensored-fast / ::reap288 with
        # thinking OFF while production runs them with it ON (2026-09-25).
        h["think"] = "native"
    backend = (overrides or {}).get("backend")
    if backend:  # engine is stamped per row by the pipeline's own trace either way
        h["pipeline_backend"] = backend
    return h


#: Cap on any single captured file in a debug record. Large enough for real
#: source files, small enough that a debug jsonl stays reviewable.
DEBUG_FILE_CAP = 100_000
DEBUG_TREE_CAP = 60

#: Prefix on a row note that marks the block as "preflight said REVIEW", which is
#: retryable, as opposed to a task-level block (offline `requires_network`), which
#: is not. execute_arm re-offers only rows carrying this prefix.
_PREFLIGHT_BLOCK = "preflight REVIEW: "
#: Note prefix of a pipeline row the seat did not serve (run_row).
SEAT_BLOCK = "not seat evidence: "


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
    """The chat engine answers. For a non-Ollama engine (WFE_ENGINE) that is its
    /v1/models; Ollama is still the model manager there, but the rows go to the
    other engine, so that is the one whose absence stops the sweep."""
    import urllib.request

    url = {"ollama": f"{OLLAMA}/api/version", "pipeline": f"{CHAT_BASE}/health"}.get(
        ENGINE, f"{CHAT_BASE}/v1/models"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return bool(json.load(r))
    except Exception:
        return False


#: Ceiling on waiting for a model to leave memory. Reached only if Ollama never
#: reports the release; the normal path returns as soon as /api/ps is clean.
DRAIN_TIMEOUT_S = max(1, int(os.environ.get("WFE_DRAIN_TIMEOUT_S", "180")))
_DRAIN_POLL_S = max(0.01, float(os.environ.get("WFE_DRAIN_POLL_S", "2")))


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


def production_seat_tags() -> set[str]:
    """Every model tag seated by a base workspace or variant."""
    spaces = (yaml.safe_load((REPO / "config/portal.yaml").read_text()) or {}).get(
        "workspaces"
    ) or {}
    tags = set()
    for base_id, base in spaces.items():
        workspace_ids = [base_id, *(f"{base_id}::{name}" for name in (base.get("variants") or {}))]
        for workspace_id in workspace_ids:
            hint = effective_workspace(spaces, workspace_id).get("model_hint")
            if hint:
                tags.add(str(hint))
    return tags


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
    protected = production_seat_tags() if ENGINE == "pipeline" else set()
    for tag in loaded_models():
        if tag == keep or tag in protected:
            continue
        drain_model(tag, timeout_s)
        evicted.append(tag)
    return evicted


#: oMLX itself — the chat base in omlx mode; in pipeline mode the engine behind it.
OMLX_BASE = (
    CHAT_BASE
    if ENGINE == "omlx"
    else os.environ.get("WFE_OMLX_URL", "http://127.0.0.1:8085").rstrip("/")
)


def _omlx_pool() -> dict:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OMLX_BASE}/health", timeout=5) as r:
            return json.load(r).get("engine_pool") or {}
    except Exception:
        return {}


def drain_omlx(timeout_s: int = DRAIN_TIMEOUT_S) -> str:
    """Start an oMLX arm with nothing else resident. drain_others() only reaches
    Ollama; oMLX holds its own pool (up to its memory ceiling), so an arm could
    run beside a previous arm's 27B weights and measure paging. oMLX's unload
    endpoint needs admin auth, so a service restart is the drain — the same
    remedy the house rules use for a wedged MLX server."""
    loaded = int(_omlx_pool().get("loaded_count") or 0)
    if not loaded:
        return "oMLX pool empty"
    subprocess.run(
        ["brew", "services", "restart", "jundot/omlx/omlx"],
        capture_output=True,
        timeout=120,
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        pool = _omlx_pool()
        if pool and not int(pool.get("loaded_count") or 0):
            return f"oMLX restarted to release {loaded} resident model(s)"
        time.sleep(_DRAIN_POLL_S)
    return f"WARNING — oMLX still reports resident models after {timeout_s}s"


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


def env_overrides() -> dict:
    """WFE_SAMPLING / WFE_THINK as an override dict. Read ONLY when the matrix
    is expanded: the override is then stored on every row it created, so a
    resume in a shell without (or with different) env vars can neither drop the
    override nor apply it to rows it was never meant for."""
    ov: dict = {}
    raw = os.environ.get("WFE_SAMPLING")
    if raw:
        ov["sampling"] = json.loads(raw)
    think = os.environ.get("WFE_THINK")
    if think in ("true", "false"):
        ov["think"] = think
    return ov


def arm_spec(entry) -> tuple[str, str, dict]:
    """(arm_id, model, overrides) for one plan arm.

    A plan arm is a model tag, or a variant of one:
      {model: <tag>, label: card, sampling: {...}, think: true|false, persona: <slug>}
    A variant's arm_id is `<tag>@<label>-<sha8 of its overrides>`, so the seat
    arm and the card arm of the SAME model are distinct arms with distinct
    run_ids. Before this, run_id carried no sampling: an A/B with --append
    added 0 rows ("already present") and the card arm silently never ran."""
    if isinstance(entry, dict):
        model = str(entry["model"])
        # `backend` pins the SERVING backend (plan-level arm option -> pipeline
        # `portal_backend`); without it a tag both engines declare is served by
        # whichever candidate the routing ladder reaches first.
        ov = {
            k: entry[k]
            for k in ("sampling", "think", "persona", "backend")
            if entry.get(k) is not None
        }
        label = entry.get("label")
    else:
        model, ov, label = str(entry), {}, None
    env = env_overrides()
    if env:
        ov, label = {**ov, **env}, label or "env"
    if "think" in ov:
        ov["think"] = str(ov["think"]).lower()
    if not ov:
        return model, model, {}
    digest = sha12(json.dumps(ov, sort_keys=True))[:8]
    return f"{model}@{label}-{digest}" if label else f"{model}@{digest}", model, ov


def _with_card_sampling(entry, role: str, ws_id: str):
    """A challenger with no explicit `sampling` runs at its MODEL CARD's
    sampling, not the seat's. The seat's sampling block was tuned for the
    incumbent (auto-compliance: temperature 0.3, repetition_penalty 1.1), and
    every challenger in workloads.yaml — gpt-oss (card 1.0/1.0), granite4.2,
    glm-4.7-flash, Qwen3.8-Uncensored — used to run at it, so a comparison
    measured fit to the incumbent's settings. Replacing the incumbent would
    re-tune the seat for the new model, so the card is the fair arm. The card
    mode follows the lane's think policy. `sampling: seat` keeps the seat's
    block on purpose; a model with no card sampling keeps it and says so."""
    if role != "challenger":
        return entry
    spec = dict(entry) if isinstance(entry, dict) else {"model": str(entry)}
    if spec.get("sampling") == "seat":
        spec.pop("sampling")
        return spec
    if spec.get("sampling") is not None:
        return spec
    lane_think = workspace_context(ws_id).get("think")
    card = card_sampling(spec["model"], lane_think)
    if not card:
        return spec
    spec["sampling"] = card
    spec.setdefault("label", "card")
    return spec


def _with_reasoning_budget(entry, role: str, ws_id: str):
    """Give a thinking challenger the audit's seat budget through its sampling override."""
    if role != "challenger":
        return entry
    spec = dict(entry) if isinstance(entry, dict) else {"model": str(entry)}
    model = str(spec["model"])
    try:
        wsc = workspace_context(ws_id, spec.get("persona"))
    except KeyError:
        return spec
    audit_ws = {key: wsc.get(key) for key in ("think", "context_limit", "predict_limit")}
    if spec.get("think") is not None:
        audit_ws["think"] = str(spec["think"]).lower() == "true"
    from tests.wfe import settings_audit

    target = settings_audit.reasoning_budget_target(
        audit_ws,
        model,
        settings_audit._load_expectations(),
        baked_window=settings_audit.ctx_from_tag(model),
    )
    if target is None:
        return spec
    current = spec.get("sampling")
    sampling = {} if current in (None, "seat") else dict(current)
    spec["sampling"] = {**sampling, "max_tokens": target}
    return spec


def row_model(r: dict) -> str:
    """The model tag a row runs. Rows written before variant arms carry none."""
    return r.get("model") or r["arm"]


def row_overrides(r: dict) -> dict:
    """The row's own overrides. A legacy row (no `overrides` key) keeps the old
    semantics — the env of the process running it — so an in-flight campaign
    started before variant arms resumes exactly as it would have."""
    return r["overrides"] if "overrides" in r else env_overrides()


def load_advance(path: Path | None) -> dict[str, set] | None:
    """The screen's advance list: workspace -> candidate arms to confirm.

    `report --screen-out` writes it. Incumbents are not listed and are always
    expanded, because a cell whose baseline is missing cannot be compared."""
    if path is None:
        return None
    data = yaml.safe_load(Path(path).read_text()) or {}
    return {str(ws): {str(a) for a in (arms or [])} for ws, arms in data.items()}


def expand_matrix(
    plan_path: Path,
    repeats: int | dict[str, int] = DEFAULT_REPEATS,
    all_suites: bool = False,
    only_arm: str | None = None,
    only_suite: str | None = None,
    only_task: str | None = None,
    only_workspace: str | None = None,
    tier: str = "confirm",
    advance: dict[str, set] | None = None,
) -> list[dict]:
    """Expand the plan into one row per (workspace, arm, suite, task, repeat).

    `tier` records how a row was created and never decides membership in a
    comparison; `advance` (workspace -> candidates to keep) is the screen's
    output. Rows are keyed by run_id and carry their own state, which is what
    makes the campaign resumable, appendable and honest about what did not run.
    The tier and advance rules are specified in docs/WFE_ROOT_CAUSES_20261013.md."""
    plan = yaml.safe_load(plan_path.read_text()) or {}
    every = sorted(p.stem for p in SUITE_DIR.glob("*.jsonl") if not p.stem.endswith("_full"))
    rows: list[dict] = []
    for ws_id, wl in (plan.get("workloads") or {}).items():
        # --workspace was accepted and then ignored until 2026-09-12, so a
        # scoped re-run silently widened to the whole plan — `--workspace X`
        # only landed on X when X happened to own the suite as well.
        if only_workspace and ws_id != only_workspace:
            continue
        home = wl.get("home")
        suites = every if all_suites else [home] + list(wl.get("discovery") or [])
        arms = wl.get("arms") or {}
        # An advance list is the screen's whole output: a workspace it does not
        # name advanced no candidate, so only that workspace's incumbent confirms.
        wanted = None if advance is None else advance.get(ws_id, set())
        for role, spec in _planned_arms(arms, ws_id, only_arm, wanted):
            for suite in dict.fromkeys(s for s in suites if s):
                if only_suite and suite != only_suite:
                    continue
                n = repeats.get(spec[0], DEFAULT_REPEATS) if isinstance(repeats, dict) else repeats
                home_tasks = wl.get("home_tasks") if suite == home else None
                task_ids = (
                    {str(task_id) for task_id in home_tasks} if home_tasks is not None else None
                )
                rows += _suite_rows(ws_id, spec, role, suite, home, tier, n, only_task, task_ids)
    # Arm-major: every task for a model runs while its weights are resident.
    rows.sort(key=lambda r: (r["arm"], r["workspace"], r["suite"], r["task_id"], r["repeat"]))
    return _with_tool_modes(rows, plan)


def _with_tool_modes(rows: list[dict], plan: dict) -> list[dict]:
    """Carry a workload's `tool_mode` (sandbox | production) onto its rows, checked now rather
    than mid-run: an unknown mode, or production for a workspace with no allowlist, is an error."""
    modes = {
        ws: wl.get("tool_mode")
        for ws, wl in (plan.get("workloads") or {}).items()
        if wl.get("tool_mode")
    }
    for ws, mode in modes.items():
        if mode not in ("sandbox", "production"):
            raise ValueError(f"{ws}: tool_mode must be sandbox or production, not {mode!r}")
        eval_mode.mode_for(ws, mode)
    return [
        {**r, "tool_mode": modes[r["workspace"]]} if r["workspace"] in modes else r for r in rows
    ]


def realuse_tool_surface_report(plan_path: Path) -> tuple[int, list[str]]:
    """Check every selected real-use home task against its row's offered tools."""
    rows = expand_matrix(plan_path, 1, tier="realuse")
    suites: dict[str, dict[str, dict]] = {}
    checked: set[tuple[str, str, str]] = set()
    failures = []
    for row in rows:
        if not row["is_home"]:
            continue
        key = (row["workspace"], row["suite"], row["task_id"])
        if key in checked:
            continue
        checked.add(key)
        if row["suite"] not in suites:
            suites[row["suite"]] = {
                task["id"]: task for task in load_suite(SUITE_DIR / f"{row['suite']}.jsonl")
            }
        task = suites[row["suite"]][row["task_id"]]
        mode = eval_mode.mode_for(row["workspace"], row.get("tool_mode"))
        surface = set(mode["allow"]) if mode else set(TOOL_NAMES)
        missing = sorted(required_tools(task) - surface)
        if missing:
            failures.append(
                f"workload {row['workspace']} task {row['task_id']} missing tools: {missing}"
            )
    return len(checked), failures


def prompt_tool_surface_report(plan_path: Path) -> tuple[int, list[str]]:
    """Check every production-mode workload's SERVED prompt (base + pipeline-injected append)
    against its served tool surface. A prompt that names a tool the surface lacks is the
    instrument that fed the model "unknown tool explore_repository" (ready4_mellum_20261105):
    the arm that obeys the prompt is penalized and the comparison is unfair. Sandbox-mode
    workspaces are exempt — the harness note declares their substitute surface."""
    doc = yaml.safe_load(plan_path.read_text()) or {}
    checked, failures = 0, []
    for ws, wl in sorted((doc.get("workloads") or {}).items()):
        try:
            mode = eval_mode.mode_for(ws, (wl or {}).get("tool_mode"))
        except ValueError as e:
            failures.append(f"workspace {ws}: {e}")
            continue
        if not mode:
            continue
        ctx = workspace_context(ws)
        prompt = ctx["system_prompt_base"] + ctx.get("system_prompt_append", "")
        from tests.wfe.prompt_surface import prompt_tool_mismatches

        named = prompt_tool_mismatches(
            prompt, set(mode["allow"]) | set(eval_mode.PROXY_TOOLS), eval_mode.known_tool_names()
        )
        checked += 1
        if named:
            failures.append(f"workspace {ws}: prompt names tool(s) not served: {named}")
    return checked, failures


def _planned_arms(arms: dict, ws_id: str, only_arm: str | None, want: set | None):
    """(role, spec) for every arm one workspace expands, obeying --arm and --advance."""
    ordered = [("incumbent", arms.get("incumbent"))] + [
        ("challenger", c) for c in (arms.get("challengers") or [])
    ]
    out = []
    for role, entry in ordered:
        if not entry:
            continue
        prepared = _with_reasoning_budget(_with_card_sampling(entry, role, ws_id), role, ws_id)
        arm_id, model, overrides = arm_spec(prepared)
        if only_arm and only_arm not in (arm_id, model):
            continue
        if role == "challenger" and want is not None and arm_id not in want:
            continue
        out.append((role, (arm_id, model, overrides)))
    return out


def _suite_rows(
    ws_id, spec, role, suite, home, tier, repeats, only_task, task_ids: set[str] | None = None
) -> list[dict]:
    """Every row one (workspace, arm, suite) contributes at this tier."""
    suite_path = SUITE_DIR / f"{suite}.jsonl"
    if not suite_path.exists():
        return [
            _row_stub(ws_id, spec, role, suite, suite_path, "MISSING", 0, suite == home, tier)
            | {
                "state": Outcome.HARNESS_ERROR.value,
                "note": f"suite file not found: {suite_path}",
            }
        ]
    out: list[dict] = []
    for task in load_suite(suite_path):
        if only_task and task["id"] != only_task:
            continue
        if task_ids is not None and task["id"] not in task_ids:
            continue
        # A real-use task names the workspace it was written for: running it in another
        # would grade the wrong seat's tools and prompt. A variant lane is its base.
        declared = str(task.get("workspace") or "")
        if declared and declared not in (ws_id, ws_id.split("::", 1)[0]):
            continue
        if tier == "screen" and not task.get("screen"):
            continue
        for rep in range(1 if tier == "screen" else repeats):
            out.append(
                _row_stub(
                    ws_id, spec, role, suite, suite_path, task["id"], rep, suite == home, tier
                )
            )
    return out


def _row_stub(ws_id, spec, role, suite, suite_path, task_id, rep, is_home, tier="confirm") -> dict:
    arm_id, model, overrides = spec
    return {
        "run_id": f"{ws_id}|{arm_id}|{suite}|{task_id}|r{rep}",
        "workspace": ws_id,
        "arm": arm_id,
        "model": model,
        "overrides": overrides,
        "arm_role": role,
        "tier": tier,
        "suite": suite,
        "suite_path": str(suite_path),
        "task_id": task_id,
        "repeat": rep,
        "is_home": is_home,
        "state": "PENDING",
    }


#: Config whose change alters what a row measures; edits to it split a campaign.
FINGERPRINTED_CONFIG = (
    "config/portal.yaml",
    "config/bench_workspaces.yaml",
    "config/backends.yaml",
    "config/model_card_expectations.yaml",
)


#: Instrument inputs hashed by content; results are outputs and never part of it.
INSTRUMENT_DIRS = ("tests/wfe",)
_NOT_INSTRUMENT = ("tests/wfe/results", "__pycache__", ".pytest_cache")
#: Paths whose uncommitted change means the instrument is not the committed one.
INSTRUMENT_PATHS = ("tests/wfe", "portal", "config", "Dockerfile.pipeline", "Dockerfile.mcp")


def _git(*a: str) -> str:
    try:
        return subprocess.run(
            ["git", *a], cwd=REPO, capture_output=True, text=True, timeout=20
        ).stdout
    except Exception:
        return ""


def _content_digest(paths) -> str:
    import hashlib

    h = hashlib.sha256()
    for rel in paths:
        root = REPO / rel
        files = sorted(root.rglob("*")) if root.is_dir() else [root]
        for f in files:
            r = f.relative_to(REPO).as_posix()
            if f.is_file() and not any(x in r for x in _NOT_INSTRUMENT):
                h.update(r.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def instrument_dirty() -> list[str]:
    out = _git("status", "--porcelain", "--", *INSTRUMENT_PATHS, ":(exclude)tests/wfe/results")
    return [ln[3:] for ln in out.splitlines() if ln.strip()]


def deployed_build() -> str:
    """The git commit the running pipeline image was built from (its /health build_sha)."""
    try:
        with urllib.request.urlopen(f"{CHAT_BASE}/health", timeout=5) as r:
            return str(json.loads(r.read()).get("build_sha") or "unknown")
    except Exception:
        return "unreachable"


def deployed_services() -> dict[str, dict]:
    """Each participating service's reported build, from its /health (root-fix Part 2c).
    WFE_SERVICES (comma-separated) narrows the set; a service that does not answer is an entry
    with an error, never a silent skip."""
    names = [
        n
        for n in (os.environ.get("WFE_SERVICES") or ",".join(eval_mode.SERVICE_URLS)).split(",")
        if n
    ]
    out: dict[str, dict] = {}
    for n in names:
        try:
            with urllib.request.urlopen(f"{eval_mode.SERVICE_URLS[n]}/health", timeout=5) as r:
                h = json.loads(r.read())
            out[n] = {
                "build_sha": str(h.get("build_sha") or "unknown"),
                "build_dirty": h.get("build_dirty", -1),
            }
        except Exception as e:  # noqa: BLE001
            out[n] = {"build_sha": "unreachable", "build_dirty": -1, "error": str(e)}
    return out


def service_findings(services: dict[str, dict]) -> list[str]:
    """Why a service cannot be trusted to run HEAD: unreachable, another build, or dirty."""
    bad = []
    for n, s in services.items():
        if s.get("error"):
            bad.append(f"{n} service unreachable: {s['error']}")
        elif not deployed_matches(s["build_sha"]):
            bad.append(
                f"{n} service runs build {s['build_sha']!r}, not HEAD's portal/: rebuild or restart it"
            )
        elif int(s.get("build_dirty") or 0) > 0:
            bad.append(
                f"{n} service was started from a tree with uncommitted changes under portal/"
            )
    return bad


def deployed_matches(build: str) -> bool:
    """True when the deployed image's portal/ tree and Dockerfile equal HEAD's."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", build or ""):
        return False
    return all(
        _git("rev-parse", f"{build}:{p}").strip() == _git("rev-parse", f"HEAD:{p}").strip() != ""
        for p in ("portal", "Dockerfile.pipeline")
    )


def instrument_fingerprint() -> dict:
    """What is measuring: harness and config by content, portal tree, deployed build, engine."""
    import hashlib

    parts = {
        "commit": _git("rev-parse", "HEAD").strip(),
        "harness": _content_digest(INSTRUMENT_DIRS),
        "config": _content_digest(FINGERPRINTED_CONFIG),
        "portal_tree": _git("rev-parse", "HEAD:portal").strip(),
        "deployed": deployed_build() if ENGINE == "pipeline" else "",
        "services": deployed_services() if ENGINE == "pipeline" else {},
        "engine": ENGINE,
        # Realuse pipeline turns prepend OWUI RAG context (Portal template) and carry the
        # inlet filter's portal_attached_files field. Bumps the hash.
        "upload_delivery": "owui-rag-v0.12.5+portal-filter-v1",
    }
    blob = json.dumps({k: v for k, v in parts.items() if k != "commit"}, sort_keys=True)
    parts["fingerprint"] = hashlib.sha256(blob.encode()).hexdigest()[:16]
    return parts


EXIT_GATE = 4


class GateRefused(SystemExit):
    """A gate refused to run: controls, a dirty or drifted instrument. Exits 4 with its reason."""

    def __init__(self, message: str):
        super().__init__(EXIT_GATE)
        self.message = message

    def __str__(self) -> str:
        return self.message


def instrument_drift(manifest: dict) -> str | None:
    """How a fresh observation differs from the campaign's frozen baseline, or None."""
    base = manifest.get("instrument") or {}
    now = instrument_fingerprint()
    if not base or now["fingerprint"] == base.get("fingerprint"):
        return None
    keys = sorted(k for k in now if k not in ("fingerprint", "commit") and now[k] != base.get(k))
    return (
        f"instrument drift in {keys}: baseline {base.get('fingerprint')} now {now['fingerprint']}"
    )


def campaign_suite_digests(campaign_dir: Path) -> dict[str, str]:
    """The suite content digests this campaign was gated against."""
    p = campaign_dir / "controls_receipts.jsonl"
    if not p.exists():
        return {}
    digests: dict[str, str] = {}
    for line in p.read_text().splitlines():
        if line.strip():
            digests.update(json.loads(line).get("suites") or {})
    return digests


def baseline_reusable(this_dir: Path, other_dir: Path) -> tuple[bool, str]:
    """Whether another campaign's incumbent rows may serve as this cell's baseline.

    A baseline measured by other checkers or other harness code is not a
    baseline, so reuse needs an identical instrument fingerprint and identical
    suite content; otherwise the incumbent is re-run."""
    fa = (load_manifest(this_dir).get("instrument") or {}).get("fingerprint")
    fb = (load_manifest(other_dir).get("instrument") or {}).get("fingerprint")
    if not fa or not fb or fa != fb:
        return False, f"instrument fingerprint {fa!r} != {fb!r}"
    da, db = campaign_suite_digests(this_dir), campaign_suite_digests(other_dir)
    if da != db:
        changed = sorted(k for k in set(da) | set(db) if da.get(k) != db.get(k))
        return False, f"suite content changed since that campaign: {changed[:4]}"
    return True, "same instrument and suite content"


#: An incumbent row is copied only when every one of these matches. The harness
#: digest and the whole portal tree are not part of it: they change on commits
#: that cannot change the served answer. Checkers are re-run on the copy.
#: `baseline_reusable` stays the full-fingerprint predicate and is not called here.
#: Harness sandbox tools are not a portal module; a tool with no module does not match.
_HARNESS_TOOLS = frozenset(TOOL_NAMES)
_SHA_RE = re.compile(r"[0-9a-f]{7,40}\Z")
_TOOL_DEF_RE = re.compile(r"def ([A-Za-z_][A-Za-z0-9_]*)\b")
_TOOL_ROUTE_RE = re.compile(r'custom_route\("/tools/([A-Za-z_][A-Za-z0-9_]*)"')
_NATIVE_DEF_RE = re.compile(r"(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_GREP_PATH_TEXT = re.compile(r"^[0-9a-f]+:(.+\.py)[:\-](.*)$")
_tool_index_cache: dict[str, dict[str, str]] = {}
REUSE_FIELDS = (
    "suite_digest",
    "task_id",
    "repeat",
    "backend",
    "model",
    "content",
    "engine",
    "engine_version",
    "sampling",
    "tool_surface",
    "pipeline",
    "tool_modules",
    "harness",
)


def reuse_key(
    *,
    suite_digest: str | None,
    task_id: str | None,
    repeat: int | None,
    identity: dict | None,
    sampling: dict | None,
    tool_surface: list | None,
    engine: str | None,
    engine_version: str | None,
    pipeline: dict | None,
    tool_modules: dict | None,
    harness: str | None = None,
) -> dict:
    """The incumbent-reuse fingerprint.

    `identity` is model and the model content digest; the backend field is the
    identity group (engine type + base url — `same_identity`'s equality, not
    the group id), so one daemon's groups reuse each other's rows. `pipeline`
    is the inference and config trees at the row's deployed sha. `tool_modules`
    maps each offered portal module to its tree at that sha; None means a tool
    could not be placed, which never matches. `harness` is the tests/wfe content digest
    the row was measured with: a harness change (fixture staging, checkers) never reuses."""
    ident = identity or {}
    return {
        "suite_digest": suite_digest or "",
        "task_id": task_id,
        "repeat": repeat,
        "backend": _identity_group(ident),
        "model": ident.get("model") or "",
        "content": ident.get("content") or "",
        "engine": engine or "",
        "engine_version": engine_version or "",
        "sampling": dict(sampling or {}),
        "tool_surface": list(tool_surface or []),
        "pipeline": dict(pipeline or {}),
        "tool_modules": None if tool_modules is None else dict(tool_modules),
        "harness": harness or "",
    }


def reuse_mismatch(want: dict, have: dict) -> list[str]:
    """Field names that differ.

    An unobserved content id, a missing deployed-build pipeline digest, a missing
    engine or version, or an unplaced tool module never matches, including two
    empties. An empty tool-module map is a real answer: the row was offered only
    harness tools."""
    bad = [k for k in REUSE_FIELDS if want.get(k) != have.get(k)]
    for name in ("content", "pipeline", "engine", "engine_version", "harness"):
        if (not want.get(name) or not have.get(name)) and name not in bad:
            bad.append(name)
    if (want.get("tool_modules") is None or have.get("tool_modules") is None) and (
        "tool_modules" not in bad
    ):
        bad.append("tool_modules")
    return bad


def _key_usable(key: dict) -> bool:
    return not reuse_mismatch(key, key)


def _freeze_reuse_key(key: dict) -> tuple:
    frozen = []
    for name in REUSE_FIELDS:
        value = key.get(name)
        if isinstance(value, (dict, list)):
            frozen.append(json.dumps(value, sort_keys=True))
        else:
            frozen.append(value)
    return tuple(frozen)


def suite_digest_of(campaign_dir: Path, row: dict, cache: dict | None = None) -> str | None:
    """The suite digest this campaign's controls receipt recorded for the row's suite."""
    if cache is not None and campaign_dir in cache:
        digests = cache[campaign_dir]
    else:
        digests = campaign_suite_digests(campaign_dir)
        if cache is not None:
            cache[campaign_dir] = digests
    path = str(row.get("suite_path") or "")
    if path and path in digests:
        return digests[path]
    stem = row.get("suite") or Path(path).stem
    hits = {
        v for k, v in digests.items() if Path(k).stem == stem or Path(k).name == f"{stem}.jsonl"
    }
    if len(hits) == 1:
        return next(iter(hits))
    return None


def expected_incumbent_sampling(stub: dict) -> dict:
    """The sampling `run_row` would record for this stub. No model call."""
    return _sampling_for({}, stub.get("repeat") or 0, row_overrides(stub))


def expected_incumbent_surface(stub: dict, task: dict | None = None) -> list:
    """The tool surface `run_row` would record. A lookup failure yields [] so the
    row is re-run rather than matched against a guess."""
    try:
        no_tools = bool(task and task.get("no_tools"))
        if ENGINE == "pipeline" and not no_tools:
            mode = eval_mode.mode_for(stub.get("workspace") or "", stub.get("tool_mode"))
            if mode:
                return sorted(mode["allow"])
        wsc = workspace_context(
            stub.get("workspace") or "", (stub.get("overrides") or {}).get("persona")
        )
        return list(wsc.get("tool_surface") or TOOL_NAMES)
    except Exception:
        return []


def _task_of(stub: dict, cache: dict) -> dict | None:
    sp = stub.get("suite_path")
    if not sp:
        return None
    if sp not in cache:
        try:
            cache[sp] = {t["id"]: t for t in load_suite(sp)}
        except Exception:
            cache[sp] = {}
    return cache[sp].get(stub.get("task_id"))


_tree_at_cache: dict[tuple[str, str], str] = {}


def tree_at(sha: str, path: str) -> str:
    """The git tree (or blob) hash of `path` at `sha`. Empty when it cannot be read.

    A sha is immutable: one `_git` call per (sha, path) per process; non-sha input is not cached."""
    if not _SHA_RE.fullmatch(sha or ""):
        return ""
    key = (sha, path)
    if key not in _tree_at_cache:
        out = _git("rev-parse", "--verify", f"{sha}:{path}").strip()
        _tree_at_cache[key] = out if re.fullmatch(r"[0-9a-f]{40}", out) else ""
    return _tree_at_cache[key]


#: config/ paths that shape a served answer. The rest of config/ (complexity budget,
#: spine manifest, catalog prose, promptfoo, dashboards) changes with nearly every
#: commit and would make reuse inert. portal.yaml is keyed by the row's own workspace
#: block, so a seat edit elsewhere does not invalidate this workspace's rows.
_SERVING_CONFIG = (
    "config/inference",
    "config/personas",
    "config/bench_workspaces.yaml",
    "config/chat_templates",
    "config/backends.yaml",
    "config/engine_contract.yaml",
    "config/tool_catalog.yaml",
    "config/routing_descriptions.json",
    "config/routing_examples.json",
)


_workspaces_cache: dict[str, dict] = {}
_workspace_block_cache: dict[tuple[str, str], str] = {}


def _workspaces_at(sha: str) -> dict:
    """portal.yaml + bench_workspaces.yaml workspaces at sha, parsed once per sha."""
    if sha not in _workspaces_cache:
        workspaces: dict = {}
        for path in ("config/portal.yaml", "config/bench_workspaces.yaml"):
            try:
                doc = yaml.safe_load(_git("show", f"{sha}:{path}")) or {}
            except yaml.YAMLError:
                continue
            workspaces.update(doc.get("workspaces") or {})
        _workspaces_cache[sha] = workspaces
    return _workspaces_cache[sha]


def _workspace_block_digest(sha: str, workspace: str) -> str:
    """The workspace's base/variant block hash at sha, computed uncached."""
    workspaces = _workspaces_at(sha)
    base_id, _, variant = workspace.partition("::")
    base = workspaces.get(base_id)
    if not isinstance(base, dict):
        return ""
    try:
        effective = effective_workspace(workspaces, workspace)
    except (KeyError, TypeError):
        return ""
    if variant:
        variant_block = (base.get("variants") or {}).get(variant)
        if not isinstance(variant_block, dict):
            return ""
        block = {"base": base, "variant": variant_block, "effective": effective}
    else:
        block = effective
    return hashlib.sha256(json.dumps(block, sort_keys=True, default=str).encode()).hexdigest()


def _workspace_block(sha: str, workspace: str) -> str:
    """Hash the base block and selected variant block at sha (portal.yaml or the bench config).

    A sha is immutable: the parse runs once per sha, the hash once per (sha, workspace)."""
    if not workspace or not _SHA_RE.fullmatch(sha or ""):
        return ""
    key = (sha, workspace)
    if key not in _workspace_block_cache:
        _workspace_block_cache[key] = _workspace_block_digest(sha, workspace)
    return _workspace_block_cache[key]


_pipeline_cache: dict[tuple[str, str], dict] = {}


def pipeline_at(sha: str, workspace: str) -> dict:
    """Hash the router, serving config paths and workspace block at a build sha. Memoized."""
    if not workspace or not _SHA_RE.fullmatch(sha or ""):
        return {}
    key = (sha, workspace)
    if key not in _pipeline_cache:
        inference = tree_at(sha, "portal/platform/inference")
        block = _workspace_block(sha, workspace)
        _pipeline_cache[key] = (
            {}
            if not inference or not block
            else {
                "inference": inference,
                "workspace": block,
                **{path: tree_at(sha, path) for path in _SERVING_CONFIG},
            }
        )
    return dict(_pipeline_cache[key])


def _tool_index(sha: str) -> dict[str, str]:
    """Tool function name to `portal/modules/<module>` at one commit."""
    if sha in _tool_index_cache:
        return _tool_index_cache[sha]
    index: dict[str, str] = {}
    out = _git("grep", "-E", r"^(async )?def [A-Za-z_]", sha, "--", "portal/modules")
    for line in out.splitlines():
        try:
            _rev, path, text = line.split(":", 2)
        except ValueError:
            continue
        found = _TOOL_DEF_RE.search(text)
        parts = path.split("/")
        if not found or len(parts) < 3 or parts[0] != "portal" or parts[1] != "modules":
            continue
        index.setdefault(found.group(1), f"portal/modules/{parts[2]}")
    # A `/tools/<name>` route is the served tool itself, so it wins over a same-named
    # function elsewhere (field_journal's `def recall` used to claim the memory tool).
    # Platform services (the memory server) expose tools only this way; without these,
    # every row offered remember/recall had an unplaced tool and was never reusable.
    out = _git(
        "grep", "-E", r'custom_route\("/tools/', sha, "--", "portal/modules", "portal/platform"
    )
    for line in out.splitlines():
        try:
            _rev, path, text = line.split(":", 2)
        except ValueError:
            continue
        found = _TOOL_ROUTE_RE.search(text)
        parts = path.split("/")
        if (
            found
            and len(parts) >= 3
            and parts[0] == "portal"
            and parts[1] in ("modules", "platform")
        ):
            index[found.group(1)] = f"portal/{parts[1]}/{parts[2]}"
    _index_native_tools(sha, index)
    _tool_index_cache[sha] = index
    return index


def _grep_path_text(line: str) -> tuple[str, str] | None:
    """`sha:path:text` or `sha:path-text` from `git grep -A`."""
    matched = _GREP_PATH_TEXT.match(line)
    if matched is None:
        return None
    return matched.group(1), matched.group(2)


def _module_of(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == "portal" and parts[1] in ("modules", "platform"):
        return f"portal/{parts[1]}/{parts[2]}"
    return None


def _index_native_tools(sha: str, index: dict[str, str]) -> None:
    """`@mcp.tool()` definitions are the served tool, including native-only servers."""
    out = _git(
        "grep",
        "-A",
        "1",
        "-E",
        r"@mcp\.tool\(",
        sha,
        "--",
        "portal/modules",
        "portal/platform",
    )
    pending: str | None = None
    for line in out.splitlines():
        if line == "--" or not line:
            pending = None
            continue
        parsed = _grep_path_text(line)
        if parsed is None:
            pending = None
            continue
        path, text = parsed
        if "@mcp.tool(" in text:
            pending = path
            continue
        if pending != path:
            continue
        found = _NATIVE_DEF_RE.search(text)
        pending = None
        if found and (module := _module_of(path)):
            index[found.group(1)] = module


_tool_trees_cache: dict[tuple[str, tuple], dict | None] = {}


def _tool_module_trees_at(sha: str, tools: list | None) -> dict | None:
    """The module tree map for one tool surface at sha, computed uncached."""
    index = _tool_index(sha)
    modules: set[str] = set()
    for name in tools or []:
        if name in _HARNESS_TOOLS:
            continue
        path = index.get(name)
        if not path:
            return None
        modules.add(path)
    trees: dict[str, str] = {}
    for path in sorted(modules):
        tree = tree_at(sha, path)
        if not tree:
            return None
        trees[path] = tree
    return trees


def tool_module_trees(sha: str, tools: list | None) -> dict | None:
    """Tree hash of each portal module the row was offered, at the deployed sha.

    Harness sandbox tools have no module. None means a non-harness tool could
    not be placed, or the sha has no tree, so the row is run rather than copied.
    A sha is immutable: memoized per (sha, tool surface), copied per call."""
    if not _SHA_RE.fullmatch(sha or ""):
        return None
    key = (sha, tuple(tools or []))
    if key not in _tool_trees_cache:
        _tool_trees_cache[key] = _tool_module_trees_at(sha, tools)
    found = _tool_trees_cache[key]
    return dict(found) if found is not None else None


def _deployed_sha(instrument: dict | None) -> str:
    sha = str((instrument or {}).get("deployed") or "")
    return sha if _SHA_RE.fullmatch(sha) else ""


def _engine_stamp(env: dict | None, instrument: dict | None) -> tuple[str, str]:
    """Engine name and the version that can change a served answer.

    Pipeline rows are served by Ollama, so the version is `ollama_version`.
    An oMLX row uses that engine's own version."""
    env = env or {}
    instrument = instrument or {}
    engine = str(instrument.get("engine") or env.get("engine") or "")
    if engine == "omlx":
        version = str(env.get("engine_version") or "")
    else:
        version = str(env.get("ollama_version") or env.get("engine_version") or "")
    if version == "unknown":
        version = ""
    return engine, version


def recorded_reuse_key(campaign_dir: Path, row: dict, digests: dict | None = None) -> dict:
    """The reuse fingerprint of a row that has already been graded."""
    inst = row.get("instrument") or {}
    sha = _deployed_sha(inst)
    engine, version = _engine_stamp(row.get("env"), inst)
    surface = list(row.get("tool_surface") or [])
    return reuse_key(
        suite_digest=suite_digest_of(campaign_dir, row, digests),
        task_id=row.get("task_id"),
        repeat=row.get("repeat"),
        identity=row.get("identity"),
        sampling=row.get("sampling"),
        tool_surface=surface,
        engine=engine,
        engine_version=version,
        pipeline=pipeline_at(sha, row.get("workspace") or ""),
        tool_modules=tool_module_trees(sha, surface),
        harness=inst.get("harness"),
    )


def destination_reuse_key(
    campaign_dir: Path,
    manifest: dict,
    stub: dict,
    task: dict | None = None,
    digests: dict | None = None,
) -> dict:
    """The reuse fingerprint the pending stub would have if this campaign ran it.

    Identity comes from the frozen map. The deployed sha is the one this
    campaign recorded at open. No live probe."""
    inst = manifest.get("instrument") or {}
    sha = _deployed_sha(inst)
    engine, version = _engine_stamp(manifest.get("env"), inst)
    surface = expected_incumbent_surface(stub, task)
    return reuse_key(
        suite_digest=suite_digest_of(campaign_dir, stub, digests),
        task_id=stub.get("task_id"),
        repeat=stub.get("repeat"),
        identity=frozen_identity(manifest, stub),
        sampling=expected_incumbent_sampling(stub),
        tool_surface=surface,
        engine=engine,
        engine_version=version,
        pipeline=pipeline_at(sha, stub.get("workspace") or ""),
        tool_modules=tool_module_trees(sha, surface),
        harness=inst.get("harness"),
    )


def _quality_outcome(outcome: str | None) -> bool:
    return outcome in {o.value for o in MODEL_QUALITY_OUTCOMES}


def _iter_incumbent_results(campaign_dir: Path) -> list[tuple[str, dict]]:
    """Graded incumbent rows of one campaign: (campaign id, row). Read-only."""
    try:
        manifest = load_manifest(campaign_dir)
    except (OSError, ValueError):
        return []
    cid = manifest.get("campaign_id") or campaign_dir.name
    out = []
    for stub in manifest.get("rows") or []:
        if stub.get("arm_role") != "incumbent" or stub.get("state") == "PENDING":
            continue
        path = _row_path(campaign_dir, stub["run_id"])
        if not path.is_file():
            continue
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if row.get("arm_role") != "incumbent" or not _quality_outcome(row.get("outcome")):
            continue
        row.setdefault("campaign_id", cid)
        row.setdefault("run_id", stub["run_id"])
        out.append((cid, row))
    return out


_REUSE_INDEX_CACHE: dict[tuple[Path, Path], dict[tuple, list[tuple[str, Path, dict]]]] = {}


def _build_reusable_incumbent_index(
    campaign_dir: Path, campaigns_root: Path
) -> dict[tuple, list[tuple[str, Path, dict]]]:
    """Earlier campaigns' graded incumbent rows, keyed by the reuse fingerprint."""
    index: dict[tuple, list[tuple[str, Path, dict]]] = {}
    if not campaigns_root.is_dir():
        return index
    here = campaign_dir.resolve()
    digests: dict = {}
    for other in sorted(p for p in campaigns_root.iterdir() if p.is_dir()):
        try:
            if other.resolve() == here:
                continue
        except OSError:
            continue
        if not (other / "manifest.json").is_file():
            continue
        for cid, row in _iter_incumbent_results(other):
            recorded = recorded_reuse_key(other, row, digests)
            if not _key_usable(recorded):
                continue
            index.setdefault(_freeze_reuse_key(recorded), []).append((cid, other, row))
    return index


def _index_reusable_incumbents(
    campaign_dir: Path, campaigns_root: Path
) -> dict[tuple, list[tuple[str, Path, dict]]]:
    """Memoized per (campaigns_root, campaign_dir): one cold build per process."""
    key = (campaigns_root, campaign_dir)
    if key not in _REUSE_INDEX_CACHE:
        _REUSE_INDEX_CACHE[key] = _build_reusable_incumbent_index(campaign_dir, campaigns_root)
    return _REUSE_INDEX_CACHE[key]


def _provenance(campaign_id: str, row: dict) -> str:
    """`<campaign>/<row>`. A row that was itself copied keeps the original source."""
    return str(row.get("reused_from") or f"{campaign_id}/{row.get('run_id')}")


def release_reused_incumbents(campaign_dir: Path, manifest: dict) -> int:
    """Drop copied incumbent rows so `--fresh-incumbent` runs them again.

    A row this campaign graded itself has no `reused_from` and is left alone."""
    n = 0
    for stub in manifest.get("rows") or []:
        if stub.get("arm_role") != "incumbent":
            continue
        path = _row_path(campaign_dir, stub["run_id"])
        if not path.is_file():
            continue
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not row.get("reused_from"):
            continue
        path.unlink()
        stub["state"] = "PENDING"
        stub.pop("reused_from", None)
        stub.pop("note", None)
        n += 1
    if n:
        save_manifest(campaign_dir, manifest)
        _log(campaign_dir, f"fresh incumbent: released {n} reused row(s)")
    return n


def _debug_by_run(campaign_dir: Path, cache: dict) -> dict:
    """run_id to the debug record that holds the sandbox tree, when one was kept."""
    if campaign_dir in cache:
        return cache[campaign_dir]
    found: dict = {}
    debug = campaign_dir / "debug"
    if debug.is_dir():
        for path in sorted(debug.glob("*.debug.jsonl")):
            try:
                lines = path.read_text().splitlines()
            except OSError:
                continue
            for line in lines:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("run_id"):
                    found[rec["run_id"]] = rec
    cache[campaign_dir] = found
    return found


def regrade_copied(row: dict, task: dict, debug_rec: dict | None = None):
    """Re-grade one copied row with the current checkers. No model call.

    Returns (outcome, why, check) or None when the checkers cannot be applied.
    The outcome is the one that counts; the caller keeps the earlier outcome
    beside it."""
    rec = {
        "final_text": row.get("final_text", ""),
        "assistant_texts": row.get("assistant_texts")
        or ([row["final_text"]] if row.get("final_text") else []),
        "tool_call_log": row.get("tool_call_log"),
        "transcript": row.get("transcript") or [],
        "turn_results": row.get("turn_results"),
        "finish_reason": row.get("finish_reason"),
        "sandbox_tree": row.get("sandbox_tree"),
        "outcome": row.get("outcome"),
    }
    for name in (
        "final_text",
        "assistant_texts",
        "tool_call_log",
        "transcript",
        "turn_results",
        "finish_reason",
        "sandbox_tree",
    ):
        if debug_rec and debug_rec.get(name) not in (None, ""):
            rec[name] = debug_rec[name]
    if not task.get("turns"):
        checks = task.get("checkers")
        if checks is None:
            checks = [task.get("checker") or {}]
        if _checkers_need_tool_log(checks) and not isinstance(rec.get("tool_call_log"), list):
            return None
    try:
        cr = (
            _rehydrate_scripted_check(rec, task)
            if task.get("turns")
            else _rehydrate_check(rec, task)
        )
    except Exception:
        return None
    if cr is None:
        return None
    final, why = _reconcile_offline(row.get("outcome"), cr.outcome.value)
    return final, why, cr


def _mark_reused(manifest: dict, stub: dict, outcome: str | None, provenance: str) -> None:
    """Record the copy on the stub and on the manifest row, which may be a different dict."""
    for row in manifest.get("rows") or []:
        if row.get("run_id") == stub.get("run_id"):
            row["state"] = outcome
            row["reused_from"] = provenance
    stub["state"] = outcome
    stub["reused_from"] = provenance


def _adopt_existing_reuse(manifest: dict, stub: dict, path: Path) -> str | None:
    """A copy already on disk counts as present. A row this campaign graded is left."""
    try:
        existing = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if existing.get("reused_from") and _quality_outcome(existing.get("outcome")):
        _mark_reused(manifest, stub, existing["outcome"], existing["reused_from"])
        return stub["run_id"]
    return None


def _suite_still_matches(stub: dict, want: dict) -> bool:
    """The suite file must still be the one the receipt gated. Otherwise run the row."""
    from tests.wfe.controls import suite_digest

    try:
        current = suite_digest(stub["suite_path"])
    except OSError:
        return False
    return current == want.get("suite_digest")


def _choose_reuse_source(
    campaign_dir: Path, stub: dict, hits: list
) -> tuple[str, Path, dict] | None:
    """One source, or none when there is no hit or the recorded outcomes disagree."""
    outcomes = {row.get("outcome") for _, _src, row in hits}
    if len(outcomes) != 1:
        if len(outcomes) > 1:
            _log(campaign_dir, f"not reusing {stub['run_id']}: sources disagree on the outcome")
        return None
    return sorted(hits, key=lambda item: (item[0], item[2].get("run_id") or ""))[0]


def _write_reused_copy(
    campaign_dir: Path,
    manifest: dict,
    stub: dict,
    src: dict,
    cid: str,
    graded: tuple,
    path: Path,
) -> None:
    final, why, cr = graded
    body = dict(src)
    body["original_outcome"] = src.get("original_outcome") or src.get("outcome")
    body["regraded_outcome"] = final
    body["outcome"] = final
    body["notes"] = f"{cr.notes} [{why}]"
    body["evidence"] = cr.evidence
    body["reused_from"] = _provenance(cid, src)
    body["campaign_id"] = manifest.get("campaign_id") or campaign_dir.name
    body["run_id"] = stub["run_id"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1))
    _mark_reused(manifest, stub, final, body["reused_from"])
    _log(campaign_dir, f"reused {stub['run_id']} from {body['reused_from']}: {why}")


def _reuse_one(
    campaign_dir: Path,
    manifest: dict,
    stub: dict,
    index: dict,
    tasks: dict,
    digests: dict,
    debug_cache: dict,
) -> str | None:
    path = _row_path(campaign_dir, stub["run_id"])
    if path.is_file():
        return _adopt_existing_reuse(manifest, stub, path)
    task = _task_of(stub, tasks)
    want = destination_reuse_key(campaign_dir, manifest, stub, task, digests)
    if not _key_usable(want) or task is None or not _suite_still_matches(stub, want):
        return None
    chosen = _choose_reuse_source(campaign_dir, stub, index.get(_freeze_reuse_key(want)) or [])
    if chosen is None:
        return None
    cid, src_dir, src = chosen
    debug = _debug_by_run(src_dir, debug_cache).get(src.get("run_id"))
    graded = regrade_copied(src, task, debug)
    if graded is None or not _quality_outcome(graded[0]):
        return None
    _write_reused_copy(campaign_dir, manifest, stub, src, cid, graded, path)
    return stub["run_id"]


def reuse_incumbent_rows(
    campaign_dir: Path,
    manifest: dict,
    stubs: list[dict],
    campaigns_root: Path | None = None,
) -> list[str]:
    """Copy matching incumbent rows from earlier campaigns. Returns copied run ids.

    The copy records `reused_from: <campaign>/<row>`, `original_outcome` and
    `regraded_outcome`. The regraded outcome is the one that counts. Two sources
    that match the fingerprint and disagree on the recorded outcome are not
    copied. A suite file that no longer matches the receipt is run, not copied.
    An interleaved campaign never copies: both arms run every row live under the
    same conditions — rows already graded in THIS campaign still resume."""
    pending = [
        s for s in stubs if s.get("arm_role") == "incumbent" and s.get("state") in (None, "PENDING")
    ]
    if not pending:
        return []
    if (manifest.get("execution") or {}).get("arm_order") == "interleaved":
        return []
    root = campaigns_root if campaigns_root is not None else CAMPAIGNS
    index = _index_reusable_incumbents(campaign_dir, root)
    if not index:
        return []
    tasks: dict = {}
    digests: dict = {}
    debug_cache: dict = {}
    copied = [
        run_id
        for stub in pending
        if (run_id := _reuse_one(campaign_dir, manifest, stub, index, tasks, digests, debug_cache))
    ]
    if copied:
        save_manifest(campaign_dir, manifest)
        _log(campaign_dir, f"reused {len(copied)} incumbent row(s) from earlier campaigns")
    return copied


def _iter_challenger_results(campaign_dir: Path) -> list[tuple[str, dict]]:
    try:
        manifest = load_manifest(campaign_dir)
    except (OSError, ValueError):
        return []
    cid = manifest.get("campaign_id") or campaign_dir.name
    out = []
    for stub in manifest.get("rows") or []:
        if stub.get("arm_role") != "challenger" or stub.get("state") in (None, "PENDING"):
            continue
        path = _row_path(campaign_dir, stub["run_id"])
        if not path.is_file():
            continue
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if row.get("arm_role") != "challenger" or not _quality_outcome(row.get("outcome")):
            continue
        row.setdefault("campaign_id", cid)
        row.setdefault("run_id", stub["run_id"])
        out.append((cid, row))
    return out


def _index_reusable_screen_rows(campaign_dir: Path, source_ids: list[str]) -> dict:
    candidates: dict = {}
    root = CAMPAIGNS.resolve()
    digests: dict = {}
    seen: set[str] = set()
    for source_id in source_ids:
        if not source_id or Path(source_id).name != source_id or source_id in (".", ".."):
            _log(campaign_dir, f"screen reuse: invalid campaign id {source_id!r}; skipped")
            continue
        try:
            other = (CAMPAIGNS / source_id).resolve()
        except OSError:
            _log(campaign_dir, f"screen reuse: cannot resolve campaign {source_id!r}; skipped")
            continue
        if other.parent != root:
            _log(campaign_dir, f"screen reuse: campaign {source_id!r} is outside campaigns root")
            continue
        if other == campaign_dir.resolve():
            _log(campaign_dir, f"screen reuse: {source_id!r} is this campaign; skipped")
            continue
        if source_id in seen:
            continue
        seen.add(source_id)
        if not (other / "manifest.json").is_file():
            _log(campaign_dir, f"screen reuse: campaign {source_id!r} has no manifest")
            continue
        for cid, row in _iter_challenger_results(other):
            key = recorded_reuse_key(other, row, digests)
            item = (cid, other, row, key)
            task_key = (
                row.get("workspace"),
                row.get("arm"),
                row.get("suite"),
                row.get("task_id"),
            )
            candidates.setdefault(task_key, []).append(item)
    return candidates


def _reuse_screen_one(
    campaign_dir: Path,
    manifest: dict,
    stub: dict,
    candidates: dict,
    tasks: dict,
    digests: dict,
    debug_cache: dict,
) -> str | None:
    path = _row_path(campaign_dir, stub["run_id"])
    if path.is_file():
        return stub["run_id"] if _adopt_existing_reuse(manifest, stub, path) else None
    task = _task_of(stub, tasks)
    want = destination_reuse_key(campaign_dir, manifest, stub, task, digests)
    if not _key_usable(want):
        missing = reuse_mismatch(want, want)
        _log(
            campaign_dir,
            f"not reusing {stub['run_id']}: destination fingerprint incomplete {missing}",
        )
        return None
    if task is None or not _suite_still_matches(stub, want):
        _log(campaign_dir, f"not reusing {stub['run_id']}: task or suite receipt changed")
        return None
    task_key = (
        stub.get("workspace"),
        stub.get("arm"),
        stub.get("suite"),
        stub.get("task_id"),
    )
    hits = []
    for cid, src_dir, src, recorded in candidates.get(task_key, []):
        mismatch = reuse_mismatch(want, recorded)
        if mismatch:
            _log(
                campaign_dir,
                f"not reusing {stub['run_id']} from {cid}/{src.get('run_id')}: "
                f"fingerprint mismatch {mismatch}",
            )
        else:
            hits.append((cid, src_dir, src))
    chosen = _choose_reuse_source(campaign_dir, stub, hits)
    if chosen is None:
        return None
    cid, src_dir, src = chosen
    debug = _debug_by_run(src_dir, debug_cache).get(src.get("run_id"))
    graded = regrade_copied(src, task, debug)
    if graded is None or not _quality_outcome(graded[0]):
        _log(campaign_dir, f"not reusing {stub['run_id']} from {cid}: current regrade unavailable")
        return None
    _write_reused_copy(campaign_dir, manifest, stub, src, cid, graded, path)
    return stub["run_id"]


def reuse_screen_rows(
    campaign_dir: Path,
    manifest: dict,
    stubs: list[dict],
    source_ids: list[str] | None = None,
) -> list[str]:
    pending = [
        s
        for s in stubs
        if s.get("arm_role") == "challenger"
        and s.get("tier", "confirm") == "confirm"
        and s.get("state") in (None, "PENDING")
    ]
    selected = list(
        dict.fromkeys(source_ids if source_ids is not None else manifest.get("reuse_screen") or [])
    )
    if not pending or not selected:
        return []
    candidates = _index_reusable_screen_rows(campaign_dir, selected)

    tasks: dict = {}
    digests: dict = {}
    debug_cache: dict = {}
    copied = [
        run_id
        for stub in pending
        if (
            run_id := _reuse_screen_one(
                campaign_dir, manifest, stub, candidates, tasks, digests, debug_cache
            )
        )
    ]
    if copied:
        save_manifest(campaign_dir, manifest)
        _log(campaign_dir, f"reused {len(copied)} challenger row(s) from selected campaigns")
    return copied


def incumbent_reuse_report(src_dir: Path, dst_dir: Path) -> dict:
    """Read-only: which of dst's incumbent rows src could supply, and why not.

    Both sides are compared as recorded. Nothing is copied and nothing is graded."""
    dst = load_manifest(dst_dir)
    src_rows = _iter_incumbent_results(src_dir)
    digests: dict = {}
    rows = []
    for stub in dst.get("rows") or []:
        if stub.get("arm_role") != "incumbent":
            continue
        path = _row_path(dst_dir, stub["run_id"])
        recorded = None
        if path.is_file():
            try:
                recorded = json.loads(path.read_text())
            except (OSError, ValueError):
                recorded = None
        if recorded and recorded.get("outcome"):
            want = recorded_reuse_key(dst_dir, recorded, digests)
        else:
            want = destination_reuse_key(dst_dir, dst, stub, digests=digests)
        same = [
            (cid, row)
            for cid, row in src_rows
            if row.get("task_id") == stub.get("task_id") and row.get("repeat") == stub.get("repeat")
        ]
        if not same:
            rows.append(
                {
                    "run_id": stub["run_id"],
                    "task_id": stub.get("task_id"),
                    "repeat": stub.get("repeat"),
                    "match": False,
                    "diffs": ["no source row"],
                }
            )
            continue
        diffs = [reuse_mismatch(want, recorded_reuse_key(src_dir, row, digests)) for _, row in same]
        ok = any(not d for d in diffs)
        rows.append(
            {
                "run_id": stub["run_id"],
                "task_id": stub.get("task_id"),
                "repeat": stub.get("repeat"),
                "match": ok,
                "diffs": [] if ok else diffs[0],
            }
        )
    matched = sum(1 for r in rows if r["match"])
    return {
        "src": src_dir.name,
        "dst": dst_dir.name,
        "dst_incumbent_rows": len(rows),
        "matched": matched,
        "unmatched": len(rows) - matched,
        "rows": rows,
    }


def gate_execution(campaign_dir: Path) -> None:
    """Controls gate plus baseline check before any row of a resumed campaign runs."""
    from tests.wfe.checkers import missing_office_parsers

    missing = missing_office_parsers()
    if missing:
        raise GateRefused("campaign preflight: missing module " + ", ".join(missing))
    m = load_manifest(campaign_dir)
    keep_receipt(campaign_dir, gate_controls(m["rows"], "execute"))
    drift = instrument_drift(m)
    if drift:
        raise GateRefused(f"execute: {drift}; open a new campaign for the changed instrument")


def tool_gaps(rows: list[dict]) -> list[str]:
    """Rows whose task requires tools the row's tool surface cannot offer."""
    out, surface, tasks = set(), {}, {}
    for r in rows:
        sp = r.get("suite_path")
        if not sp:
            continue
        tasks.setdefault(sp, {t["id"]: t for t in load_suite(sp)})
        need = set((tasks[sp].get(r["task_id"]) or {}).get("requires_tools") or [])
        key = (r["workspace"], row_overrides(r).get("persona"))
        if need and key not in surface:
            prod = (
                eval_mode.mode_for(r["workspace"], r.get("tool_mode"))
                if ENGINE == "pipeline"
                else None
            )
            surface[key] = (
                set(prod["allow"])
                if prod
                else set(workspace_context(*key).get("tool_surface") or TOOL_NAMES)
            )
        missing = sorted(need - surface.get(key, set(TOOL_NAMES)))
        if missing:
            out.add(
                f"{r['suite']}:{r['task_id']} in {r['workspace']}: needs tools not offered {missing}"
            )
    return sorted(out)


def gate_controls(rows: list[dict], where: str) -> dict:
    """Known-answer controls for these rows' tasks; raises on failure, returns the receipt."""
    from tests.wfe import controls

    dirty = instrument_dirty()
    if dirty and os.environ.get("WFE_ALLOW_DIRTY_INSTRUMENT") != "1":
        raise GateRefused(
            f"{where}: the instrument has uncommitted changes {dirty[:8]}; commit first"
        )
    paths = sorted({r["suite_path"] for r in rows if r.get("suite_path")})
    rec = controls.receipt(paths, {r["task_id"] for r in rows if r.get("suite_path")})
    rec["failures"] += tool_gaps(rows)
    if rec["failures"]:
        raise GateRefused(
            f"{where}: {len(rec['failures'])} task control(s) fail — the checker cannot tell "
            "a right answer from a wrong one (or a key has expired), so no model can be "
            "scored with it:\n  " + "\n  ".join(rec["failures"][:40])
        )
    return {**rec, "where": where}


def keep_receipt(campaign_dir: Path, rec: dict) -> None:
    """Append a receipt to controls_receipts.jsonl, never to the manifest."""
    with (campaign_dir / "controls_receipts.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _record_screen_reuse_sources(manifest: dict, source_ids: list[str] | None) -> bool:
    sources = manifest.setdefault("reuse_screen", [])
    changed = False
    for source_id in source_ids or []:
        if source_id not in sources:
            sources.append(source_id)
            changed = True
    return changed


def setup_exclusions(campaign_dir: Path) -> dict[str, str]:
    """Workspace -> reason from sibling `<id>_canary/excluded.json`. A canary excludes nothing."""
    name = Path(campaign_dir).name
    if name.endswith("_canary"):
        return {}
    path = Path(campaign_dir).parent / f"{name}_canary" / "excluded.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, list):
        return {}
    out: dict[str, str] = {}
    for item in raw:
        if isinstance(item, dict) and item.get("workspace"):
            out.setdefault(str(item["workspace"]), str(item.get("reason") or ""))
    return out


def apply_setup_exclusions(campaign_dir: Path, manifest: dict) -> list[str]:
    """Mark still-pending rows of an excluded workspace EXCLUDED_SETUP. Returns workspaces."""
    excluded = setup_exclusions(campaign_dir)
    if not excluded:
        return []
    marked: list[str] = []
    for row in manifest.get("rows") or []:
        reason = excluded.get(str(row.get("workspace") or ""))
        if reason is None or row.get("state") != "PENDING":
            continue
        row["state"] = Outcome.EXCLUDED_SETUP.value
        row["note"] = reason
        marked.append(str(row.get("workspace")))
    if marked:
        save_manifest(campaign_dir, manifest)
    return marked


def _opened(campaign_dir: Path) -> Path:
    apply_setup_exclusions(campaign_dir, load_manifest(campaign_dir))
    return campaign_dir


def open_campaign(
    cid: str,
    plan_path: Path,
    matrix: list[dict],
    append: bool,
    reuse_screen: list[str] | None = None,
    execution: dict | None = None,
) -> Path:
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
        added_execution = execution is not None and not (
            (manifest.get("execution") or {}).get("interleave_block_by_workspace")
        )
        if added_execution:
            manifest["execution"] = execution
        if not append:
            if added_execution:
                save_manifest(d, manifest)
            if _record_screen_reuse_sources(manifest, reuse_screen):
                save_manifest(d, manifest)
            return _opened(d)
        if instrument_drift(manifest):
            raise GateRefused(f"append: {instrument_drift(manifest)}; open a new campaign")
        known = {r["run_id"] for r in manifest["rows"]}
        added = [r for r in matrix if r["run_id"] not in known]
        changed_workspaces = {r.get("workspace") for r in added if r.get("workspace")}
        if execution is not None and changed_workspaces:
            saved = manifest.setdefault("execution", {})
            for key in (
                "interleave_block_by_workspace",
                "interleave_block_reason_by_workspace",
                "interleave_models_by_workspace",
            ):
                target = saved.setdefault(key, {})
                source = execution.get(key) or {}
                for workspace in changed_workspaces:
                    if workspace in source:
                        target[workspace] = source[workspace]
            saved["interleave_block"] = max(
                (saved.get("interleave_block_by_workspace") or {}).values(),
                default=execution.get("interleave_block", 4),
            )
            saved["interleave_swap_profiles"] = execution.get("interleave_swap_profiles", {})
            saved["interleave_block_override"] = execution.get("interleave_block_override", False)
        keep_receipt(d, gate_controls([*manifest["rows"], *added], "append"))
        manifest["rows"].extend(added)
        manifest["rows"].sort(
            key=lambda r: (r["arm"], r["workspace"], r["suite"], r["task_id"], r["repeat"])
        )
        _record_screen_reuse_sources(manifest, reuse_screen)
        manifest.setdefault("appends", []).append(
            {
                "utc": dt.datetime.now(dt.UTC).isoformat(),
                "added": len(added),
                "instrument": instrument_fingerprint(),
            }
        )
        mpath.write_text(json.dumps(manifest, indent=1))
        print(f"appended {len(added)} rows ({len(matrix) - len(added)} already present)")
        return _opened(d)
    rec = gate_controls(matrix, "open")
    keep_receipt(d, rec)
    mpath.write_text(
        json.dumps(
            {
                "schema": MANIFEST_SCHEMA_VERSION,
                "instrument": instrument_fingerprint(),
                "campaign_id": cid,
                "plan": str(plan_path),
                "plan_sha": sha12(plan_path.read_text()),
                "created_utc": dt.datetime.now(dt.UTC).isoformat(),
                "env": env_fingerprint(OLLAMA),
                "config_dirty_at_start": config_dirty(),
                "reuse_screen": list(dict.fromkeys(reuse_screen or [])),
                "execution": execution or {},
                "rows": matrix,
            },
            indent=1,
        )
    )
    return _opened(d)


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
#: an exhausted wall or turn budget, a blocked-offline task, an all-errored tool
#: loop. apply_checkers cannot re-derive these from a static record, so --rescore
#: preserves them.
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
    mirroring runner._classify's precedence. Returns (outcome, why).

    BUDGET_EXHAUSTED always stands: the model did not finish, and a checker
    re-grade — even a PASS on the artifacts it left — cannot change that. This
    used to upgrade it to PASS, which re-created the stall-masking defect on
    every --rescore. BLOCKED stands too: a row the seat did not serve (a
    failover turn) is not seat evidence however well it grades. The other
    telemetry outcomes may still be upgraded by a checker PASS (a too-strict
    checker was the real reason for a FAIL-shaped TOOL_ERROR)."""
    if recorded in (Outcome.BUDGET_EXHAUSTED.value, Outcome.BLOCKED.value) or (
        recorded in _RUN_TELEMETRY_OUTCOMES and checker_outcome != Outcome.PASS.value
    ):
        return (
            recorded,
            f"kept recorded {recorded} (run telemetry; checker re-grade: {checker_outcome})",
        )
    return checker_outcome, "checker re-grade"


def _rehydrate_check(rec: dict, task: dict):
    """Grade one recorded run from its captured artifacts, then drop the tree."""
    root = rehydrate_tree(rec.get("sandbox_tree") or {})
    transcript = rec.get("transcript") or []
    try:
        return apply_checkers(
            task,
            CheckContext(
                final_text=rec.get("final_text", ""),
                assistant_texts=rec.get("assistant_texts") or [],
                tool_calls=rec.get("tool_call_log") or [],
                sandbox_root=root,
                task=task,
                finish_reason=rec.get("finish_reason"),
                owui_context=str(rec.get("owui_context") or ""),
                served=next(
                    (
                        t.get("served")
                        for t in reversed(transcript)
                        if (t.get("served") or {}).get("options")
                    ),
                    None,
                ),
            ),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


_TREE_CHECKERS = frozenset(
    {
        "file_exists",
        "file_contains",
        "hidden_pytest",
        "immutable",
        "office_contains",
        "pytest_pass",
        "receipt_artifact",
    }
)


def _checkers_need_tool_log(checks: list[dict]) -> bool:
    return any(
        spec.get("type") in {"tool_grounded", "cited_answer", "compliance_reading_contract"}
        or bool(spec.get("forbid_in_tool_output"))
        for spec in checks
    )


def _scripted_turn_range(state: dict, index: int, tool_count: int) -> tuple[int, int] | None:
    required = ("final_text", "assistant_texts", "tool_call_range", "finish_reason", "served")
    if state.get("turn") != index:
        return None
    if any(key not in state for key in required) or not isinstance(state["assistant_texts"], list):
        return None
    call_range = state["tool_call_range"]
    if (
        not isinstance(call_range, list)
        or len(call_range) != 2
        or not all(isinstance(n, int) for n in call_range)
    ):
        return None
    start, end = call_range
    if start < 0 or end < start or end > tool_count:
        return None
    return start, end


def _scripted_turn_context(
    task: dict, state: dict, tool_log: list, end: int, root: Path
) -> CheckContext:
    """Check context for one saved scripted turn, including its RAG prefix."""
    return CheckContext(
        final_text=state["final_text"],
        assistant_texts=state["assistant_texts"],
        tool_calls=tool_log[:end],
        sandbox_root=root,
        task=task,
        finish_reason=state["finish_reason"],
        served=state["served"],
        owui_context=str(state.get("owui_context") or ""),
    )


def _rehydrate_scripted_check(rec: dict, task: dict):
    """Re-grade scripted turns from their saved inputs or decline incomplete evidence."""
    turns = task.get("turns") or []
    saved = rec.get("turn_results")
    tool_log = rec.get("tool_call_log")
    if not isinstance(saved, list) or len(saved) != len(turns):
        return None
    needs_tool_log = any(
        spec.get("expect_tools") or _checkers_need_tool_log(spec.get("checks") or [])
        for spec in turns
    )
    if not isinstance(tool_log, list):
        if needs_tool_log:
            return None
        tool_log = []
    results = []
    for index, (spec, state) in enumerate(zip(turns, saved, strict=True)):
        if not isinstance(state, dict) or state.get("turn") != index:
            return None
        call_range = _scripted_turn_range(state, index, len(tool_log))
        if call_range is None:
            return None
        start, end = call_range
        checks = spec.get("checks") or []
        receipts_ok = isinstance(((task.get("_eval") or {}).get("receipts")), list)
        tree_checkers = _TREE_CHECKERS - (
            {"office_contains", "receipt_artifact"} if receipts_ok else set()
        )
        needs_tree = any(c.get("type", "answer_contains") in tree_checkers for c in checks)
        tree = state.get("sandbox_tree")
        if tree is None and index == len(turns) - 1:
            tree = rec.get("sandbox_tree")
        if needs_tree and not isinstance(tree, dict):
            return None
        root = rehydrate_tree(tree or {})
        try:
            graded = (
                apply_checkers(
                    {**task, "checkers": checks},
                    _scripted_turn_context(task, state, tool_log, end, root),
                )
                if checks
                else CheckResult(Outcome.PASS, "", {})
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)
        called = {str(call.get("name", "")) for call in tool_log[start:end]}
        missing, carried = expect_tools_verdict(spec, called, graded, tool_log[:start])
        outcome, notes, evidence = graded.outcome, graded.notes, dict(graded.evidence)
        if missing and outcome not in (Outcome.HARNESS_ERROR, Outcome.PENDING_REVIEW):
            outcome = Outcome.FAIL
            notes = f"expected tools not called: {missing} | {notes}"
        if missing:
            evidence["missing_tools"] = missing
        if carried:
            evidence["expect_tools_carried"] = carried
        evidence["turn_tools"] = sorted(called)
        results.append({"turn": index, "outcome": outcome.value, "notes": notes})
    return _combined_turn_result(results)


def _write_rescored_row(campaign_dir: Path, rec: dict, cr, final_outcome: str, why: str) -> None:
    """Persist one re-grade onto its campaign row, preserving the first verdict.

    R-7: a re-grade must never destroy what the first grading recorded. `original`
    is written once, on the first re-score of this row; `rescore.grader` names the
    instrument that produced the current outcome, so a comparison can tell which
    checkers graded each side."""
    if not rec.get("run_id"):
        return
    p = _row_path(campaign_dir, rec["run_id"])
    if not p.exists():
        return
    row = json.loads(p.read_text())
    row.setdefault(
        "original",
        {
            "outcome": row.get("outcome"),
            "notes": row.get("notes"),
            "instrument": row.get("instrument"),
        },
    )
    row["outcome"] = final_outcome
    row["notes"] = f"{cr.notes} [{why}]"
    row["evidence"] = cr.evidence
    row["rescore"] = {"outcome": final_outcome, "grader": instrument_fingerprint()}
    row["rescored_utc"] = dt.datetime.now(dt.UTC).isoformat()
    p.write_text(json.dumps(row, indent=1))


def _resolve_receipts(rec: dict, campaign_dir: Path | None) -> list[dict] | None:
    """A finished row's persisted receipts, resolved to files that still exist. The run
    workspace is cleaned up, but finish() copied every valid receipted artifact into the
    campaign's artifacts/<sha12(run_id)>/. Returns None when the record carries no
    receipts (a sandbox-mode row), so tree-based grading applies as before."""
    rcs = [r for r in ((rec.get("evidence") or {}).get("receipts") or []) if isinstance(r, dict)]
    if not rcs or not campaign_dir or not rec.get("run_id"):
        return None
    keep = campaign_dir / "artifacts" / hashlib.sha256(rec["run_id"].encode()).hexdigest()[:12]
    out = []
    for r in rcs:
        src = Path(r.get("host_path") or "")
        if not src.is_file():
            src = keep / Path(r.get("path") or "").name
        ok = src.is_file() and (
            not r.get("sha256") or hashlib.sha256(src.read_bytes()).hexdigest() == r["sha256"]
        )
        out.append({**r, "host_path": str(src), "valid": True if ok else "artifact missing"})
    return out


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
                # The record names the suite by the checkout that ran it (an older
                # worktree's absolute path). Grade with THIS instrument's copy of the
                # suite, so checker and pattern fixes travel together — re-grading on
                # a stale answer key would silently resurrect the defect.
                here = SUITE_DIR / Path(sp).name
                suites[sp] = {t["id"]: t for t in load_suite(here if here.is_file() else sp)}
            task = (suites.get(sp) or {}).get(rec.get("task_id"))
            if task is None:
                rec["rescore"] = {"outcome": None, "note": "task not found in suite"}
                updated.append(rec)
                continue
            receipts = _resolve_receipts(rec, campaign_dir)
            if receipts is not None:
                task = {**task, "_eval": {"production": True, "receipts": receipts}}
            cr = (
                _rehydrate_scripted_check(rec, task)
                if task.get("turns")
                else _rehydrate_check(rec, task)
            )
            if cr is None:
                rec["rescore"] = {
                    "outcome": None,
                    "note": "recorded evidence incomplete for re-grade",
                }
                updated.append(rec)
                continue
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
            if campaign_dir:
                _write_rescored_row(campaign_dir, rec, cr, final_outcome, why)
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


def _serving_seat(workspace: str, model: str, backend: str | None = None) -> tuple[str, str]:
    """(backend id, native model) production routes this workspace hint to.

    `backend` (a row's `backend` arm override) restricts the ladder to that
    backend: a tag both engines declare is then resolved AS THAT BACKEND serves
    it, so a pinned row's seat evidence is judged against the pinned engine."""
    # Pin shuffle so the first candidate that serves the tag is stable (N-8).
    import random
    from unittest import mock

    reg = _seat_registry()
    with mock.patch.object(random, "shuffle", lambda _xs: None):
        for backend_entry in reg.get_backend_candidates(workspace):
            if backend and backend_entry.id != backend:
                continue
            resolved = backend_entry.resolve_model(model)
            if resolved is not None:
                return backend_entry.id, resolved
    return "", model


def seat_primary(workspace: str, model: str, backend: str | None = None) -> str:
    """The model id production routes this arm to when every backend is
    healthy: the workspace's routing groups in order (then the fallback group),
    backends within a group by descending priority, first one that serves the
    tag — through an alias or directly. backends.yaml shadows several incumbent
    tags onto priority-10 oMLX seats (auto-compliance -> Qwen3.8-27B-oQ4e-mtp),
    so that alias IS the seat. The raw tag on Ollama behind it is the failover,
    a different engine and build: V2 counted 17 failover rows as seat evidence."""
    return _serving_seat(workspace, model, backend)[1]


@functools.lru_cache(maxsize=1)
def _seat_registry() -> BackendRegistry:
    return BackendRegistry(config_path=str(REPO / "config/backends.yaml"))


def served_mismatch(transcript: list, primary: str) -> str | None:
    """Why a pipeline row is not seat evidence, or None. Every model turn must
    carry a served model (a missing trace is unverified, not assumed) and it
    must be the seat's primary; one failover turn taints the whole row."""
    turns = [t for t in transcript if "tool_calls" in t]
    served = [(t.get("served") or {}).get("model") for t in turns]
    if any(m is None for m in served):
        return f"served model unverified on {served.count(None)}/{len(served)} turn(s)"
    off = sorted({m for m in served if m != primary})
    if off:
        return f"pipeline served {off} (seat is {primary}) — failover or drift"
    return None


def backend_catalog() -> frozenset[str]:
    """Ids production accepts as ?model= (preinject._known_backend_models)."""
    cfg = yaml.safe_load((REPO / "config/backends.yaml").read_text()) or {}
    return frozenset(
        m["id"] if isinstance(m, dict) else m
        for b in cfg.get("backends") or []
        for m in b.get("models") or []
        if (m.get("id") if isinstance(m, dict) else m)
    )


# Re-exported so callers and tests that patch this module still reach the portal identity.
OMLX_SERVER_SETTINGS = _omlx_identity.OMLX_SERVER_SETTINGS
OMLX_SETTINGS = _omlx_identity.OMLX_SETTINGS
OMLX_DEFAULT_MODEL_DIR = _omlx_identity.OMLX_DEFAULT_MODEL_DIR
OMLX_IDENTITY_FILES = _omlx_identity.OMLX_IDENTITY_FILES


def backend_engine(backend_id: str) -> str:
    """The engine a backends.yaml entry id names ('ollama', 'omlx', ...)."""
    cfg = yaml.safe_load((REPO / "config/backends.yaml").read_text()) or {}
    for b in cfg.get("backends") or []:
        if b.get("id") == backend_id:
            return str(b.get("type") or "")
    return ""


def omlx_model_dirs() -> list[Path]:
    """Where oMLX looks for model directories: OMLX_MODEL_DIR, else its settings."""
    return _omlx_identity.omlx_model_dirs(
        server_settings=OMLX_SERVER_SETTINGS,
        default_model_dir=OMLX_DEFAULT_MODEL_DIR,
    )


def ollama_content_id(model: str) -> tuple[str, str]:
    """Ollama's manifest digest for a tag (/api/tags), or ("", why it is unobservable)."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as r:
            listed = json.load(r).get("models") or []
    except Exception as e:
        return "", f"Ollama /api/tags unreachable ({e})"
    names = {model, model if ":" in model else f"{model}:latest"}
    for m in listed:
        if {m.get("name"), m.get("model")} & names and m.get("digest"):
            return str(m["digest"]), ""
    return "", f"{model!r} is not in Ollama's /api/tags"


def omlx_content_id(model: str) -> tuple[str, str]:
    """A content id for an oMLX checkpoint, or ("", why it is unobservable): its
    config, tokenizer and template files, each weight file's name and size, and
    its model_settings.json entry (doc: identity)."""
    return _omlx_identity.omlx_content_id(
        model,
        settings=OMLX_SETTINGS,
        server_settings=OMLX_SERVER_SETTINGS,
        default_model_dir=OMLX_DEFAULT_MODEL_DIR,
    )


def observe_identity(backend_id: str, model: str) -> tuple[dict, str]:
    """What serves one model now, observed in the engine's own store: backend id,
    model id and content id, plus why the content could not be observed."""
    engine = backend_engine(backend_id)
    if engine == "ollama":
        content, why = ollama_content_id(model)
    elif engine == "omlx":
        content, why = omlx_content_id(model)
    else:
        content, why = "", f"backend {backend_id!r} has no content identity"
    return {"backend": backend_id, "model": model, "content": content}, why


def served_identity(backend_id: str, model: str) -> dict:
    """What serves one model now (backend, model, content); content is "" when unobservable."""
    return observe_identity(backend_id, model)[0]


def _identity_key(ident: dict) -> tuple[str, str, str, str]:
    """(engine type, base url, model, content). An unknown backend id stays distinct."""
    backend_id = str(ident.get("backend") or "")
    engine, url = "", backend_id
    for backend in _seat_registry().list_backends():
        if backend.id == backend_id:
            engine, url = str(backend.type or ""), str(backend.url or "").rstrip("/")
            break
    return (engine, url, ident.get("model") or "", ident.get("content") or "")


def same_identity(a: dict | None, b: dict | None) -> bool:
    """Same engine, model and content. Two groups on one daemon are one engine."""
    if not a or not b:
        return False
    return _identity_key(a) == _identity_key(b)


def _identity_group(ident: dict) -> str:
    """A backend id as the reuse key sees it: engine type + base url, the
    `same_identity` equality — the serving daemon, not the group label."""
    engine, url, _model, _content = _identity_key(ident)
    return f"{engine}|{url}"


def freeze_identities(frozen: dict, identities: dict) -> list[str]:
    """Freeze each pair's identity on first sight; report every later change."""
    drift = []
    for key in sorted(identities):
        ident = identities[key]
        known = frozen.get(key)
        if not ident.get("content"):  # never freeze what could not be observed
            continue
        if known is None:
            frozen[key] = ident
        elif not same_identity(known, ident):
            drift.append(f"{key}: frozen {known} != now {ident}")
    return drift


def frozen_identity(manifest: dict, r: dict) -> dict | None:
    """The identity preflight froze for this row's (workspace, model) pair."""
    return (manifest.get("identity_map") or {}).get(f"{r['workspace']}|{row_model(r)}")


def row_identity(transcript: list) -> dict | None:
    """What served a row, observed when it finished: backend and model from the
    row's own trace, content from the engine's store, never copied from the freeze.
    Turns served by more than one model make a row whose identity matches nothing."""
    served = {
        ((t.get("served") or {}).get("backend") or "", (t.get("served") or {}).get("model"))
        for t in transcript
        if (t.get("served") or {}).get("model")
    }
    if not served:
        return None
    if len(served) > 1:
        return {"backend": "mixed", "model": repr(sorted(served)), "content": ""}
    return served_identity(*next(iter(served)))


_ROUTED_TASKS: dict[str, set[str]] = {}


def _is_routed_row(r: dict) -> bool:
    """Whether this row's task is graded by the routed_workspace checker — the ONLY
    rows the identity exemption covers (O2 clearance §1): a routing row turns on the
    `auto` workspace and the pipeline serves the ROUTED seat, so the served model is
    another workspace's by design."""
    sp = r.get("suite_path")
    if not sp:
        return False
    if sp not in _ROUTED_TASKS:
        try:
            _ROUTED_TASKS[sp] = {
                t["id"]
                for t in load_suite(sp)
                if any(c.get("type") == "routed_workspace" for c in t.get("checkers") or [])
            }
        except Exception:  # noqa: BLE001 — a missing suite must not kill the arm loop
            _ROUTED_TASKS[sp] = set()
    return r.get("task_id") in _ROUTED_TASKS[sp]


def identity_drift(manifest: dict, r: dict, row: dict) -> str | None:
    """Why the build that served this row is not its pair's frozen one, or None.
    A row with no served turn (an instrument error) has nothing to compare.
    routed_workspace rows are exempt, and only those: the router resolved the turn
    to another workspace's seat on purpose. Two groups on one daemon compare equal."""
    ident = row.get("identity")
    if ENGINE != "pipeline" or not ident:
        return None
    if _is_routed_row(r):
        return None
    key = f"{r['workspace']}|{row_model(r)}"
    if not ident.get("content"):
        return f"{key}: the build serving {ident.get('model')!r} cannot be observed"
    want = frozen_identity(manifest, r)
    return None if same_identity(want, ident) else f"{key}: frozen {want} != served {ident}"


_IMAGE_TASKS: dict[str, set[str]] = {}
#: One-pixel PNG. The pipeline's image gate only checks for an image_url part.
_PROBE_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _task_sends_inline_image(task: dict) -> bool:
    """True when the runner puts an image_url part on this task (user_content)."""
    turns = task.get("turns")
    if turns is not None:
        return any(
            isinstance(turn.get("user"), list)
            and any(
                isinstance(part, dict) and part.get("type") == "image_url" for part in turn["user"]
            )
            for turn in turns
        )
    return bool(task.get("images"))


def _image_task_ids(suite_path: str) -> set[str]:
    """Task ids in this suite whose wire request carries an image. A missing suite has none."""
    if suite_path not in _IMAGE_TASKS:
        try:
            _IMAGE_TASKS[suite_path] = {
                str(task["id"]) for task in load_suite(suite_path) if _task_sends_inline_image(task)
            }
        except (OSError, ValueError):
            _IMAGE_TASKS[suite_path] = set()
    return _IMAGE_TASKS[suite_path]


def _workspace_rows_carry_images(rows: list[dict] | None, workspace: str, model: str) -> bool:
    """True when a row this probe covers will send an image on this workspace and model."""
    if not rows:
        return False
    for row in rows:
        if row.get("workspace") != workspace or row_model(row) != model:
            continue
        suite_path, task_id = row.get("suite_path"), row.get("task_id")
        if suite_path and task_id and str(task_id) in _image_task_ids(str(suite_path)):
            return True
    return False


def _preflight_content(with_image: bool) -> str | list[dict]:
    """The probe user turn. An image workload uses the rows' image_url part shape."""
    text = "Reply with the word ready."
    if not with_image:
        return text
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_PROBE_PNG_B64}"}},
    ]


def preflight_pipeline(workspaces: list[str], model: str, rows: list[dict] | None = None) -> dict:
    """Pipeline mode: the pipeline owns the wire, so the raw transport probe is
    moot. What must hold is that each seat is actually served by the arm's model
    seat (a failover or a third model would make every row describe another
    model). A workspace whose rows attach images is probed with one image, so
    the frozen identity is the route those rows use."""
    findings = []
    if model not in backend_catalog():
        return {
            "model": model,
            "verdict": "REVIEW",
            "findings": [
                f"{model!r} is not a model id in config/backends.yaml: production ignores "
                f"?model= for it and serves the seat instead. Add it to a backend's models."
            ],
        }
    build = deployed_build()
    if not deployed_matches(build):
        findings.append(f"deployed pipeline build {build!r} is not HEAD's portal/: rebuild first")
    findings += service_findings(deployed_services())
    identities: dict[str, dict] = {}
    for ws in workspaces:
        try:
            r = chat(
                ws,
                [
                    {
                        "role": "user",
                        "content": _preflight_content(
                            _workspace_rows_carry_images(rows, ws, model)
                        ),
                    }
                ],
                tools=False,
                harness={"pipeline_model": model},
            )
            served_rec = r.get("served") or {}
            served = served_rec.get("model")
        except Exception as e:
            served, findings = None, [*findings, f"{ws}: request failed: {e}"]
            continue
        routed, primary = _serving_seat(ws, model)
        if served != primary:
            findings.append(
                f"{ws}: pipeline served {served!r}, seat is {primary!r} (arm {model!r})"
            )
        if served:
            # Freeze the workspace route. The trace's group id is not the seat.
            ident, why = observe_identity(routed or (served_rec.get("backend") or ""), served)
            identities[f"{ws}|{model}"] = ident
            if why:
                findings.append(f"{ws}: the build serving {served!r} cannot be observed: {why}")
    return {
        "model": model,
        "verdict": "REVIEW" if findings else "OK",
        "findings": findings,
        "identities": identities,
    }


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


#: A single turn past this many tokens is a runaway on any seat in the fleet.
HARNESS_RUNAWAY_CAP = 32768


def _sampling_for(wsc: dict, repeat: int, overrides: dict | None = None) -> dict:
    """The workspace's OWN sampling block, with a distinct seed per repeat.

    Dimension 8: a temperature-0 pass is not evidence about a product served at
    the lane's declared temperature, and repeats must be three real draws rather
    than three copies of one. All 81 workspaces in portal.yaml declare a
    sampling block; the campaign serves each arm at its workspace's settings.

    Output cap: the workspace's predict_limit when it has one — exactly what
    production sends. Without one, production sends NO cap (oMLX then defaults
    to 262144, Ollama to unbounded), so the old 4096 default manufactured
    TRUNCATED rows production would never produce — worst on thinking arms.
    HARNESS_RUNAWAY_CAP only stops a single turn that has genuinely run away;
    `max_tokens_source` records which cap applied."""
    if ENGINE == "pipeline":
        # The pipeline serves the seat's own sampling and output cap; only an
        # arm's explicit override is sent, and it wins key by key (caller wins).
        forced = (overrides or {}).get("sampling") or {}
        source = "arm_override" if forced.get("max_tokens") is not None else "pipeline"
        return {**forced, "seed": 1000 + repeat, "max_tokens_source": source}
    s = {"max_tokens": HARNESS_RUNAWAY_CAP, **(wsc.get("sampling") or {})}
    s["max_tokens_source"] = (
        "predict_limit" if (wsc.get("sampling") or {}).get("max_tokens") else "harness_runaway_cap"
    )
    # A sampling override (e.g. "seat config vs the vendor's card") REPLACES the
    # workspace's sampling keys, keeping only max_tokens, so seat-only keys like
    # min_p can't leak into a vendor arm. Every row records what it ran with.
    forced = (overrides or {}).get("sampling")
    if forced:
        s = {"max_tokens": s["max_tokens"], "max_tokens_source": s["max_tokens_source"], **forced}
    s["seed"] = 1000 + repeat
    return s


def _served_predict_budget(wsc: dict, sampling: dict) -> int:
    """The effective output cap recorded for this request, including the Pipeline default."""
    if sampling.get("max_tokens") is not None:
        return int(sampling["max_tokens"])
    if ENGINE == "pipeline":
        from tests.wfe.settings_audit import _served_output_budget

        return _served_output_budget(wsc)
    return 2048


@functools.cache
def _baked_params(model: str) -> dict:
    """The Modelfile PARAMETERs Ollama serves for `model` — the value of every
    key /v1 drops. Empty off Ollama (other engines honour the request)."""
    if ENGINE != "ollama":
        return {}
    import urllib.request

    params: dict = {}
    with contextlib.suppress(Exception):
        req = urllib.request.Request(
            f"{OLLAMA}/api/show",
            data=json.dumps({"model": model}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            show = json.load(r)
        for line in (show.get("parameters") or "").splitlines():
            k, _, v = line.strip().partition(" ")
            v = v.strip()
            with contextlib.suppress(ValueError):
                params[k] = float(v) if "." in v else int(v)
    return params


def served_context_limit(workspace: str, model: str, wsc: dict) -> int | None:
    """The context window the row is actually served with, when knowable. An
    Ollama tag bakes it (`num_ctx`, or the `-ctxNk` naming convention); an oMLX
    seat serves its full window, which the harness does not know, so the
    shrinking-prompt check alone applies there."""
    served = seat_primary(workspace, model) if ENGINE == "pipeline" else model
    if ENGINE in ("ollama", "pipeline") and served == model:
        baked = _baked_params(model).get("num_ctx") if ENGINE == "ollama" else None
        if baked:
            return int(baked)
        m = re.search(r"ctx(\d+)k", model)
        if m:
            return int(m.group(1)) * 1024
        return wsc.get("context_limit") if model == wsc.get("model") else None
    return None


def served_temperature(transcript: list) -> float | None:
    """The temperature the pipeline applied to the row's first served turn (its
    `options_applied`), or None when the trace recorded none. Never the plan's value."""
    for t in transcript:
        temp = ((t.get("served") or {}).get("options") or {}).get("temperature")
        if temp is not None:
            return float(temp)
    return None


def arm_served_at_zero(campaign_dir: Path, arm: str) -> bool:
    """True when every row the arm already ran in this campaign (its screen) recorded a served
    temperature of 0. An arm with no recorded temperature is never assumed deterministic."""
    temps = set()
    for f in (campaign_dir / "rows").glob("*.json"):
        with contextlib.suppress(Exception):
            d = json.loads(f.read_text())
            if d.get("arm") == arm and d.get("served_temperature") is not None:
                temps.add(float(d["served_temperature"]))
    return temps == {0.0}


def repeats_policy(campaign_dir: Path, matrix: list[dict], default: int) -> dict[str, int]:
    """arm -> confirm repeats. A workspace's arms get 1 repeat only when EVERY arm in it served
    temperature 0; any other mix gets `default` for all, so a cell never compares unequal repeat
    counts (decision.task_scores needs the same repeats on both sides)."""
    arms_of: dict[str, set[str]] = {}
    for r in matrix:
        arms_of.setdefault(r["workspace"], set()).add(r["arm"])
    out: dict[str, int] = {}
    for arms in arms_of.values():
        n = 1 if all(arm_served_at_zero(campaign_dir, a) for a in arms) else default
        for a in arms:
            out[a] = max(out.get(a, 0), n)
    return out


#: A checker that needs a human to read the answer. Its suite is not objective.
NON_OBJECTIVE_CHECKERS = frozenset({"human_review"})


def _task_checkers(task: dict) -> list[dict]:
    """Every checker spec a task carries, single-turn or per-turn."""
    return list(task.get("checkers") or []) + [
        s for t in task.get("turns") or [] for s in (t.get("checks") or [])
    ]


def suite_is_objective(suite_path: str | Path, cache: dict | None = None) -> bool:
    """True when nothing in the suite waits on a human verdict: only an objective suite
    is worth a second draw."""
    key = str(suite_path)
    if cache is not None and key in cache:
        return cache[key]
    try:
        tasks = load_suite(suite_path)
    except Exception:
        ok = False
    else:
        ok = bool(tasks) and not any(
            s.get("type") in NON_OBJECTIVE_CHECKERS for t in tasks for s in _task_checkers(t)
        )
    if cache is not None:
        cache[key] = ok
    return ok


def _arm_temperature(
    campaign_dir: Path, arm: str, workspace: str, overrides: dict | None
) -> float | None:
    """The temperature this arm is served at: what its recorded rows observed, else the
    arm's own override, else the workspace's declared block. None when unknown."""
    temps = []
    for f in (campaign_dir / "rows").glob("*.json"):
        with contextlib.suppress(Exception):
            d = json.loads(f.read_text())
            if d.get("arm") == arm and d.get("served_temperature") is not None:
                temps.append(float(d["served_temperature"]))
    if temps:
        return max(temps)
    forced = ((overrides or {}).get("sampling") or {}).get("temperature")
    if forced is not None:
        return float(forced)
    with contextlib.suppress(Exception):
        declared = workspace_context(workspace).get("declared_temperature")
        return float(declared) if declared is not None else None
    return None


def realuse_repeats(campaign_dir: Path, matrix: list[dict]) -> dict[str, int]:
    """arm -> repeats under --tier realuse. One draw covers a task; a second is added
    only where the arm can produce a different answer — served temperature above 0 — on
    an objective-check suite. An unrecorded temperature is never assumed deterministic."""
    out: dict[str, int] = {}
    objective: dict[str, bool] = {}
    for r in matrix:
        out.setdefault(r["arm"], 1)
        if out[r["arm"]] > 1 or not suite_is_objective(r["suite_path"], objective):
            continue
        t = _arm_temperature(campaign_dir, r["arm"], r["workspace"], r.get("overrides"))
        if t is None or t > 0:
            out[r["arm"]] = 2
    return out


def degenerate_repeats(wsc: dict, overrides: dict | None = None) -> str | None:
    """A row served at temperature 0 (or with a pinned seed) repeats one draw.
    Recorded so the report never presents n=3 as three independent draws when
    it was one draw counted three times. The ARM's sampling decides: a
    challenger at its card temperature in a temperature-0 workspace is not
    degenerate, and was mis-flagged when only the workspace was read."""
    if wsc.get("pinned_seed") is not None:
        return f"workspace pins seed={wsc['pinned_seed']}"
    forced = (overrides or {}).get("sampling") or {}
    t = forced.get("temperature", wsc.get("declared_temperature"))
    if t is not None and float(t) == 0.0:
        return "served at temperature 0 — repeats are deterministic"
    return None


def _raised_out(e: Exception) -> dict:
    """The row a runner exception leaves: an instrument error, never a model outcome."""
    return {
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
    overrides = row_overrides(r)
    sampling = _sampling_for(wsc, r["repeat"], overrides)
    harness = campaign_harness(wsc, overrides)
    t0 = time.monotonic()
    pipe = ENGINE == "pipeline"
    harness["pipeline_model"] = row_model(r) if pipe else None
    task, wsc, prod = eval_mode.prepare(pipe, r, manifest, task, wsc, harness)
    predict_budget = _served_predict_budget(wsc, sampling)
    # The prompt actually sent: in pipeline mode the pipeline adds the append.
    sent_prompt = wsc["system_prompt_pipeline"] if pipe else wsc["system_prompt"]
    try:
        out = run_task(
            r["workspace"] if pipe else row_model(r),
            sent_prompt,
            task,
            sandbox,
            max_turns,
            budget_s,
            use_tools=prod["use_tools"] if prod else not task.get("no_tools"),
            harness=dict(harness),
            sampling=sampling,
            tool_surface=wsc.get("tool_surface"),
            context_limit=served_context_limit(r["workspace"], row_model(r), wsc),
        )
    except Exception as e:
        _log(campaign_dir, f"  runner raised: {type(e).__name__}: {e}")
        out = _raised_out(e)
    out = eval_mode.finish(prod, out, campaign_dir, r)
    mismatch = (
        served_mismatch(
            out.get("transcript") or [],
            seat_primary(r["workspace"], row_model(r), overrides.get("backend")),
        )
        if pipe and out.get("transcript")
        else None
    )
    if mismatch:
        # Not seat evidence; BLOCKED rows are re-offered by --rerun-failed.
        out = {
            **out,
            "outcome": Outcome.BLOCKED.value,
            "notes": f"{SEAT_BLOCK}{mismatch} | {out.get('notes', '')}",
        }
    econ = dict(out.get("economics") or {})
    econ["cold_load"] = cold
    row = ResultRow(
        run_id=r["run_id"],
        campaign_id=manifest["campaign_id"],
        stage="full",
        instrument=row_instrument(manifest.get("instrument") or instrument_fingerprint(), out),
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
        prompt_sha=sha12(sent_prompt),
        tool_surface=wsc.get("tool_surface") or TOOL_NAMES,
        tool_surface_proxy=bool(wsc.get("tool_surface_proxy", True)),
        harness=dict(harness),
        sampling=sampling,
        predict_budget=predict_budget,
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
    row["turn_results"] = out.get("turn_results", [])
    row["repeat_degeneracy"] = degenerate_repeats(wsc, overrides)
    row["served_temperature"] = served_temperature(out.get("transcript") or [])
    row["repeats_planned"] = sum(
        1
        for m in manifest["rows"]
        if (m["workspace"], m["arm"], m["suite"], m["task_id"])
        == (r["workspace"], r["arm"], r["suite"], r["task_id"])
    )
    row["model"] = row_model(r)
    row["overrides"] = overrides
    row["identity"] = row_identity(out.get("transcript") or [])
    # What the engine was ASKED for but silently drops (runner.DELIVERABLE_KEYS) and, on
    # Ollama, what the tag bakes; else a row's `sampling` claims values never served.
    row["sampling_undelivered"] = undeliverable_keys(sampling)
    row["baked_params"] = _baked_params(row_model(r))
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
                "system_prompt": sent_prompt,
                "persona_slug": wsc.get("persona_slug"),
                "instruction": task.get("instruction")
                or (task.get("turns") or [{}])[0].get("user", ""),
                "harness": dict(harness),
                "sampling": sampling,
                "predict_budget": predict_budget,
                "tool_surface": wsc.get("tool_surface"),
                "outcome": out["outcome"],
                "notes": out["notes"],
                "evidence": out["evidence"],
                "final_text": out.get("final_text", ""),
                "turn_results": out.get("turn_results", []),
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
    excluded = set(setup_exclusions(campaign_dir))
    arm_rows = [r for r in manifest["rows"] if r["arm"] == arm]
    # excluded.json is the source of truth: every state of that workspace stays unrun.
    runnable = [r for r in arm_rows if str(r.get("workspace") or "") not in excluded]
    todo = [r for r in runnable if r.get("state") == "PENDING" or r.get("state") in retry_states]
    offered = {r["run_id"] for r in todo}
    stale_block = [
        r
        for r in runnable
        if r["run_id"] not in offered
        and r.get("state") == Outcome.BLOCKED.value
        and str(r.get("note") or "").startswith(_PREFLIGHT_BLOCK)
    ]
    if not todo and not stale_block:
        _log(campaign_dir, f"arm {arm}: nothing pending")
        return [], {"arm": arm, "ran": 0}

    # An override that depends on a key this engine silently drops would run
    # hours of rows identical to the seat arm and report them as the card arm.
    # Refuse it before the first request (runner.DELIVERABLE_KEYS; on Ollama
    # such a key has to be baked into a tag, which is then its own arm).
    dropped = undeliverable_keys((row_overrides(todo[0]) if todo else {}).get("sampling") or {})
    if dropped:
        note = (
            f"override sampling keys {dropped} are silently dropped by the {ENGINE} "
            "/v1 endpoint — bake them into a tag (its own arm) or serve on oMLX"
        )
        for r in todo:
            r["state"] = Outcome.BLOCKED.value
            r["note"] = note
        save_manifest(campaign_dir, manifest)
        _log(campaign_dir, f"arm {arm}: BLOCKED — {note}")
        return [], {"arm": arm, "ran": 0, "blocked": len(todo)}

    # Preflight probes only workspaces the canary did not exclude: a probe of an excluded
    # workspace failing would otherwise block the healthy ones (sol 10-31).
    if not runnable:
        return [], {"arm": arm, "ran": 0}
    model = row_model(runnable[0])
    pf = _arm_preflight(campaign_dir, manifest, runnable, model, force_preflight)
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


def _arm_preflight(campaign_dir: Path, manifest: dict, arm_rows: list, model: str, force) -> dict:
    """The arm's preflight. In pipeline mode it also freezes each (workspace, model)
    pair's identity on first sight, and a later change becomes a finding, so the
    arm is blocked instead of measured on another build (doc: identity)."""
    if ENGINE != "pipeline":
        return preflight_arm(campaign_dir, model, force)
    pf = preflight_pipeline(sorted({r["workspace"] for r in arm_rows}), model, arm_rows)
    drift = freeze_identities(manifest.setdefault("identity_map", {}), pf.get("identities") or {})
    save_manifest(campaign_dir, manifest)
    if not drift:
        return pf
    found = [*(pf.get("findings") or []), *(f"IDENTITY DRIFT: {d}" for d in drift)]
    return {**pf, "verdict": "REVIEW", "findings": found}


def _quarantine(campaign_dir: Path, manifest: dict, r: dict, row: dict, note: str) -> None:
    """Keep the row's evidence but mark it BLOCKED, so it never enters a comparison."""
    row = {**row, "outcome": Outcome.BLOCKED.value, "notes": note}
    _row_path(campaign_dir, r["run_id"]).write_text(json.dumps(row, indent=1))
    r["state"] = Outcome.BLOCKED.value
    save_manifest(campaign_dir, manifest)


#: Consecutive HARNESS_ERROR rows that stop an arm (the instrument, not the model).
MAX_CONSECUTIVE_HARNESS_ERRORS = 3
_RECENT: dict[str, list[str]] = {}

#: Rows of one task kind after which an arm that is failing wholesale is halted.
HALT_AFTER_ROWS = 4
_KIND_ROWS: dict[tuple[str, str], list[dict]] = {}


def task_kind(task: dict) -> str:
    """The halt group: explicit `halt_kind`, else its `kind`, else id without index."""
    return task.get("halt_kind") or task.get("kind") or re.sub(r"(-\d+[a-z]?)+$", "", task["id"])


def hop_limited(row: dict) -> bool:
    """The model kept calling tools and never answered within the turn limit."""
    return any("exhausted_turns" in t for t in row.get("transcript") or [])


def kind_halt_reason(
    arm: str,
    kind: str,
    row: dict,
    n: int = HALT_AFTER_ROWS,
    tools: bool = True,
    tier: str = "confirm",
) -> str | None:
    """Keep ordinary kind gates, while realuse retains only its HARNESS_ERROR stop."""
    rows = _KIND_ROWS.setdefault((arm, kind), [])
    rows.append(
        {
            "outcome": row["outcome"],
            "tool_calls": row.get("tool_calls") or 0,
            "hop": hop_limited(row),
        }
    )
    if len(rows) < n:
        return None
    if tier == "realuse":
        return (
            "HARNESS_ERROR row"
            if any(x["outcome"] == Outcome.HARNESS_ERROR.value for x in rows)
            else None
        )
    passes = sum(x["outcome"] == Outcome.PASS.value for x in rows)
    if _at_or_below_pass_floor(passes, len(rows), n=n):
        return f"pass rate {passes}/{len(rows)} <= 1/{n}"
    if tools and not any(x["tool_calls"] for x in rows):
        return f"0 tool calls on all {len(rows)} rows"
    if any(x["outcome"] == Outcome.HARNESS_ERROR.value for x in rows):
        return "HARNESS_ERROR row"
    if any(x["hop"] for x in rows):
        return "hop-limit row"
    return None


def _at_or_below_pass_floor(
    passes: int, graded_rows: int, *, floor_rate: float | None = None, n: int = HALT_AFTER_ROWS
) -> bool:
    rate = floor_rate if floor_rate is not None else 1 / n
    return graded_rows > 0 and passes / graded_rows <= rate


def _halt_arm(
    campaign_dir: Path,
    arm: str,
    task: dict,
    row: dict,
    halt: bool,
    tier: str = "confirm",
) -> str | None:
    """Judge the row's task kind; on a halt, log it and return "<kind>: <reason>"."""
    kind = task_kind(task)
    # wfe_math_20261018a: every reasoning/math arm halted on "0 tool calls" — its tasks are
    # no_tools, so a call is never possible.
    why = kind_halt_reason(arm, kind, row, tools=not task.get("no_tools"), tier=tier)
    if not (why and halt):
        return None
    _log(campaign_dir, f"arm {arm}: HALTED — {kind}: {why}")
    log_halt(campaign_dir, arm, kind, why)
    return f"{kind}: {why}"


def log_halt(campaign_dir: Path, arm: str, kind: str, reason: str) -> None:
    """Append `HALT <arm> <kind> <reason>` to arm_exits.log (the supervisor's log when it set one)."""
    path = Path(os.environ.get("WFE_EXIT_LOG") or campaign_dir / "arm_exits.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(f"HALT {arm} {kind} {reason}\n")


def record_arm_stop(campaign_dir: Path, arm: str, reason: str) -> None:
    """Append the stop to arm_stops.jsonl, the record campaign_finish() reads after this process is gone."""
    path = Path(campaign_dir) / "arm_stops.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps({"arm": arm, "reason": reason}) + "\n")


def record_campaign_stop(campaign_dir: Path, manifest: dict, reason: str, kind: str) -> None:
    """Persist the campaign-level stop receipt used by --finish and report."""
    manifest.setdefault(
        "campaign_stop",
        {"kind": kind, "reason": reason, "utc": dt.datetime.now(dt.UTC).isoformat()},
    )
    save_manifest(campaign_dir, manifest)


def _campaign_row_budget(
    campaign_dir: Path, manifest: dict, deadline_epoch: float | None, requested: int
) -> int | None:
    if deadline_epoch is None:
        return requested
    remaining = deadline_epoch - time.time()
    if remaining < 1:
        record_campaign_stop(campaign_dir, manifest, "time cap", "time_cap")
        return None
    return min(requested, max(1, int(remaining)))


def arm_stop_reason(
    arm: str, row: dict, campaign_dir: Path | None = None, manifest: dict | None = None, r=None
) -> str | None:
    """Why the arm must stop after this row (a failover stops it at once), or None.
    Instrument or identity drift observed after a row quarantines that row and
    stops the arm."""
    if manifest and campaign_dir is not None and r is not None:
        for label, drift in (
            ("INSTRUMENT DRIFT", instrument_drift(manifest)),
            ("IDENTITY DRIFT", identity_drift(manifest, r, row)),
        ):
            if drift:
                _quarantine(campaign_dir, manifest, r, row, f"{label}: {drift}")
                return drift
    if str(row.get("notes") or "").startswith(SEAT_BLOCK):
        return str(row["notes"])[:200]
    recent = _RECENT.setdefault(arm, [])
    recent.append(row["outcome"])
    tail = recent[-MAX_CONSECUTIVE_HARNESS_ERRORS:]
    if len(tail) == MAX_CONSECUTIVE_HARNESS_ERRORS and set(tail) == {Outcome.HARNESS_ERROR.value}:
        return f"{MAX_CONSECUTIVE_HARNESS_ERRORS} consecutive HARNESS_ERROR rows: {row.get('notes', '')[:160]}"
    return None


#: CLI exit codes (tests/wfe/run_arm.py records them in arm_exits.log).
EXIT_OK, EXIT_STOPPED, EXIT_BLOCKED, EXIT_NO_SELECTION, EXIT_INCOMPLETE = 0, 5, 6, 7, 8
#: An arm halted on a task kind that was failing wholesale (see kind_halt_reason).
EXIT_HALT = 9
#: wfe_campaign.sh exits 10 when every row is BLOCKED, PENDING, or MISSING.
EXIT_NOTHING_MEASURED = 10
EXIT_REHEARSAL_FAILED = 11
_UNMEASURED_ROW_STATES = frozenset({"BLOCKED", "PENDING", "MISSING"})


def exit_status(outs: list[dict], arms: list[str]) -> int:
    """0 ran or nothing left to run; 5 an arm stopped; 6 an arm was blocked; 7 none selected;
    9 an arm halted on a failing task kind."""
    if not arms:
        return EXIT_NO_SELECTION
    if any(o.get("halted") for o in outs):
        return EXIT_HALT
    if any(o.get("blocked") for o in outs):
        return EXIT_BLOCKED
    return EXIT_STOPPED if any(o.get("stopped") for o in outs) else EXIT_OK


def _row_block_reason(row: dict) -> str:
    note = str(row.get("note") or row.get("notes") or "").strip()
    if note.startswith(_PREFLIGHT_BLOCK):
        note = note[len(_PREFLIGHT_BLOCK) :].strip()
    return " ".join(note.split())


def dominant_block_reason(rows: list[dict]) -> str:
    """The most common block note, or the most common row state when none is set."""
    counts: dict[str, int] = {}
    for row in rows:
        reason = _row_block_reason(row)
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    if counts:
        return max(counts, key=lambda reason: counts[reason])
    states: dict[str, int] = {}
    for row in rows:
        state = str(row.get("state") or "PENDING")
        states[state] = states.get(state, 0) + 1
    if not states:
        return "no rows"
    state = max(states, key=lambda name: states[name])
    return f"{states[state]} {state}"


def campaign_measurement_exit(rows: list[dict]) -> int:
    """0 when any row was measured; else 10 and one NOTHING MEASURED line."""
    measured = any(str(row.get("state") or "PENDING") not in _UNMEASURED_ROW_STATES for row in rows)
    if measured:
        return EXIT_OK
    print(f"NOTHING MEASURED: {dominant_block_reason(rows)}")
    return EXIT_NOTHING_MEASURED


def archive_drifted_campaign(cid: str) -> None:
    """A drifted campaign with zero measured rows is archived aside so the same id
    reopens fresh; one with measured rows stays (data must not be mixed) and the
    printed line is the refusal remedy the job's receipt shows."""
    directory = CAMPAIGNS / cid
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    drift = instrument_drift(manifest)
    if not drift:
        return
    rows = manifest.get("rows") or []
    measured = sum(
        1 for r in rows if str(r.get("state") or "PENDING") not in _UNMEASURED_ROW_STATES
    )
    if measured:
        print(
            f"CAMPAIGN {cid}: instrument drift with {measured} measured row(s); not archived — "
            "data must not be mixed. Open a new campaign id in the job spec (or archive the "
            "campaign dir manually), then requeue."
        )
        return
    from portal.modules.orchestration.escalate import archive_stale

    dest = archive_stale(directory)
    print(f"archived drifted campaign {directory.name} -> {dest.name}: {drift}")


def _recorded_stops(campaign_dir: Path) -> list[dict]:
    path = Path(campaign_dir) / "arm_stops.jsonl"
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text().splitlines():
        with contextlib.suppress(Exception):
            if line.strip():
                out.append(json.loads(line))
    return out


def _recorded_halts(campaign_dir: Path) -> list[str]:
    """The `HALT <arm> <kind> <reason>` lines; run_arm.py's exit lines don't start with HALT."""
    path = Path(campaign_dir) / "arm_exits.log"
    if not path.is_file():
        return []
    return [ln.strip() for ln in path.read_text().splitlines() if ln.startswith("HALT ")]


_TIMING_PHASES = ("block_setup", "model_prepare", "rows", "release")


def _pilot_floor_summary(manifest: dict) -> dict | None:
    execution = manifest.get("execution") or {}
    if not execution.get("pilot_tasks") or execution.get("rehearsal"):
        return None
    rows = manifest.get("rows") or []
    if not rows or any(
        str(row.get("state") or "PENDING") in _UNMEASURED_ROW_STATES for row in rows
    ):
        return None
    floor_rate = float(execution.get("pilot_floor_rate", 1 / HALT_AFTER_ROWS))
    arm_results = []
    for arm in sorted({str(row["arm"]) for row in rows if row.get("arm")}):
        arm_rows = [row for row in rows if row.get("arm") == arm]
        graded = [row for row in arm_rows if str(row.get("state")) in MODEL_QUALITY_OUTCOMES]
        passes = sum(str(row.get("state")) == Outcome.PASS.value for row in graded)
        if not graded:
            return None
        rate = passes / len(graded)
        arm_results.append(
            {
                "arm": arm,
                "passes": passes,
                "graded_rows": len(graded),
                "rate": rate,
                "below_floor": _at_or_below_pass_floor(passes, len(graded), floor_rate=floor_rate),
            }
        )
    return {
        "floor_rate": floor_rate,
        "arms": arm_results,
        "no_signal": bool(arm_results) and all(arm["below_floor"] for arm in arm_results),
    }


def pilot_floor_check(campaign_id: str, campaigns: Path = CAMPAIGNS) -> dict | None:
    path = campaigns / f"{campaign_id}_pilot" / "manifest.json"
    try:
        return _pilot_floor_summary(json.loads(path.read_text()))
    except (OSError, ValueError):
        return None


def _timing_totals(timing: dict) -> tuple[float, float, float]:
    model_s = float(timing.get("model_s") or 0)
    wall_s = float(timing.get("wall_s") or 0)
    harness_s = wall_s - model_s if "wall_s" in timing else float(timing.get("harness_s") or 0)
    return harness_s, model_s, harness_s / wall_s if wall_s else 0.0


def _timing_unattributed_s(timing: dict) -> float:
    named_s = sum(
        float((block.get("phases") or {}).get(f"{phase}_s") or 0)
        for block in timing.get("blocks") or []
        for phase in _TIMING_PHASES
    )
    wall_s = float(timing["wall_s"]) if "wall_s" in timing else named_s
    return wall_s - named_s


def _rehearsal_failures(execution: dict, timing: dict) -> list[str]:
    failures = []
    max_phase_s = float(execution.get("rehearsal_max_phase_s", 120))
    max_overhead = float(execution.get("rehearsal_max_overhead", 0.25))
    blocks = timing.get("blocks") or []
    for arm in sorted({str(block.get("arm")) for block in blocks}):
        count = len({block.get("block_id") for block in blocks if block.get("arm") == arm})
        if count < 2:
            failures.append(f"arm {arm} ran {count} block(s); 2 required")
    for block in blocks:
        for phase in _TIMING_PHASES:
            seconds = float((block.get("phases") or {}).get(f"{phase}_s") or 0)
            if phase != "rows" and seconds > max_phase_s:
                failures.append(
                    f"{phase} arm={block.get('arm')} s={seconds:.3f} > {max_phase_s:.3f}"
                )
    _harness_s, _model_s, ratio = _timing_totals(timing)
    if not blocks:
        failures.append("no interleaved block timing recorded")
    if ratio > max_overhead:
        failures.append(f"overhead ratio={ratio:.3f} > {max_overhead:.3f}")
    unattributed_s = _timing_unattributed_s(timing)
    if unattributed_s > max_phase_s:
        failures.append(f"unattributed_s={unattributed_s:.3f} > {max_phase_s:.3f}")
    return failures


def _print_timing_report(execution: dict) -> tuple[float, float, float]:
    timing = execution.get("timing") or {}
    blocks = timing.get("blocks") or []
    if blocks:
        print("PHASE TABLE block arm block_setup_s model_prepare_s rows_s release_s")
        for block in blocks:
            phases = block.get("phases") or {}
            values = " ".join(f"{phases.get(f'{phase}_s', 0):.3f}" for phase in _TIMING_PHASES)
            print(f"PHASE TABLE {block.get('block_id')} {block.get('arm')} {values}")
    harness_s, model_s, ratio = _timing_totals(timing)
    print(f"OVERHEAD harness_s={harness_s:.3f} model_s={model_s:.3f} ratio={ratio:.3f}")
    print(f"unattributed_s={_timing_unattributed_s(timing):.3f}")
    return harness_s, model_s, ratio


def campaign_finish(campaign_dir: Path, campaign_id: str) -> int:
    """Print the final `CAMPAIGN <id>: ...` line and exit for the matrix that was run.

    wfe_campaign.sh's last call: a stop (instrument drift, seat loss) is 5,
    nothing measured 10, rows left PENDING with no stop record 8, a completed
    matrix 0. A halt is a result, not a failure: it completes its arm early and
    is summarised on the line. The line is the job receipt's reason."""
    manifest_path = Path(campaign_dir) / "manifest.json"
    rows: list[dict] = []
    campaign_stop = None
    manifest = {}
    if manifest_path.is_file():
        with contextlib.suppress(Exception):
            manifest = json.loads(manifest_path.read_text())
            rows = manifest.get("rows") or []
            campaign_stop = manifest.get("campaign_stop")
    execution = manifest.get("execution") or {}
    timing = execution.get("timing") or {}
    _print_timing_report(execution)
    states = [str(r.get("state") or "PENDING") for r in rows]
    done = sum(1 for s in states if s not in _UNMEASURED_ROW_STATES)
    left = sum(1 for s in states if s in ("PENDING", "MISSING"))
    blocked = sum(1 for s in states if s == "BLOCKED")
    stops, halts = _recorded_stops(campaign_dir), _recorded_halts(campaign_dir)
    verdict, reason, code = "complete", "all rows measured", EXIT_OK
    if campaign_stop:
        verdict, code = "stopped", EXIT_STOPPED
        reason = str(campaign_stop.get("reason") or "campaign stopped")
    elif stops:
        verdict, code = "stopped", EXIT_STOPPED
        reason = str(stops[-1].get("reason") or "arm stopped")
    elif done == 0:
        dominant = dominant_block_reason(rows)
        print(f"NOTHING MEASURED: {dominant}")
        verdict, code = "stopped", EXIT_NOTHING_MEASURED
        reason = f"nothing measured: {dominant}"
    elif halts:
        reason = f"{len(halts)} halt(s): {halts[-1][len('HALT ') :]}"
    elif left:
        verdict, code = "stopped", EXIT_INCOMPLETE
        reason = f"{left} row(s) left PENDING with no stop recorded"
    elif blocked:
        reason = f"{blocked} row(s) BLOCKED, rest measured"
    pilot = _pilot_floor_summary(manifest)
    if verdict == "complete" and pilot and pilot["no_signal"]:
        counts = ", ".join(
            f"{arm['arm']}={arm['passes']}/{arm['graded_rows']}" for arm in pilot["arms"]
        )
        verdict = "NO_SIGNAL"
        reason = f"all arms below floor {pilot['floor_rate']:.0%}: {counts}"
    rehearsal = _rehearsal_failures(execution, timing) if execution.get("rehearsal") else []
    if verdict == "complete" and rehearsal:
        verdict, code = "failed", EXIT_REHEARSAL_FAILED
        reason = "rehearsal gate: " + "; ".join(rehearsal)
    print(f"CAMPAIGN {campaign_id}: {verdict} ({reason}) rows {done}/{len(rows)}")
    return code


def _manifest_row_result(campaign_dir: Path, row: dict) -> dict:
    """Read a persisted task-run, or synthesize its terminal manifest outcome."""
    path = _row_path(campaign_dir, row["run_id"])
    if path.exists():
        return json.loads(path.read_text())
    return {
        "suite": row["suite"],
        "task_id": row["task_id"],
        "repeat": row["repeat"],
        "outcome": row.get("state", "PENDING"),
    }


def _curtail_id(workspace: str, arm: str) -> str:
    return f"{workspace}|{arm}"


def _incomplete_incumbent_reason(
    baseline_rows: list[dict], expected: set, repeats: int
) -> str | None:
    baseline_expected = {(r["suite"], r["task_id"]) for r in baseline_rows}
    if baseline_expected != expected:
        return f"incumbent task set differs ({len(baseline_expected)} vs {len(expected)})"
    if any(r.get("state") in ("PENDING", "SKIPPED_DECIDED") for r in baseline_rows):
        return "incumbent rows are incomplete when challenger starts"
    want = set(range(repeats))
    for task in expected:
        got = [r["repeat"] for r in baseline_rows if (r["suite"], r["task_id"]) == task]
        if set(got) != want or len(got) != repeats:
            return f"incumbent repeats incomplete for {task[0]}/{task[1]}: {sorted(got)} of {sorted(want)}"
    return None


def _evaluate_curtailment(
    campaign_dir: Path, baseline_rows: list[dict], cand_rows: list[dict], expected: set
):
    """Score completed tasks across tiers; gradeable partial tasks remain future work."""
    repeats = max((r["repeat"] for r in [*baseline_rows, *cand_rows]), default=0) + 1
    completed, fixed_excluded = set(), set()
    for task_key in expected:
        task_rows = [r for r in cand_rows if (r["suite"], r["task_id"]) == task_key]
        states = [r.get("state", "PENDING") for r in task_rows]
        if states and all(s not in ("PENDING", "SKIPPED_DECIDED") for s in states):
            completed.add(task_key)
        elif any(
            s not in ("PENDING", "SKIPPED_DECIDED") and s not in MODEL_QUALITY_OUTCOMES
            for s in states
        ):
            fixed_excluded.add(task_key)
    inc_results = [_manifest_row_result(campaign_dir, r) for r in baseline_rows]
    cand_results = [
        _manifest_row_result(campaign_dir, r)
        for r in cand_rows
        if (r["suite"], r["task_id"]) in completed | fixed_excluded
        and r.get("state") not in ("PENDING", "SKIPPED_DECIDED")
    ]
    arguable = set()
    suite_paths = {r.get("suite_path") for r in cand_rows if r.get("suite_path")}
    for suite_path in suite_paths:
        arguable.update(
            (Path(suite_path).stem, task["id"])
            for task in load_suite(suite_path)
            if task.get("arguable")
        )
    execution = load_manifest(campaign_dir).get("execution") or {}
    return decision.curtail(
        inc_results,
        cand_results,
        expected,
        completed,
        repeats=repeats,
        arguable=arguable,
        fixed_excluded=fixed_excluded,
        non_inferiority_margin=execution.get("non_inferiority_margin") or 0.0,
    )


def _bypass_curtailment(rec_id, workspace, arm, incumbent, after_task, reason):
    return {
        "id": rec_id,
        "workspace": workspace,
        "arm": arm,
        "incumbent": incumbent,
        "state": "BYPASSED_INCOMPLETE_INCUMBENT",
        "reason": reason,
        "after_task": after_task,
        "rows_saved": 0,
    }


def _curtail_workspace(
    campaign_dir: Path, manifest: dict, arm: str, workspace: str, after_task: str = "campaign start"
) -> dict | None:
    """Curtail confirm rows against a complete incumbent, reusing observed screen rows."""
    workspace_rows = [
        r
        for r in manifest["rows"]
        if r.get("workspace") == workspace and r.get("arm") and r.get("arm_role")
    ]
    confirm_rows = [r for r in workspace_rows if r.get("tier", "confirm") == "confirm"]
    cand_rows = [r for r in confirm_rows if r.get("arm") == arm]
    if not cand_rows or cand_rows[0].get("arm_role") != "challenger":
        return None
    pending = [r for r in cand_rows if r.get("state") == "PENDING"]
    if not pending:
        return None
    incumbents = {r["arm"] for r in confirm_rows if r["arm_role"] == "incumbent"}
    if len(incumbents) != 1:
        return None
    incumbent = next(iter(incumbents))
    expected = {(r["suite"], r["task_id"]) for r in cand_rows}
    baseline_rows = [
        r
        for r in workspace_rows
        if r["arm"] == incumbent and (r["suite"], r["task_id"]) in expected
    ]
    repeats = (
        max(
            (r["repeat"] for r in workspace_rows if (r["suite"], r["task_id"]) in expected),
            default=0,
        )
        + 1
    )
    cand_rows = [
        r for r in workspace_rows if r["arm"] == arm and (r["suite"], r["task_id"]) in expected
    ]
    curtailments = manifest.setdefault("curtailments", [])
    rec_id = _curtail_id(workspace, arm)
    existing = next((c for c in curtailments if c.get("id") == rec_id), None)
    if existing and existing.get("state") == "CURTAILED":
        return existing

    bypass_reason = _incomplete_incumbent_reason(baseline_rows, expected, repeats)
    if bypass_reason:
        record = _bypass_curtailment(rec_id, workspace, arm, incumbent, after_task, bypass_reason)
    else:
        cell = _evaluate_curtailment(campaign_dir, baseline_rows, cand_rows, expected)
        remaining = [r for r in confirm_rows if r.get("arm") == arm and r.get("state") == "PENDING"]
        if cell is None or not remaining:
            return None
        summary = {
            key: getattr(cell, key)
            for key in ("verdict", "reason", "n", "wins", "losses", "ties", "p")
        }
        record = {
            "id": rec_id,
            "workspace": workspace,
            "arm": arm,
            "incumbent": incumbent,
            "state": "CURTAILED",
            "verdict": cell.verdict,
            "reason": cell.reason,
            "after_task": after_task,
            "tasks_compared": cell.n,
            "tasks_remaining": len({(r["suite"], r["task_id"]) for r in remaining}),
            "rows_saved": len(remaining),
            "cell": summary,
        }
        for row in remaining:
            row.update(
                state="SKIPPED_DECIDED",
                note=f"curtailed: {cell.verdict}; {cell.reason}",
                curtailment_id=rec_id,
            )
        _log(
            campaign_dir,
            f"arm {arm} [{workspace}]: curtailed after {after_task} — {cell.verdict}; saved {len(remaining)} row(s)",
        )

    if existing:
        existing.clear()
        existing.update(record)
    else:
        curtailments.append(record)
    save_manifest(campaign_dir, manifest)
    if record["state"] == "BYPASSED_INCOMPLETE_INCUMBENT":
        _log(campaign_dir, f"arm {arm} [{workspace}]: curtailment bypassed — {record['reason']}")
    return record


def _resume_curtailed_rows(campaign_dir: Path, manifest: dict, arm: str) -> None:
    """The explicit --no-curtail override re-offers rows skipped by an earlier run."""
    resumed = []
    for record in list(manifest.get("curtailments", [])):
        if record.get("arm") != arm or record.get("state") != "CURTAILED":
            continue
        for row in manifest["rows"]:
            if (
                row.get("curtailment_id") == record.get("id")
                and row.get("state") == "SKIPPED_DECIDED"
            ):
                row["state"] = "PENDING"
                row.pop("note", None)
                row.pop("curtailment_id", None)
        resumed.append({**record, "state": "RESUMED_NO_CURTAIL"})
        manifest["curtailments"].remove(record)
    if resumed:
        manifest.setdefault("curtailment_history", []).extend(resumed)
        save_manifest(campaign_dir, manifest)


def completion_problems(campaign_dir: Path) -> list[str]:
    """Every expected row must have a persisted model-quality result under the baseline."""
    m = load_manifest(campaign_dir)
    base = (m.get("instrument") or {}).get("fingerprint")
    ok = {o.value for o in MODEL_QUALITY_OUTCOMES}
    valid_curtailments = {
        c.get("id") for c in m.get("curtailments", []) if c.get("state") == "CURTAILED"
    }
    excluded = setup_exclusions(campaign_dir)
    out = []
    for r in m["rows"]:
        if r.get("state") == "SKIPPED_DECIDED" and r.get("curtailment_id") in valid_curtailments:
            continue
        # Every row of a canary-excluded workspace, whatever its stored state (a resumed
        # HARNESS_ERROR row is withheld from execution too), is not owed a result.
        if r.get("state") == Outcome.EXCLUDED_SETUP.value or r.get("workspace") in excluded:
            continue
        p = _row_path(campaign_dir, r["run_id"])
        row = json.loads(p.read_text()) if p.exists() else {"outcome": "no result"}
        reused = bool(row.get("reused_from"))
        if row.get("outcome") not in ok:
            out.append(f"{r['run_id']}: {row.get('outcome')}")
        elif base and (row.get("instrument") or {}).get("fingerprint") != base and not reused:
            # A reused incumbent row was graded under the earlier campaign's
            # instrument fingerprint. The reuse key already matched; it is present.
            out.append(f"{r['run_id']}: measured under another instrument")
    return out


def _prepare_arm_curtailment(campaign_dir: Path, manifest: dict, arm: str, enabled: bool) -> None:
    if not enabled:
        _resume_curtailed_rows(campaign_dir, manifest, arm)
        return
    workspaces = {
        r["workspace"] for r in manifest["rows"] if r.get("arm") == arm and r.get("workspace")
    }
    for workspace in sorted(workspaces):
        _curtail_workspace(campaign_dir, manifest, arm, workspace)


def _curtail_after_task(campaign_dir: Path, manifest: dict, arm: str, row: dict, enabled: bool):
    if not enabled or row.get("tier") != "confirm" or row.get("arm_role") != "challenger":
        return
    task_rows = [
        m
        for m in manifest["rows"]
        if (m.get("workspace"), m.get("arm"), m.get("suite"), m.get("task_id"))
        == (row["workspace"], arm, row["suite"], row["task_id"])
    ]
    finished = all(m.get("state") not in ("PENDING", "SKIPPED_DECIDED") for m in task_rows)
    if task_rows and finished:
        _curtail_workspace(
            campaign_dir,
            manifest,
            arm,
            row["workspace"],
            after_task=f"{row['suite']}/{row['task_id']}",
        )


def _cmd_verify_complete(campaign_dir: Path) -> int:
    problems = completion_problems(campaign_dir)
    for p in problems[:50]:
        print(f"  INCOMPLETE {p}")
    print(f"{len(problems)} problem(s) in {campaign_dir.name}")
    return EXIT_INCOMPLETE if problems else EXIT_OK


def _prepare_arm_resources(
    campaign_dir: Path, arm: str, todo: list[dict], resident_workspaces: set[str] | None = None
) -> tuple[str, bool]:
    model = row_model(todo[0])
    todo_workspaces = {str(row.get("workspace") or "") for row in todo}
    keep_resident = bool(todo_workspaces) and todo_workspaces.issubset(resident_workspaces or set())
    if keep_resident:
        _log(campaign_dir, f"arm {arm}: retaining load-guard-fit resident model {model}")
        return model, True
    seat = seat_primary(todo[0]["workspace"], model) if ENGINE == "pipeline" else model
    evicted = drain_others(model if seat == model else "")
    if evicted:
        _log(campaign_dir, f"arm {arm}: drained {len(evicted)} resident model(s): {evicted}")
    if ENGINE == "omlx" or (ENGINE == "pipeline" and model not in model_sizes()):
        _log(campaign_dir, f"arm {arm}: {drain_omlx()}")
    return model, False


def _order_pending_rows(todo: list[dict], manifest: dict) -> list[dict]:
    reused_tasks = {
        (r.get("workspace"), r.get("arm"), r.get("suite"), r.get("task_id"))
        for r in manifest.get("rows") or []
        if r.get("reused_from")
    }
    return [
        row
        for _index, row in sorted(
            enumerate(todo),
            key=lambda item: (
                item[1].get("repeat", 0),
                (
                    item[1].get("workspace"),
                    item[1].get("arm"),
                    item[1].get("suite"),
                    item[1].get("task_id"),
                )
                in reused_tasks,
                item[0],
            ),
        )
    ]


def _interleave_blocks(
    rows: list[dict], arms: list[str], block_size: int | dict, retry_states: set | None = None
) -> list[list[dict]]:
    """Group runnable task/repeat rows across arms, then divide them into pair blocks."""
    runnable = {"PENDING", *(retry_states or set())}
    groups: dict[tuple, dict[str, list[str]]] = {}
    for row in rows:
        stale_preflight = row.get("state") == Outcome.BLOCKED.value and str(
            row.get("note") or ""
        ).startswith(_PREFLIGHT_BLOCK)
        if row.get("arm") not in arms or (row.get("state") not in runnable and not stale_preflight):
            continue
        key = (row["workspace"], row["suite"], row["task_id"], row["repeat"])
        groups.setdefault(key, {}).setdefault(row["arm"], []).append(row["run_id"])
    units = [
        {"key": key, "run_ids": groups[key]}
        for key in sorted(groups, key=lambda item: (item[3], item[0], item[1], item[2]))
    ]
    by_workspace: dict[str, list[dict]] = {}
    for unit in units:
        by_workspace.setdefault(unit["key"][0], []).append(unit)
    blocks = []
    for workspace, workspace_units in by_workspace.items():
        size = block_size.get(workspace, 4) if isinstance(block_size, dict) else block_size
        blocks.extend(
            workspace_units[index : index + size] for index in range(0, len(workspace_units), size)
        )
    return blocks


def _campaign_deadline(options: dict) -> float:
    started = os.environ.get("WFE_CAMPAIGN_START_EPOCH")
    try:
        start_epoch = float(started) if started else time.time()
    except ValueError:
        start_epoch = time.time()
    return start_epoch + options["max_minutes"] * 60


def _finish_arm(
    campaign_dir, arm, model, tally, elapsed_start, notify, stop, halted, ran, keep_resident=False
):
    if stop:
        record_arm_stop(campaign_dir, arm, stop)
    if keep_resident and not stop and not halted:
        _log(campaign_dir, f"arm {arm}: retained resident model {model} for next interleave block")
    elif not drain_model(model):
        _log(campaign_dir, f"arm {arm}: WARNING — still resident after {DRAIN_TIMEOUT_S}s")
    elapsed = round(time.monotonic() - elapsed_start)
    summary = f"{arm}: {tally} in {elapsed}s"
    _log(campaign_dir, f"arm complete — {summary}")
    if notify:
        _notify("test_summary", f"WFE arm done ({elapsed}s)\n{arm}\n{tally}", {"arm": arm})
    return {
        "arm": arm,
        "ran": ran,
        "tally": tally,
        "elapsed_s": elapsed,
        "stopped": stop,
        "halted": halted,
    }


def _arm_todo(
    campaign_dir: Path,
    manifest: dict,
    arm: str,
    force_preflight: bool,
    notify: bool,
    rerun_failed: bool,
    fresh_incumbent: bool,
    curtail: bool,
    only_run_ids: set[str] | None = None,
) -> tuple[list[dict], dict | None, list[str]]:
    """Pending rows for one arm, after a fresh release, curtailment, or a row copy.

    The third value is the run ids copied from earlier campaigns. An early dict
    means the arm should return that and not start a model. Release happens
    before curtailment so a fresh incumbent is incomplete when the challenger
    is considered."""
    if fresh_incumbent:
        release_reused_incumbents(campaign_dir, manifest)
    _prepare_arm_curtailment(campaign_dir, manifest, arm, curtail)
    retry_states = (
        {Outcome.HARNESS_ERROR.value, Outcome.TOOL_ERROR.value, Outcome.BLOCKED.value}
        if rerun_failed
        else set()
    )
    todo, early = _rows_to_run(campaign_dir, manifest, arm, retry_states, force_preflight, notify)
    if early is not None:
        return todo, early, []
    if only_run_ids is not None:
        todo = [row for row in todo if row["run_id"] in only_run_ids]
    reused = []
    if not fresh_incumbent:
        reused.extend(reuse_incumbent_rows(campaign_dir, manifest, todo))
    reused.extend(reuse_screen_rows(campaign_dir, manifest, todo))
    done = set(reused)
    todo = [r for r in todo if r["run_id"] not in done]
    todo = _order_pending_rows(todo, manifest)
    if todo:
        return todo, None, reused
    _log(campaign_dir, f"arm {arm}: nothing left to run ({len(reused)} row(s) reused)")
    return [], {"arm": arm, "ran": 0, "reused": len(reused)}, reused


def _record_block_timing(
    campaign_dir: Path,
    arm: str,
    block_id: str | None,
    phases: dict[str, float],
    model_s: float,
    first_row_started_monotonic: float | None = None,
) -> None:
    manifest = load_manifest(campaign_dir)
    execution = manifest.setdefault("execution", {})
    timing = execution.setdefault("timing", {"blocks": []})
    blocks = timing.setdefault("blocks", [])
    ident = block_id or f"{arm}-{len(blocks) + 1}"
    phases = {f"{name}_s": round(max(0.0, phases.get(name, 0.0)), 3) for name in _TIMING_PHASES}
    elapsed = sum(phases.values())
    harness_s = max(0.0, elapsed - model_s)
    record = {
        "block_id": ident,
        "arm": arm,
        "phases": phases,
        "harness_s": round(harness_s, 3),
        "model_s": round(model_s, 3),
    }
    if first_row_started_monotonic is not None:
        record["first_row_started_monotonic"] = first_row_started_monotonic
    blocks[:] = [row for row in blocks if (row.get("block_id"), row.get("arm")) != (ident, arm)]
    blocks.append(record)
    timing["harness_s"] = round(sum(row["harness_s"] for row in blocks), 3)
    timing["model_s"] = round(sum(row["model_s"] for row in blocks), 3)
    total = timing["harness_s"] + timing["model_s"]
    timing["ratio"] = round(timing["harness_s"] / total, 4) if total else 0.0
    save_manifest(campaign_dir, manifest)
    for phase, seconds in phases.items():
        name = phase.removesuffix("_s")
        line = f"PHASE {name} arm={arm} s={seconds:.3f}"
        print(line, flush=True)
        with (campaign_dir / "progress.log").open("a", encoding="utf-8") as log:
            log.write(line + "\n")


def _execute_arm_rows(
    campaign_dir: Path,
    manifest: dict,
    arm: str,
    todo: list[dict],
    reused: list[str],
    model: str,
    keep_resident: bool,
    max_turns: int,
    budget_s: int,
    debug_dir: Path | None,
    notify: bool,
    halt: bool,
    curtail: bool,
    deadline_epoch: float | None,
) -> tuple[dict, dict[str, float], float, float | None]:
    _log(campaign_dir, f"arm {arm}: {len(todo)} runs pending")
    if notify:
        _notify("test_start", f"WFE arm started: {arm}\n{len(todo)} task-runs")
    ws_cache: dict[tuple, dict] = {}
    suite_cache: dict[str, dict] = {}
    tally: dict = {}
    ran = model_s = 0
    first_row_started_monotonic: float | None = None
    stop = halted = None
    t_arm = t_rows = time.monotonic()
    for i, r in enumerate(todo, 1):
        row_budget = _campaign_row_budget(campaign_dir, manifest, deadline_epoch, budget_s)
        if row_budget is None:
            break
        if r.get("state") == "SKIPPED_DECIDED":
            continue
        ws_key = (r["workspace"], row_overrides(r).get("persona"))
        if ws_key not in ws_cache:
            ws_cache[ws_key] = workspace_context(*ws_key)
        if r["suite_path"] not in suite_cache:
            suite_cache[r["suite_path"]] = {t["id"]: t for t in load_suite(r["suite_path"])}
        task = suite_cache[r["suite_path"]].get(r["task_id"])
        if task is None:
            r["state"] = Outcome.HARNESS_ERROR.value
            r["note"] = "task id not present in suite"
            save_manifest(campaign_dir, manifest)
            continue
        _log(campaign_dir, f"  [{i}/{len(todo)}] {r['run_id']}")
        first_row_started_monotonic = first_row_started_monotonic or time.monotonic()
        row = run_row(
            campaign_dir,
            manifest,
            r,
            ws_cache[ws_key],
            task,
            max_turns,
            row_budget,
            debug_dir,
            cold=(i == 1),
        )
        ran += 1
        row_wall = (row.get("economics") or {}).get("wall_s")
        if isinstance(row_wall, (int, float)):
            model_s += max(0.0, float(row_wall))
        r["state"] = row["outcome"]
        tally[row["outcome"]] = tally.get(row["outcome"], 0) + 1
        save_manifest(campaign_dir, manifest)
        _log(
            campaign_dir,
            f"      -> {row['outcome']} turns={row['turns']} tools={row['tool_calls']} "
            f"errs={row['tool_errors']} {(row.get('economics') or {}).get('wall_s')}s",
        )
        stop = arm_stop_reason(arm, row, campaign_dir, manifest, r)
        if stop:
            _log(campaign_dir, f"arm {arm}: STOPPED — {stop}")
            break
        if halted := _halt_arm(campaign_dir, arm, task, row, halt, tier=r.get("tier", "confirm")):
            break
        _curtail_after_task(campaign_dir, manifest, arm, r, curtail)
    rows_s = time.monotonic() - t_rows
    t_release = time.monotonic()
    out = _finish_arm(
        campaign_dir, arm, model, tally, t_arm, notify, stop, halted, ran, keep_resident
    )
    release_s = time.monotonic() - t_release
    out["reused"] = len(reused)
    out["stopped"] = (load_manifest(campaign_dir).get("campaign_stop") or {}).get("reason")
    return out, {"rows": rows_s, "release": release_s}, model_s, first_row_started_monotonic


def execute_arm(
    campaign_dir: Path,
    arm: str,
    max_turns: int,
    budget_s: int,
    debug_dir: Path | None,
    force_preflight: bool,
    notify: bool,
    rerun_failed: bool = False,
    halt: bool = True,
    curtail: bool = True,
    fresh_incumbent: bool = False,
    only_run_ids: set[str] | None = None,
    deadline_epoch: float | None = None,
    timing: bool = False,
    block_id: str | None = None,
) -> dict:
    """Run every pending row for one arm in its own worker process."""
    manifest = load_manifest(campaign_dir)
    if _campaign_row_budget(campaign_dir, manifest, deadline_epoch, budget_s) is None:
        return {"arm": arm, "ran": 0, "stopped": "time cap"}
    t_setup = time.monotonic()
    apply_setup_exclusions(campaign_dir, manifest)
    todo, early, reused = _arm_todo(
        campaign_dir,
        manifest,
        arm,
        force_preflight,
        notify,
        rerun_failed,
        fresh_incumbent,
        curtail,
        only_run_ids,
    )
    phases = {"block_setup": time.monotonic() - t_setup, "model_prepare": 0.0}
    if early is not None:
        if timing:
            _record_block_timing(campaign_dir, arm, block_id, phases, 0.0)
        return early
    t_prepare = time.monotonic()
    model, keep_resident = _prepare_arm_resources(
        campaign_dir,
        arm,
        todo,
        set((manifest.get("execution") or {}).get("resident_fit_workspaces") or []),
    )
    phases["model_prepare"] = time.monotonic() - t_prepare
    out, tail_phases, model_s, first_row_started_monotonic = _execute_arm_rows(
        campaign_dir,
        manifest,
        arm,
        todo,
        reused,
        model,
        keep_resident,
        max_turns,
        budget_s,
        debug_dir,
        notify,
        halt,
        curtail,
        deadline_epoch,
    )
    phases.update(tail_phases)
    if timing:
        _record_block_timing(
            campaign_dir, arm, block_id, phases, model_s, first_row_started_monotonic
        )
    return out


def _interleaved_comparisons(manifest: dict, arms: list[str]) -> list[dict]:
    rows = [
        row
        for row in manifest["rows"]
        if row.get("arm") in arms and row.get("tier", "confirm") == "confirm"
    ]
    comparisons = []
    workspaces = sorted({row["workspace"] for row in rows})
    for workspace in workspaces:
        scoped = [row for row in rows if row["workspace"] == workspace]
        incumbents = sorted({r["arm"] for r in scoped if r.get("arm_role") == "incumbent"})
        if len(incumbents) != 1:
            continue
        incumbent = incumbents[0]
        candidates = sorted({r["arm"] for r in scoped if r.get("arm_role") == "challenger"})
        for candidate in candidates:
            expected = {(r["suite"], r["task_id"]) for r in scoped if r.get("arm") == candidate}
            if expected:
                comparisons.append(
                    {
                        "workspace": workspace,
                        "incumbent": incumbent,
                        "candidate": candidate,
                        "expected": expected,
                    }
                )
    return comparisons


def _interleaved_cell(
    campaign_dir: Path, manifest: dict, spec: dict, margin: float
) -> decision.Cell | None:
    ws, inc, cand, expected = (
        spec["workspace"],
        spec["incumbent"],
        spec["candidate"],
        spec["expected"],
    )
    rows = [
        r
        for r in manifest["rows"]
        if r.get("workspace") == ws
        and r.get("arm") in (inc, cand)
        and (r["suite"], r["task_id"]) in expected
        and r.get("tier", "confirm") == "confirm"
    ]
    repeats = max((r["repeat"] for r in rows), default=0) + 1
    task_rows: dict[tuple[str, str], list[dict]] = {task: [] for task in expected}
    for row in rows:
        task_rows[(row["suite"], row["task_id"])].append(row)
    completed = {
        task
        for task, group in task_rows.items()
        if group and all(r.get("state") not in ("PENDING", "SKIPPED_DECIDED") for r in group)
    }
    results = {inc: [], cand: []}
    for row in rows:
        if row.get("state") in ("PENDING", "SKIPPED_DECIDED"):
            continue
        results[row["arm"]].append(_manifest_row_result(campaign_dir, row))
    arguable = set()
    for suite_path in {r.get("suite_path") for r in rows if r.get("suite_path")}:
        arguable.update(
            (Path(suite_path).stem, task["id"])
            for task in load_suite(suite_path)
            if task.get("arguable")
        )
    return decision.curtail_interleaved(
        results[inc],
        results[cand],
        expected,
        completed,
        repeats=repeats,
        arguable=arguable,
        non_inferiority_margin=margin,
    )


def _record_interleaved_decision(
    campaign_dir: Path, manifest: dict, spec: dict, cell: decision.Cell
) -> bool:
    remaining = [
        r
        for r in manifest["rows"]
        if r.get("workspace") == spec["workspace"]
        and r.get("arm") == spec["candidate"]
        and r.get("state") == "PENDING"
        and r.get("tier", "confirm") == "confirm"
    ]
    if not remaining:
        return False
    record = {
        "id": _curtail_id(spec["workspace"], spec["candidate"]),
        "workspace": spec["workspace"],
        "arm": spec["candidate"],
        "incumbent": spec["incumbent"],
        "state": "CURTAILED",
        "verdict": cell.verdict,
        "reason": cell.reason,
        "after_task": "paired interleave block",
        "tasks_compared": cell.n,
        "tasks_remaining": len({(r["suite"], r["task_id"]) for r in remaining}),
        "rows_saved": len(remaining),
        "cell": {
            key: getattr(cell, key)
            for key in ("verdict", "reason", "n", "wins", "losses", "ties", "p")
        },
    }
    for row in remaining:
        row.update(
            state="SKIPPED_DECIDED",
            note=f"curtailed: {cell.verdict}; {cell.reason}",
            curtailment_id=record["id"],
        )
    curtailments = manifest.setdefault("curtailments", [])
    existing = next((r for r in curtailments if r.get("id") == record["id"]), None)
    if existing:
        existing.clear()
        existing.update(record)
    else:
        curtailments.append(record)
    save_manifest(campaign_dir, manifest)
    _log(
        campaign_dir,
        f"{spec['candidate']} [{spec['workspace']}]: interleaved decision "
        f"{cell.verdict} after {cell.n} paired task(s); saved {len(remaining)} row(s)",
    )
    return True


def _evaluate_interleaved(campaign_dir: Path, manifest: dict, arms: list[str], margin: float):
    specs = _interleaved_comparisons(manifest, arms)
    new_records = []
    for spec in specs:
        existing = next(
            (
                r
                for r in manifest.get("curtailments", [])
                if r.get("id") == _curtail_id(spec["workspace"], spec["candidate"])
                and r.get("state") == "CURTAILED"
            ),
            None,
        )
        if existing:
            continue
        cell = _interleaved_cell(campaign_dir, manifest, spec, margin)
        if cell and _record_interleaved_decision(campaign_dir, manifest, spec, cell):
            new_records.append({**spec, "verdict": cell.verdict})
    if not specs:
        return new_records, False
    settled = all(
        any(
            record.get("id") == _curtail_id(spec["workspace"], spec["candidate"])
            and record.get("state") == "CURTAILED"
            for record in manifest.get("curtailments", [])
        )
        or not any(
            r.get("workspace") == spec["workspace"]
            and r.get("arm") == spec["candidate"]
            and r.get("state") == "PENDING"
            and r.get("tier", "confirm") == "confirm"
            for r in manifest["rows"]
        )
        for spec in specs
    )
    early = any(
        r.get("id") == _curtail_id(spec["workspace"], spec["candidate"])
        and r.get("state") == "CURTAILED"
        for spec in specs
        for r in manifest.get("curtailments", [])
    )
    paired_cells = {
        (spec["workspace"], arm) for spec in specs for arm in (spec["incumbent"], spec["candidate"])
    }
    all_cells = {
        (r["workspace"], r["arm"])
        for r in manifest["rows"]
        if r.get("tier", "confirm") == "confirm"
    }
    if settled and early and all_cells <= paired_cells:
        reasons = [f"{r['candidate']}={r['verdict']}" for r in new_records]
        for row in manifest["rows"]:
            if (
                (row.get("workspace"), row.get("arm")) in paired_cells
                and row.get("state") == "PENDING"
                and row.get("tier", "confirm") == "confirm"
            ):
                row.update(state="SKIPPED_DECIDED", note="all paired comparisons are decided")
        reason = "decision: " + (", ".join(reasons) or "all comparisons invariant")
        record_campaign_stop(campaign_dir, manifest, reason, "decision")
        return new_records, True
    save_manifest(campaign_dir, manifest)
    return new_records, False


def _interleaved_block_id(block: list[dict]) -> str:
    return sha12(
        "|".join(
            sorted(run_id for unit in block for ids in unit["run_ids"].values() for run_id in ids)
        )
    )


def _record_parent_block_gap(
    campaign_dir: Path, block_id: str, previous_block_end: float, block_end: float
) -> None:
    manifest = load_manifest(campaign_dir)
    execution = manifest.setdefault("execution", {})
    timing = execution.setdefault("timing", {"blocks": []})
    records = [record for record in timing.get("blocks", []) if record.get("block_id") == block_id]
    starts = [
        float(start)
        for record in records
        if (start := record.pop("first_row_started_monotonic", None)) is not None
    ]
    next_event = min(starts) if starts else block_end
    gap_before_s = round(max(0.0, next_event - previous_block_end), 3)
    for record in records:
        record["gap_before_s"] = gap_before_s
    save_manifest(campaign_dir, manifest)


def _run_interleaved_block(
    campaign_dir: Path, block: list[dict], arms: list[str], args, budget: int
):
    outs = []
    block_id = _interleaved_block_id(block)
    for arm in arms:
        run_ids = {run_id for unit in block for run_id in unit["run_ids"].get(arm, [])}
        if not run_ids:
            continue
        if not ollama_reachable():
            record_arm_stop(campaign_dir, arm, "Ollama unreachable")
            outs.append({"stopped": "Ollama unreachable"})
            break
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="wfe_interleave_", delete=False
        ) as run_file:
            run_file.write("\n".join(sorted(run_ids)))
            run_ids_path = Path(run_file.name)
        try:
            rc = subprocess.run(
                _block_worker_command(campaign_dir, arm, run_ids_path, block_id, args, budget),
                cwd=REPO,
                stdin=subprocess.DEVNULL,
                check=False,
            ).returncode
        finally:
            run_ids_path.unlink(missing_ok=True)
        if rc == 6:
            outs.append({"blocked": True})
        elif rc == 9:
            outs.append({"halted": "arm worker halted"})
            break
        elif rc == EXIT_STOPPED:
            outs.append({"stopped": "arm worker stopped"})
            break
        elif rc != 0:
            reason = f"arm worker exited {rc}"
            record_arm_stop(campaign_dir, arm, reason)
            outs.append({"stopped": reason})
            break
        else:
            outs.append({"arm": arm, "ran": len(run_ids)})
    return outs


def _run_timed_interleaved_block(
    campaign_dir: Path,
    block: list[dict],
    run_arms: list[str],
    args,
    budget: int,
    previous_block_end: float,
) -> tuple[list[dict], float]:
    block_id = _interleaved_block_id(block)
    outs = _run_interleaved_block(campaign_dir, block, run_arms, args, budget)
    block_end = time.monotonic()
    _record_parent_block_gap(campaign_dir, block_id, previous_block_end, block_end)
    return outs, block_end


def _block_worker_command(
    campaign_dir: Path, arm: str, run_ids_path: Path, block_id: str, args, budget: int
):
    command = [
        sys.executable,
        "-m",
        "tests.wfe.campaign",
        "--campaign-id",
        campaign_dir.name,
        "--plan",
        args.plan,
        "--tier",
        args.tier,
        "--arm",
        arm,
        "--run-ids-file",
        str(run_ids_path),
        "--block-id",
        block_id,
        "--block-worker",
        "--budget-s",
        str(budget),
        "--max-turns",
        str(args.max_turns),
    ]
    for flag, enabled in (
        ("--all-suites", args.all_suites),
        ("--notify", args.notify),
        ("--no-halt", args.no_halt),
        ("--no-curtail", args.no_curtail),
        ("--rerun-failed", args.rerun_failed),
        ("--fresh-incumbent", args.fresh_incumbent),
    ):
        if enabled:
            command.append(flag)
    if args.repeats is not None:
        command.extend(("--repeats", str(args.repeats)))
    if getattr(args, "pilot", None) is not None:
        command.extend(("--pilot", str(args.pilot)))
    if getattr(args, "rehearse", False):
        command.append("--rehearse")
    if args.debug_dir:
        command.extend(("--debug-dir", str(args.debug_dir)))
    if args.force:
        command.append("--force")
    return command


def _finish_interleaved_timing(
    campaign_dir: Path, campaign_started: float, last_block_end: float | None
) -> None:
    manifest = load_manifest(campaign_dir)
    execution = manifest.setdefault("execution", {})
    timing = execution.setdefault("timing", {"blocks": []})
    if last_block_end is not None:
        timing["wall_s"] = round(last_block_end - campaign_started, 3)
        timing["model_s"] = round(
            sum(float(block.get("model_s") or 0) for block in timing["blocks"]), 3
        )
        timing["harness_s"] = round(timing["wall_s"] - timing["model_s"], 3)
        timing["ratio"] = (
            round(timing["harness_s"] / timing["wall_s"], 4) if timing["wall_s"] else 0.0
        )
    save_manifest(campaign_dir, manifest)


def _run_interleaved_campaign(
    campaign_dir: Path, arms: list[str], args, options: dict, deadline_epoch: float
) -> list[dict]:
    campaign_started = time.monotonic()
    previous_block_end = campaign_started
    last_block_end = None
    roles = {r["arm"]: r.get("arm_role") for r in load_manifest(campaign_dir)["rows"]}
    run_arms = sorted(arms, key=lambda arm: (roles.get(arm) != "incumbent", arms.index(arm)))
    if args.no_curtail:
        manifest = load_manifest(campaign_dir)
        for arm in run_arms:
            _resume_curtailed_rows(campaign_dir, manifest, arm)
        for row in manifest["rows"]:
            if row.get("arm") in run_arms and row.get("state") == "SKIPPED_DECIDED":
                row.update(state="PENDING")
                row.pop("note", None)
                row.pop("curtailment_id", None)
        save_manifest(campaign_dir, manifest)
    retry = (
        {Outcome.HARNESS_ERROR.value, Outcome.TOOL_ERROR.value, Outcome.BLOCKED.value}
        if args.rerun_failed
        else set()
    )
    outs = []
    while True:
        manifest = load_manifest(campaign_dir)
        if manifest.get("campaign_stop"):
            break
        blocks = _interleave_blocks(
            manifest["rows"],
            run_arms,
            options.get("interleave_block_by_workspace") or options["interleave_block"],
            retry,
        )
        if not blocks:
            break
        block = blocks[0]
        row_count = sum(len(ids) for unit in block for ids in unit["run_ids"].values())
        remaining = deadline_epoch - time.time()
        if remaining < max(row_count, 1):
            record_campaign_stop(campaign_dir, manifest, "time cap", "time_cap")
            outs.append({"stopped": "time cap"})
            break
        budget = min(args.budget_s, max(1, int(remaining / max(row_count, 1))))
        block_outs, previous_block_end = _run_timed_interleaved_block(
            campaign_dir, block, run_arms, args, budget, previous_block_end
        )
        last_block_end = previous_block_end
        outs.extend(block_outs)
        if any(out.get("stopped") or out.get("halted") or out.get("blocked") for out in block_outs):
            break
        if not args.no_curtail and options.get("pilot_tasks") is None:
            manifest = load_manifest(campaign_dir)
            _new, stopped = _evaluate_interleaved(
                campaign_dir, manifest, run_arms, options.get("non_inferiority_margin") or 0.0
            )
            if stopped:
                outs.append({"stopped": "decision"})
                break
    _finish_interleaved_timing(campaign_dir, campaign_started, last_block_end)
    return outs


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


def run_judge(campaign_dir: Path) -> None:
    """Blind pairwise judge over the pairs both arms now hold (reported, never gated)."""
    from tests.wfe import judge

    try:
        res = judge.judge_campaign(campaign_dir)
    except Exception as e:  # noqa: BLE001 - a judge outage is not a campaign failure
        print(f"judge: skipped — {e}", file=sys.stderr)
        return
    print(
        f"judge: {res['judged']} pair(s) judged, {res['skipped']} already recorded, "
        f"{res['errors']} error(s) ({res['model']} @ {res['url']})"
    )


def _maybe_judge(campaign_dir: Path, enabled: bool) -> None:
    if enabled:
        run_judge(campaign_dir)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(REPO / "tests/wfe/workloads.yaml"))
    ap.add_argument(
        "--tier",
        choices=("screen", "confirm", "realuse"),
        default="confirm",
        help="screen: marked tasks once; confirm: every task at --repeats; realuse: every "
        "task once, twice only where an arm above temperature 0 can differ",
    )
    ap.add_argument("--advance", type=Path, help="advance.yaml from report --screen-out")
    ap.add_argument("--campaign-id", help="create or continue this campaign")
    ap.add_argument("--run-ids-file", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--block-worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--block-id", help=argparse.SUPPRESS)
    ap.add_argument("--pilot-floor-check", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--arms-file", type=Path, help=argparse.SUPPRESS)
    ap.add_argument(
        "--pilot",
        type=int,
        nargs="?",
        const=6,
        help="run this many one-draw tasks per arm in an interleaved <id>_pilot campaign (default 6)",
    )
    ap.add_argument(
        "--rehearse", action="store_true", help="run two spread tasks per arm for a timing gate"
    )
    ap.add_argument("--arm", help="run exactly one model tag (one arm per process)")
    ap.add_argument("--workspace", help="restrict to one workspace")
    ap.add_argument("--suite", help="restrict to one suite")
    ap.add_argument("--task", help="restrict to one task id")
    ap.add_argument(
        "--no-halt",
        action="store_true",
        help="do not halt an arm whose task kind is failing wholesale (exit 9)",
    )
    ap.add_argument(
        "--repeats",
        type=int,
        help=f"repeats per task (confirm default: {DEFAULT_REPEATS}, or 1 for an arm whose "
        "screen rows were served at temperature 0; screen always runs 1)",
    )
    ap.add_argument(
        "--all-suites",
        action="store_true",
        help="every suite, not just home + discovery — the variety of work a model may face",
    )
    ap.add_argument("--append", action="store_true", help="add rows to a live campaign")
    ap.add_argument(
        "--judge",
        action="store_true",
        help="after the arms, blind-judge every task pair both arms hold a row for "
        "(WFE_JUDGE_MODEL or tests/wfe/judge.yaml; local endpoint; reported, not gated)",
    )
    ap.add_argument(
        "--no-curtail",
        action="store_true",
        help="run every confirm row even when the incumbent comparison is already decided",
    )
    ap.add_argument(
        "--rerun-failed", action="store_true", help="also redo HARNESS_ERROR/TOOL_ERROR rows"
    )
    ap.add_argument(
        "--fresh-incumbent",
        action="store_true",
        help="rerun incumbent rows instead of reusing an earlier campaign's matching rows",
    )
    ap.add_argument(
        "--reuse-screen",
        action="append",
        default=[],
        metavar="CAMPAIGN_ID",
        help="reuse matching graded challenger rows from this campaign (repeatable)",
    )
    ap.add_argument("--max-turns", type=int, default=16)
    ap.add_argument("--budget-s", type=int, default=1800, help="per task-run wall budget")
    ap.add_argument("--debug-dir", type=Path, help="write a full per-run .debug.jsonl per arm")
    ap.add_argument("--rescore", type=Path, help="re-grade a debug dir; no model calls")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="one task end to end, full record printed")
    ap.add_argument("--list-arms", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument(
        "--require-measured",
        action="store_true",
        help="exit 10 and name the dominant block reason when no row was measured",
    )
    ap.add_argument(
        "--finish",
        action="store_true",
        help="wfe_campaign.sh's last call: print `CAMPAIGN <id>: complete|stopped "
        "(reason) rows done/total` and exit 0 complete, 5 stopped, 10 nothing "
        "measured, 8 incomplete",
    )
    ap.add_argument("--watch", action="store_true", help="live view of a running campaign")
    ap.add_argument(
        "--verify-complete",
        action="store_true",
        help="exit 0 only if every expected row has a model-quality result under the baseline",
    )
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


def _cmd_require_measured(campaign_dir: Path) -> int:
    path = campaign_dir / "manifest.json"
    if not path.is_file():
        print("NOTHING MEASURED: no manifest")
        return EXIT_NOTHING_MEASURED
    rows = json.loads(path.read_text()).get("rows") or []
    return campaign_measurement_exit(rows)


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
    matrix = expand_matrix(
        plan, 1, args.all_suites, args.arm, args.suite, args.task, args.workspace
    )
    if not matrix:
        print("smoke: no matching row", file=sys.stderr)
        return 2
    r = matrix[0]
    rec = gate_controls([r], "smoke")
    d = CAMPAIGNS / (args.campaign_id or "wfe_smoke")
    (d / "rows").mkdir(parents=True, exist_ok=True)
    (d / "preflight").mkdir(parents=True, exist_ok=True)
    keep_receipt(d, rec)
    manifest = {"campaign_id": d.name, "env": env_fingerprint(OLLAMA), "rows": [r]}
    manifest["instrument"] = instrument_fingerprint()
    save_manifest(d, manifest)
    pf = (
        preflight_pipeline([r["workspace"]], row_model(r), [r])
        if ENGINE == "pipeline"
        else preflight_arm(d, row_model(r), force=True)
    )
    print(json.dumps(pf, indent=1))
    if pf.get("verdict") != "OK" and not args.force:
        print("\nsmoke: preflight REVIEW — fix or pass --force", file=sys.stderr)
        return 1
    wsc = workspace_context(r["workspace"], row_overrides(r).get("persona"))
    task = {t["id"]: t for t in load_suite(r["suite_path"])}[r["task_id"]]
    debug = args.debug_dir or (d / "debug")
    row = run_row(d, manifest, r, wsc, task, args.max_turns, args.budget_s, debug, cold=True)
    print("\n=== SMOKE RESULT ===")
    print(json.dumps({k: v for k, v in row.items() if k != "transcript"}, indent=1)[:4000])
    print(f"\ndebug record: {debug}")
    print(f"outcome: {row['outcome']}  ({row['notes'][:200]})")
    return 0 if row["outcome"] in (Outcome.PASS.value, Outcome.FAIL.value) else 1


def _cmd_dry_run(matrix: list[dict], repeats: int | dict[str, int]) -> int:
    import collections

    c = collections.Counter(r["arm"] for r in matrix)
    shown = repeats if isinstance(repeats, int) else "per arm"
    print(f"matrix rows: {len(matrix)}   arms: {len(c)}   repeats: {shown}")
    for a, n in sorted(c.items()):
        rep = f"   repeats {repeats[a]}" if isinstance(repeats, dict) else ""
        print(f"  {n:>4}  {a}{rep}")
    head = _git("rev-parse", "HEAD").strip()
    for workspace in sorted({row["workspace"] for row in matrix}):
        try:
            context = workspace_context(workspace)
        except (KeyError, TypeError):
            print(f"  workspace {workspace}: settings unavailable config_fingerprint=unavailable")
            continue
        fingerprint = (pipeline_at(head, workspace) or {}).get("workspace", "unavailable")
        print(
            f"  workspace {workspace}: model={context.get('model')} "
            f"context={context.get('context_limit')} predict={context.get('sampling', {}).get('max_tokens')} "
            f"config_fingerprint={fingerprint}"
        )
    try:
        rec = gate_controls(matrix, "dry-run")
    except SystemExit as e:
        print(f"controls: FAIL\n{e}")
        return 4
    print(f"controls: PASS ({len(rec['suites'])} suite(s), {rec['tasks']} task(s))")
    return 0


def _cmd_list_arms(plan: Path, all_suites: bool) -> int:
    import collections

    c = collections.Counter(r["arm"] for r in expand_matrix(plan, 1, all_suites))
    for a, n in sorted(c.items()):
        print(f"{n:>4}  {a}")
    return 0


def _print_preflight(
    i: int,
    total: int,
    arm: str,
    res: dict,
    elapsed: float,
    budgets: list[tuple[str, str, int]],
) -> None:
    """One arm's preflight verdict and everything that qualified it."""
    print(f"[{i}/{total}] {str(res.get('verdict')):6s} {round(elapsed, 1):7.1f}s  {arm}")
    for arm_id, workspace, budget in budgets:
        print(f"          predict_budget: {arm_id} [{workspace}] {budget}")
    for f in res.get("findings") or []:
        print(f"          FINDING: {f}")
    for n in res.get("notes") or []:
        print(f"          note: {n}")


def _cmd_preflight(campaign_dir: Path, force: bool) -> int:
    """Probe every arm's transport before the sweep starts.

    An arm the harness cannot talk to yields no rows at all — and in an
    unattended sweep that is discovered at hour forty, not hour zero. Twenty
    minutes up front clears the whole roster, and every OK verdict is cached, so
    the sweep does not pay for the probe twice. Exit 1 if any arm needs review."""
    drain_others("")
    sizes = model_sizes()
    manifest = load_manifest(campaign_dir)
    # Preflight probes the MODEL's transport; variant arms of one model share it.
    arms = sorted(
        {row_model(r) for r in manifest["rows"]},
        key=lambda a: (sizes.get(a, 0), a),
    )
    # Arms served by another engine (WFE_ENGINE) are not Ollama tags at all.
    missing = [a for a in arms if a not in sizes] if sizes and ENGINE == "ollama" else []
    frozen = manifest.setdefault("identity_map", {})
    ws_by_model: dict[str, set] = {}
    budgets_by_model: dict[str, list[tuple[str, str, int]]] = {}
    seen_budgets: set[tuple[str, str, str]] = set()
    for r in manifest["rows"]:
        model = row_model(r)
        workspace = r["workspace"]
        ws_by_model.setdefault(model, set()).add(workspace)
        key = (model, r["arm"], workspace)
        if key in seen_budgets:
            continue
        seen_budgets.add(key)
        wsc = workspace_context(workspace, row_overrides(r).get("persona"))
        sampling = _sampling_for(wsc, r.get("repeat") or 0, row_overrides(r))
        budgets_by_model.setdefault(model, []).append(
            (r["arm"], workspace, _served_predict_budget(wsc, sampling))
        )
    bad = []
    drift: list[str] = []
    for i, a in enumerate(arms, 1):
        t0 = time.monotonic()
        res = (  # in pipeline mode, ask the pipeline what it serves for this arm
            preflight_pipeline(sorted(ws_by_model.get(a, ())), a, manifest["rows"])
            if ENGINE == "pipeline"
            else preflight_arm(campaign_dir, a, force)
        )
        verdict = str(res.get("verdict"))
        # The first preflight of a pair freezes its identity; a later change
        # means the two halves of the comparison describe different builds.
        drift += freeze_identities(frozen, res.get("identities") or {})
        _print_preflight(i, len(arms), a, res, time.monotonic() - t0, budgets_by_model.get(a, []))
        if verdict != "OK":
            bad.append(a)
        drain_model(a)
        sys.stdout.flush()
    save_manifest(campaign_dir, manifest)
    for d in drift:
        print(f"          IDENTITY DRIFT: {d}")
    if drift:
        bad.append("identity-drift")
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


_INSPECT_FLAGS = ("status", "watch", "verify_complete", "health")


def _is_inspect_only(args) -> bool:
    """True for the read-only campaign views dispatched by _inspect_command."""
    return any(getattr(args, flag, False) for flag in _INSPECT_FLAGS)


def _inspect_command(args, campaign_dir: Path) -> int | None:
    """The read-only views of a campaign. Separated from main() so a sweep in
    flight can be inspected without any code path that could write to it."""
    if args.status:
        return _cmd_status(campaign_dir)
    if args.watch:
        return _cmd_watch(campaign_dir, args.watch_interval)
    if args.verify_complete:
        return _cmd_verify_complete(campaign_dir)
    if args.health:
        return _cmd_health(campaign_dir, args.stale_after_s)
    return None


def _select_arms(manifest: dict, want: str | None, arms_file: Path | None = None) -> list[str]:
    """Arm ids to run. `--arm` may name an arm id or a model tag (every variant)."""
    roles = {}
    for row in manifest["rows"]:
        arm = row.get("arm")
        if arm:
            roles[arm] = min(roles.get(arm, 1), 0 if row.get("arm_role") == "incumbent" else 1)
    selected = sorted(
        {r["arm"] for r in manifest["rows"] if want in (None, r["arm"], row_model(r))},
        key=lambda arm: (roles.get(arm, 1), arm),
    )
    if arms_file is None:
        return selected
    requested = {line.strip() for line in arms_file.read_text().splitlines() if line.strip()}
    models = {
        arm: {row_model(row) for row in manifest["rows"] if row.get("arm") == arm}
        for arm in selected
    }
    return [arm for arm in selected if arm in requested or models[arm] & requested]


def _ready(campaign_dir: Path) -> bool:
    """The chat engine answers, and it is the engine the campaign was created
    for: the arm ids of an oMLX campaign are oMLX served ids, and resuming it
    with WFE_ENGINE unset would send them to Ollama (404 -> HARNESS_ERROR rows),
    or, for a tag both engines serve, silently measure the other engine."""
    if not ollama_reachable():
        _log(campaign_dir, "ABORT: chat engine unreachable")
        return False
    started_on = (load_manifest(campaign_dir).get("env") or {}).get("engine", "ollama")
    if started_on != ENGINE:
        _log(campaign_dir, f"ABORT: campaign created on engine {started_on}, now {ENGINE}")
        return False
    return True


def _warn_prompt_surface(matrix: list[dict]) -> None:
    import yaml

    from tests.wfe.prompt_surface import audit_workspace, production_tool_names
    from tests.wfe.runner import REPO as _REPO
    from tests.wfe.runner import workspace_context

    portal = yaml.safe_load((_REPO / "config/portal.yaml").read_text()) or {}
    known = production_tool_names(portal)
    keys = {
        (r.get("workspace", ""), r.get("suite_path", ""), (r.get("overrides") or {}).get("persona"))
        for r in matrix
    }
    for ws_id, suite, persona in sorted(
        (k for k in keys if k[0] and k[1]), key=lambda k: (k[0], k[1], k[2] or "")
    ):
        if not Path(suite).is_file():
            continue
        ctx = workspace_context(ws_id, persona)
        served, surface = ctx["system_prompt"], set(ctx["tool_surface"])
        for w in audit_workspace(served, Path(suite).read_text(), surface, known):
            print(f"WARN prompt/tool surface [{ws_id}]: {w}", flush=True)


def plan_repeats(plan_path: Path) -> int | None:
    """Plan-level `repeats`, an explicit per-task count. None leaves the tier policy."""
    data = yaml.safe_load(plan_path.read_text()) or {}
    if not isinstance(data, dict):
        return None
    raw = data.get("repeats")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError(f"{plan_path.name}: repeats must be a positive integer")
    return raw


def execution_options(
    plan_path: Path,
    matrix: list[dict],
    pilot_tasks: int | None = None,
    rehearsal: bool = False,
) -> dict:
    """Read bounded scheduling choices from the workload plan."""
    data = yaml.safe_load(plan_path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{plan_path.name}: plan must be a mapping")
    arm_count = len({row["arm"] for row in matrix})
    order = data.get("arm_order")
    if pilot_tasks is not None:
        order = "interleaved"
    elif order is None:
        order = "interleaved" if arm_count >= 2 else "sequential"
    if order not in ("interleaved", "sequential"):
        raise ValueError(f"{plan_path.name}: arm_order must be interleaved or sequential")
    block = data.get("interleave_block")
    if block is not None and (isinstance(block, bool) or not isinstance(block, int) or block < 1):
        raise ValueError(f"{plan_path.name}: interleave_block must be a positive integer")
    max_minutes = data.get("max_minutes", 120)
    if isinstance(max_minutes, bool) or not isinstance(max_minutes, int) or max_minutes < 1:
        raise ValueError(f"{plan_path.name}: max_minutes must be a positive integer")
    margin = data.get("non_inferiority_margin")
    if margin is not None:
        margin = decision._validated_margin(margin)
    pilot_floor_rate = _plan_fraction(data, "pilot_floor_rate", 1 / HALT_AFTER_ROWS, exclusive=True)
    rehearsal_max_overhead = _plan_fraction(data, "rehearsal_max_overhead", 0.25)
    rehearsal_max_phase_s = _plan_positive_number(data, "rehearsal_max_phase_s", 120)
    workspaces = {str(row.get("workspace") or "") for row in matrix} - {""}
    if order == "interleaved" and arm_count >= 2 and workspaces and not rehearsal:
        row_walls = _row_wall_history(matrix)
        swap_profiles = _engine_swap_profiles()
        block_by_workspace, reason_by_workspace, models_by_workspace = _choose_interleave_blocks(
            matrix, block, row_walls, swap_profiles
        )
    else:
        default_block = block or 4
        block_by_workspace = dict.fromkeys(sorted(workspaces), default_block)
        reason = f"plan override interleave_block={block}" if block else "fallback block 4"
        reason_by_workspace = dict.fromkeys(block_by_workspace, reason)
        models_by_workspace = {}
        swap_profiles = {}
    if rehearsal:
        block_by_workspace = dict.fromkeys(sorted(workspaces), 1)
        reason_by_workspace = dict.fromkeys(workspaces, "rehearsal requires one task per block")
        models_by_workspace = {}
        swap_profiles = {}
    return {
        "arm_order": order,
        "interleave_block": max(block_by_workspace.values(), default=4),
        "interleave_block_by_workspace": block_by_workspace,
        "interleave_block_reason_by_workspace": reason_by_workspace,
        "interleave_models_by_workspace": models_by_workspace,
        "interleave_swap_profiles": swap_profiles,
        "interleave_block_override": block is not None or rehearsal,
        "resident_fit_workspaces": [],
        "max_minutes": max_minutes,
        "non_inferiority_margin": margin,
        "pilot_tasks": pilot_tasks,
        "pilot_floor_rate": pilot_floor_rate,
        "rehearsal": rehearsal,
        "rehearsal_max_overhead": rehearsal_max_overhead,
        "rehearsal_max_phase_s": rehearsal_max_phase_s,
    }


def _plan_fraction(data: dict, key: str, default: float, *, exclusive: bool = False) -> float:
    raw = data.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise ValueError(f"{key} must be a finite number")
    low_ok = raw > 0 if exclusive else raw >= 0
    high_ok = raw < 1 if exclusive else raw <= 1
    if not low_ok or not high_ok:
        interval = "(0, 1)" if exclusive else "[0, 1]"
        raise ValueError(f"{key} must be in {interval}")
    return float(raw)


def _plan_positive_number(data: dict, key: str, default: float) -> float:
    raw = data.get(key, default)
    if (
        isinstance(raw, bool)
        or not isinstance(raw, (int, float))
        or not math.isfinite(raw)
        or raw <= 0
    ):
        raise ValueError(f"{key} must be a finite positive number")
    return float(raw)


def _summary(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "median_s": round(statistics.median(ordered), 2),
        "p95_s": round(ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)], 2),
    }


def _latest_log_day(path: Path, pattern: re.Pattern) -> str | None:
    latest = None
    try:
        with path.open(errors="replace") as log:
            for line in log:
                match = pattern.search(line)
                if match:
                    day = match["ts"][:10]
                    latest = max(latest, day) if latest else day
    except OSError:
        return None
    return latest


def _omlx_swap_profile(path: Path) -> dict | None:
    pending: dict[tuple[str, str], list[dt.datetime]] = {}
    spans: dict[str, list[float]] = {"load": [], "unload": []}
    pattern = re.compile(
        r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[.,]\d+) - "
        r"omlx\.engine_pool - INFO - (?P<event>Loading model|Loaded model|"
        r"Unloading model|Unloaded model): (?P<model>[^,(]+)"
    )
    latest = _latest_log_day(path, pattern)
    if latest is None:
        return None
    try:
        with path.open(errors="replace") as log:
            for line in log:
                match = pattern.match(line)
                if match is None or match["ts"][:10] != latest:
                    continue
                stamp = dt.datetime.fromisoformat(match["ts"].replace(",", "."))
                event = match["event"]
                kind = "load" if event in ("Loading model", "Loaded model") else "unload"
                model = match["model"].strip()
                key = (kind, model)
                if event in ("Loading model", "Unloading model"):
                    pending.setdefault(key, []).append(stamp)
                    continue
                starts = pending.get(key) or []
                if starts:
                    index = -1 if kind == "unload" else 0
                    elapsed = (stamp - starts.pop(index)).total_seconds()
                    if 0 < elapsed <= 600:
                        spans[kind].append(elapsed)
    except OSError:
        return None
    load = _summary(spans["load"])
    if load is None:
        return None
    unload = _summary(spans["unload"])
    return {
        "load": load,
        "unload": unload,
        "swap_median_s": round(load["median_s"] + (unload or {}).get("median_s", 0), 2),
        "swap_p95_s": round(load["p95_s"] + (unload or {}).get("p95_s", 0), 2),
        "p95_method": "sum of component p95 values",
        "log_day": latest,
    }


def _ollama_swap_profile(path: Path) -> dict | None:
    pending = 0
    starts = re.compile(r'msg="loading model via llama-server"')
    durations = re.compile(r'msg="llama-server started in ([\d.]+) seconds"')
    day_pattern = re.compile(
        r'time=(?P<ts>\d{4}-\d\d-\d\dT[^ ]+).*msg="(?:loading model via llama-server|'
        r"llama-server started in)"
    )
    latest = _latest_log_day(path, day_pattern)
    if latest is None:
        return None
    loads = []
    try:
        with path.open(errors="replace") as log:
            for line in log:
                day = day_pattern.search(line)
                if day is None or day["ts"][:10] != latest:
                    continue
                if starts.search(line):
                    pending += 1
                match = durations.search(line)
                if match and pending:
                    pending -= 1
                    loads.append(float(match.group(1)))
    except OSError:
        return None
    load = _summary(loads)
    if load is None:
        return None
    return {
        "load": load,
        "unload": None,
        "swap_median_s": load["median_s"],
        "swap_p95_s": load["p95_s"],
        "p95_method": "logged startup duration; unload duration unavailable",
        "log_day": latest,
    }


def _engine_swap_profiles() -> dict:
    omlx_path = Path(os.environ.get("WFE_OMLX_LOG", "/opt/homebrew/var/log/omlx.log"))
    ollama_path = Path(os.environ.get("WFE_OLLAMA_LOG", "/opt/homebrew/var/log/ollama.log"))
    return {
        "omlx": _omlx_swap_profile(omlx_path),
        "ollama": _ollama_swap_profile(ollama_path),
    }


def _row_wall_history(matrix: list[dict]) -> dict[str, dict]:
    identities = {(row.get("workspace"), row.get("suite"), row.get("task_id")) for row in matrix}
    walls: dict[str, list[float]] = {}
    for path in CAMPAIGNS.glob("*/rows/*.json"):
        try:
            row = json.loads(path.read_text())
            key = (row.get("workspace"), row.get("suite"), row.get("task_id"))
            wall = (row.get("economics") or {}).get("wall_s")
        except (OSError, ValueError, TypeError):
            continue
        if key not in identities or isinstance(wall, bool) or not isinstance(wall, (int, float)):
            continue
        if math.isfinite(wall) and wall > 0:
            walls.setdefault(str(row["workspace"]), []).append(float(wall))
    return {
        workspace: {"n": len(values), "median_s": round(statistics.median(values), 2)}
        for workspace, values in walls.items()
    }


def _models_by_workspace(matrix: list[dict]) -> dict[str, list[dict[str, str]]]:
    models: dict[str, set[tuple[str, str]]] = {}
    for row in matrix:
        workspace = str(row.get("workspace") or "")
        model = row_model(row)
        if ENGINE == "pipeline":
            backend, model = _serving_seat(workspace, model)
            engine = backend_engine(backend)
        else:
            engine = ENGINE
        if workspace and engine in ("omlx", "ollama"):
            models.setdefault(workspace, set()).add((engine, model))
    return {
        workspace: [{"engine": engine, "model": model} for engine, model in sorted(entries)]
        for workspace, entries in models.items()
    }


def _choose_interleave_blocks(
    matrix: list[dict], override: int | None, row_walls: dict, swap_profiles: dict
) -> tuple[dict[str, int], dict[str, str], dict[str, list[dict[str, str]]]]:
    models = _models_by_workspace(matrix)
    choices, reasons = {}, {}
    for workspace in sorted({str(row.get("workspace") or "") for row in matrix} - {""}):
        if override is not None:
            choices[workspace] = override
            reasons[workspace] = f"plan override interleave_block={override}"
            continue
        wall = row_walls.get(workspace)
        engines = sorted({model["engine"] for model in models.get(workspace, [])})
        profiles = [swap_profiles.get(engine) for engine in engines]
        if len(models.get(workspace, [])) == 1:
            choices[workspace] = 1
            reasons[workspace] = "same resident model serves all arms"
        elif not wall or not profiles or any(profile is None for profile in profiles):
            choices[workspace] = 4
            reasons[workspace] = (
                "fallback block 4; matching row history or engine swap timing unavailable"
            )
        else:
            swap_s = max(profile["swap_median_s"] for profile in profiles)
            choices[workspace] = max(1, math.ceil(swap_s / (0.10 * wall["median_s"])))
            profile_text = ", ".join(
                f"{engine} median={profile['swap_median_s']}s p95={profile['swap_p95_s']}s"
                for engine, profile in zip(engines, profiles, strict=True)
            )
            reasons[workspace] = (
                f"ceil(max engine swap median / 10% of median row wall): {profile_text}; "
                f"row median={wall['median_s']}s n={wall['n']}"
            )
    return choices, reasons, models


def _pilot_suite_tasks(rows: list[dict]) -> dict[str, dict[str, dict]]:
    """suite -> task_id -> task, for declared family/category lookups."""
    out: dict[str, dict[str, dict]] = {}
    for suite, path in {r["suite"]: r.get("suite_path") for r in rows}.items():
        tasks: dict[str, dict] = {}
        if path:
            try:
                tasks = {t["id"]: t for t in load_suite(path)}
            except (OSError, ValueError):
                tasks = {}
        out[suite] = tasks
    return out


def _task_family(task_id: str, task: dict | None) -> str:
    """A task's family: its declared family/category, else its id with the
    trailing draw-index and size components stripped (`lr-aggregation-02-t112k`
    -> `lr-aggregation`)."""
    for field in ("family", "category"):
        value = (task or {}).get(field)
        if value:
            return str(value)
    parts = task_id.split("-")
    while len(parts) > 1 and (parts[-1].isdigit() or re.fullmatch(r"[a-z]\d+[km]?", parts[-1])):
        parts.pop()
    return "-".join(parts)


def pilot_matrix(matrix: list[dict], task_limit: int) -> list[dict]:
    """Keep one draw per arm of N task identities, SPREAD across task families.

    A task's group is its suite plus its family (see `_task_family`). The
    selection round-robins the groups in stable first-appearance order — one
    task per group per pass, each group's tasks in stable order — until N
    identities are picked, so a pilot samples the families instead of the first
    N identities in suite order. The same identities are selected for every arm."""
    if task_limit < 1:
        raise ValueError("pilot task count must be a positive integer")
    identities = list(dict.fromkeys((r["workspace"], r["suite"], r["task_id"]) for r in matrix))
    suite_tasks = _pilot_suite_tasks(matrix)
    groups: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for ident in identities:
        _ws, suite, task_id = ident
        group = (suite, _task_family(task_id, suite_tasks.get(suite, {}).get(task_id)))
        groups.setdefault(group, []).append(ident)
    picked: list[tuple[str, str, str]] = []
    cursor = dict.fromkeys(groups, 0)
    while len(picked) < task_limit:
        progressed = False
        for group in groups:
            if cursor[group] >= len(groups[group]):
                continue
            picked.append(groups[group][cursor[group]])
            cursor[group] += 1
            progressed = True
            if len(picked) == task_limit:
                break
        if not progressed:
            break
    selected = set(picked)
    return [
        row
        for row in matrix
        if row["repeat"] == 0 and (row["workspace"], row["suite"], row["task_id"]) in selected
    ]


def _effective_campaign_id(
    campaign_id: str | None, pilot_tasks: int | None, rehearsal: bool = False
) -> str | None:
    if rehearsal:
        if campaign_id is None or campaign_id.endswith("_rehearsal"):
            return campaign_id
        return f"{campaign_id}_rehearsal"
    if campaign_id is None or pilot_tasks is None or campaign_id.endswith("_pilot"):
        return campaign_id
    return f"{campaign_id}_pilot"


def _planned_matrix(plan: Path, args) -> tuple[int | dict[str, int], list[dict]]:
    """The matrix and its repeats. Without --repeats a confirm gives each arm 1 repeat when its
    screen rows recorded a served temperature of 0, and the default otherwise; a realuse tier
    gives every task one draw, and a second only to an arm above temperature 0. A plan-level
    `repeats` integer is an explicit count, same as --repeats, and beats that policy."""

    def expand(n):
        return expand_matrix(
            plan,
            n,
            args.all_suites,
            None if getattr(args, "block_worker", False) else args.arm,
            args.suite,
            args.task,
            args.workspace,
            args.tier,
            load_advance(args.advance),
        )

    chosen = args.repeats if args.repeats is not None else plan_repeats(plan)
    repeats = DEFAULT_REPEATS if chosen is None else chosen
    if chosen is None and args.tier == "realuse":
        repeats = 1
    matrix = expand(repeats)
    if chosen is None and args.tier == "confirm":
        repeats = repeats_policy(CAMPAIGNS / args.campaign_id, matrix, DEFAULT_REPEATS)
        matrix = expand(repeats)
    if chosen is None and args.tier == "realuse":
        repeats = realuse_repeats(CAMPAIGNS / args.campaign_id, matrix)
        matrix = expand(repeats)
    pilot_tasks = getattr(args, "pilot", None)
    if pilot_tasks is not None:
        matrix = pilot_matrix(matrix, pilot_tasks)
    return repeats, matrix


def _validate_reuse_screen_args(ap, args) -> None:
    if args.reuse_screen and args.tier != "confirm":
        ap.error("--reuse-screen can only be used with --tier confirm")


def _realuse_tool_preflight(plan: Path) -> None:
    if not plan.is_file():
        return
    checked, failures = prompt_tool_surface_report(plan)
    plan_doc = yaml.safe_load(plan.read_text()) or {}
    if any(
        (workload.get("home") or "").startswith("realuse_")
        for workload in (plan_doc.get("workloads") or {}).values()
    ):
        task_checked, task_failures = realuse_tool_surface_report(plan)
        checked += task_checked
        failures += task_failures
    if failures:
        report = [f"tool surface preflight: FAIL ({len(failures)} mismatch(es))"]
        report.extend(f"  {failure}" for failure in failures)
        raise GateRefused("\n".join(report))
    # stderr: --list-arms stdout is parsed line by line as arm tags.
    print(f"tool surface preflight: PASS ({checked} check(s))", file=sys.stderr)


def _plan_command(args, plan: Path) -> int | None:
    """--rescore, the plan preflight, and the plan-only commands. Only commands that build
    or list rows from a plan are gated: the read-only views (--status, --watch, ...) run
    against an existing campaign without --plan, and the default workloads.yaml would
    refuse them for workspaces the campaign never touches (readiness pass 5, 2026-11-05)."""
    if args.rescore:
        return _cmd_rescore(args)
    if not _is_inspect_only(args) and not args.block_worker:
        _realuse_tool_preflight(plan)
    if args.list_arms:
        return _cmd_list_arms(plan, args.all_suites)
    if args.smoke:
        return _cmd_smoke(args, plan)
    return None


def _load_guard_plan(models: list[dict[str, str]]) -> dict:
    key = os.environ.get("PIPELINE_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        f"{CHAT_BASE.rstrip('/')}/admin/load-plan",
        data=json.dumps({"models": models}).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)
    except Exception as exc:
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}


def _apply_load_guard_choices(
    campaign_dir: Path, manifest: dict, execution: dict, arms: list[str]
) -> dict:
    rows = [row for row in manifest["rows"] if row.get("arm") in arms]
    models_by_workspace = _models_by_workspace(rows)
    block_map = dict(execution.get("interleave_block_by_workspace") or {})
    reasons = dict(execution.get("interleave_block_reason_by_workspace") or {})
    resident = set(execution.get("resident_fit_workspaces") or [])
    results = {}
    for workspace in sorted({str(row.get("workspace") or "") for row in rows} - {""}):
        workspace_arms = {row.get("arm") for row in rows if row.get("workspace") == workspace}
        if len(workspace_arms) < 2:
            continue
        models = models_by_workspace.get(workspace, [])
        if len(models) == 1:
            resident.add(workspace)
            results[workspace] = {"status": "same resident model"}
            continue
        if not models:
            results[workspace] = {"status": "unavailable", "reason": "serving seats unresolved"}
            continue
        if ENGINE != "pipeline":
            results[workspace] = {"status": "unavailable", "reason": "load plan requires pipeline"}
            continue
        plan = _load_guard_plan(models)
        results[workspace] = plan
        if (
            plan.get("guard_enabled") is True
            and plan.get("fits") is True
            and plan.get("busy") is False
        ):
            resident.add(workspace)
            if not execution.get("interleave_block_override"):
                block_map[workspace] = 1
                reasons[workspace] = "load guard confirms both arms fit resident together; block 1"
    execution["interleave_block_by_workspace"] = block_map
    execution["interleave_block_reason_by_workspace"] = reasons
    execution["interleave_block"] = max(
        block_map.values(), default=execution.get("interleave_block", 4)
    )
    execution["resident_fit_workspaces"] = sorted(resident)
    execution["interleave_load_guard"] = results
    manifest["execution"] = execution
    save_manifest(campaign_dir, manifest)
    return execution


def _prepare_campaign(ap, args, plan: Path) -> tuple[Path | None, dict, int | None]:
    if not args.campaign_id:
        ap.error("--campaign-id is required (or use --smoke / --rescore / --list-arms)")
    if args.rehearse:
        args.pilot = 2
        args.campaign_id = _effective_campaign_id(args.campaign_id, 2, rehearsal=True)
    elif args.pilot is not None:
        if args.pilot < 1:
            ap.error("--pilot must be a positive task count")
        args.campaign_id = _effective_campaign_id(args.campaign_id, args.pilot)
    repeats, matrix = _planned_matrix(plan, args)
    if (
        args.rehearse
        and len({(row["workspace"], row["suite"], row["task_id"]) for row in matrix}) != 2
    ):
        ap.error("--rehearse requires exactly two selected task identities")
    if args.pilot is not None and len({row["arm"] for row in matrix}) < 2:
        ap.error("--pilot requires at least two arms")
    stored_manifest = CAMPAIGNS / args.campaign_id / "manifest.json"
    if args.block_worker and stored_manifest.is_file():
        execution = load_manifest(stored_manifest.parent).get("execution")
        if not execution:
            execution = execution_options(plan, matrix, args.pilot, rehearsal=args.rehearse)
    else:
        execution = execution_options(plan, matrix, args.pilot, rehearsal=args.rehearse)
    if not args.block_worker:
        _warn_prompt_surface(matrix)
    if args.dry_run:
        return None, execution, _cmd_dry_run(matrix, repeats)
    campaign_dir = open_campaign(
        args.campaign_id,
        plan,
        matrix,
        args.append,
        reuse_screen=args.reuse_screen,
        execution=execution,
    )
    return campaign_dir, execution, None


def _run_selected_arms(
    campaign_dir: Path, args, execution: dict
) -> tuple[list[str], list[dict], int | None]:
    manifest = load_manifest(campaign_dir)
    arms = _select_arms(manifest, args.arm, args.arms_file)
    only_run_ids = (
        {line.strip() for line in args.run_ids_file.read_text().splitlines() if line.strip()}
        if args.run_ids_file
        else None
    )
    deadline = _campaign_deadline(execution)
    if execution.get("arm_order") == "interleaved" and len(arms) > 1:
        if not args.block_worker:
            execution = _apply_load_guard_choices(campaign_dir, manifest, execution, arms)
        return arms, _run_interleaved_campaign(campaign_dir, arms, args, execution, deadline), None
    outs = []
    for arm in arms:
        manifest = load_manifest(campaign_dir)
        if manifest.get("campaign_stop"):
            break
        if not ollama_reachable():
            _log(campaign_dir, f"ABORT before {arm}: Ollama unreachable")
            return arms, outs, 3
        out = execute_arm(
            campaign_dir,
            arm,
            args.max_turns,
            args.budget_s,
            args.debug_dir,
            args.force,
            args.notify,
            args.rerun_failed,
            not args.no_halt,
            curtail=not args.no_curtail,
            fresh_incumbent=args.fresh_incumbent,
            only_run_ids=only_run_ids,
            deadline_epoch=deadline,
            timing=bool(args.block_worker),
            block_id=getattr(args, "block_id", None),
        )
        outs.append(out or {})
        if (out or {}).get("halted"):
            break
    return arms, outs, None


def _resume_stopped_campaign(campaign_dir: Path, manifest: dict, args) -> dict:
    stop = manifest.get("campaign_stop") or {}
    if stop and (stop.get("kind") == "time_cap" or args.no_curtail or args.append):
        manifest.setdefault("campaign_stop_history", []).append(stop)
        manifest.pop("campaign_stop", None)
        save_manifest(campaign_dir, manifest)
    return manifest


def _complete_campaign(campaign_dir: Path, args, arms: list[str], outs: list[dict]) -> int:
    _maybe_judge(campaign_dir, args.judge)
    n = build_review_queue(campaign_dir)
    dirty = config_dirty()
    manifest = load_manifest(campaign_dir)
    manifest["config_dirty_at_end"] = dirty
    save_manifest(campaign_dir, manifest)
    if dirty != (manifest.get("config_dirty_at_start") or []):
        _log(campaign_dir, f"WARNING: config/ changed during the campaign: {dirty}")
    print(f"\ncampaign dir: {campaign_dir}   creative queue: {n} item(s)")
    print(f"next: uv run python -m tests.wfe.report --campaign {campaign_dir.name}")
    return EXIT_STOPPED if manifest.get("campaign_stop") else exit_status(outs, arms)


def _execute_campaign(campaign_dir: Path, execution: dict, args) -> int:
    rc = _inspect_command(args, campaign_dir)
    if rc is not None:
        return rc
    if not _ready(campaign_dir):
        return 3
    # Re-gate every row before it runs: suites change and keys expire after open.
    gate_execution(campaign_dir)
    if args.preflight:
        return _cmd_preflight(campaign_dir, args.force)
    manifest = load_manifest(campaign_dir)
    if not manifest.get("execution"):
        manifest["execution"] = execution
        save_manifest(campaign_dir, manifest)
    execution = manifest.get("execution") or execution
    _resume_stopped_campaign(campaign_dir, manifest, args)
    arms, outs, rc = _run_selected_arms(campaign_dir, args, execution)
    if rc is not None:
        return rc
    if args.block_worker:
        manifest = load_manifest(campaign_dir)
        return EXIT_STOPPED if manifest.get("campaign_stop") else exit_status(outs, arms)
    return _complete_campaign(campaign_dir, args, arms, outs)


def main() -> int:
    ap, args = _parse_args()
    _validate_reuse_screen_args(ap, args)
    plan = Path(args.plan)
    rc = _plan_command(args, plan)
    if rc is not None:
        return rc
    campaign_dir, execution, rc = _prepare_campaign(ap, args, plan)
    if rc is not None:
        return rc
    assert campaign_dir is not None
    return _execute_campaign(campaign_dir, execution, args)


def _finish_exit() -> int | None:
    """The offline finish checks. None means main() should run."""
    ap, args = _parse_args()
    if args.dry_run:
        return None
    if args.pilot_floor_check:
        if not args.campaign_id:
            ap.error("--pilot-floor-check needs --campaign-id")
        result = pilot_floor_check(args.campaign_id)
        if result and result["no_signal"]:
            counts = ", ".join(
                f"{arm['arm']}={arm['passes']}/{arm['graded_rows']}" for arm in result["arms"]
            )
            print(f"NO_SIGNAL all pilot arms below {result['floor_rate']:.0%}: {counts}")
            return EXIT_OK
        print("PILOT_FLOOR CLEAR_OR_UNAVAILABLE")
        return EXIT_NO_SELECTION
    if args.finish:
        if not args.campaign_id:
            ap.error("--finish needs --campaign-id")
        if args.rehearse:
            args.pilot = 2
        args.campaign_id = _effective_campaign_id(
            args.campaign_id, args.pilot, rehearsal=args.rehearse
        )
        return campaign_finish(CAMPAIGNS / args.campaign_id, args.campaign_id)
    if not args.require_measured:
        return None
    if not args.campaign_id:
        ap.error("--require-measured needs --campaign-id")
    if args.rehearse:
        args.pilot = 2
    args.campaign_id = _effective_campaign_id(args.campaign_id, args.pilot, rehearsal=args.rehearse)
    return _cmd_require_measured(CAMPAIGNS / args.campaign_id)


def _cli() -> int:
    try:
        early = _finish_exit()
        if early is not None:
            return early
        return main()
    except GateRefused as e:
        print(e, file=sys.stderr)
        return EXIT_GATE


if __name__ == "__main__":
    raise SystemExit(_cli())
