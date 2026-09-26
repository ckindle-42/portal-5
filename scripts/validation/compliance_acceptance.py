"""HG/HH — compliance acceptance currency, and the seat's template identity.

TASK_COMPLIANCE_PROVE_CIP_007_V1 §P6.1. Seven live harnesses were abandoned
because abandonment was free, and `tests/wfe/settings_audit.py` went unused for
the same reason. Nothing failed when a harness stopped running; nothing failed
when the thing it measured moved underneath it. These two make both a failing
gate, modelled on the doc-ledger currency check.

* **HG** fails when `portal/modules/compliance/` has moved and no acceptance run
  exists at or after the commit that moved it. The module's history is a
  sequence of rewrites each of which passed every unit test and then failed the
  moment a model was on the other end; the only thing that catches that class is
  a live run, and the only thing that makes a live run happen is a gate.
* **HH** fails when the compliance seat's LIVE chat-template sha differs from
  the one the campaign pinned. A run whose template moved underneath it is not
  comparable to the runs before it, and the sha is the only way to know it
  happened. A template is not versioned, not announced, and changes on an
  `ollama pull`.

Both are pre-PUSH checks in practice: they need the store and the runner. Both
are also held at SKIP by the `IN_SERVICE` flag below while compliance is still
being built, so neither spends a push's time on a module nothing depends on yet.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.validation.registry import register

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = "portal/modules/compliance"
ACCEPTANCE_ROOT = REPO_ROOT / "reports" / "compliance" / "acceptance"
CAMPAIGN_PIN = REPO_ROOT / "reports" / "compliance" / "SETTINGS_PREFLIGHT_V1.json"
#: The PIPELINE-era pin (PIPELINE_ALIGNMENT_V1 §P5): per seat, the route the
#: pipeline takes with EACH engine's own template sha. Present it outranks the
#: native-era V1 pin, whose shas were read through Ollama's /api/show while a
#: different checkpoint on a different engine answers.
CAMPAIGN_PIN_V2 = REPO_ROOT / "reports" / "compliance" / "SETTINGS_PREFLIGHT_V2.json"

# The module is under active development (weeks in, not yet handling real
# traffic): HG's live-run requirement — a multi-hour acceptance suite re-run
# on every push that so much as reformats a file under MODULE_PATH — blocks
# unrelated work for a safety property nothing downstream depends on yet.
# Flip this to True the day compliance goes into service, which restores HG
# to a hard push-blocking FAIL as originally designed.
#
# Pre-service the result is SKIP, not WARN. A WARN still named
# run_compliance_acceptance.sh on every push touching the module, and that is
# how the suite kept getting started: a ~6-hour live run whose council cycles
# a 58 GB seat through Ollama, for a module nothing depends on yet. The gate
# should be silent while the answer is "not yet", and loud the day it is not.
IN_SERVICE = False


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def _is_ancestor(older: str, newer: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", older, newer],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def _acceptance_runs() -> list[dict[str, Any]]:
    """Every acceptance run on disk, each keyed by the rev it ran against.

    A directory with no `status.json`, or one whose cells are empty, is NOT a
    run. That distinction is the whole point: six of the seven abandoned
    harnesses left directories behind.
    """
    runs: list[dict[str, Any]] = []
    if not ACCEPTANCE_ROOT.is_dir():
        return runs
    for entry in sorted(ACCEPTANCE_ROOT.iterdir()):
        status = entry / "status.json"
        if not entry.is_dir() or not status.is_file():
            continue
        try:
            data = json.loads(status.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cells = data.get("cells") or []
        if not cells:
            continue
        # COMPLETE means every cell the manifest planned actually ran. A partial
        # run is not currency: measured on this very check, a campaign stopped
        # after 5 of 18 cells satisfied it, because it asked "is there a run"
        # and never "did it finish". An aborted run is exactly the shape the
        # seven abandoned harnesses left behind.
        expected = 0
        manifest = entry / "manifest.json"
        if manifest.is_file():
            try:
                plan = json.loads(manifest.read_text(encoding="utf-8"))
                expected = (
                    len(plan.get("cases") or [])
                    * len(plan.get("seats") or [])
                    * len(plan.get("adapters") or [])
                    * int(plan.get("runs") or 0)
                )
            except (OSError, ValueError):
                expected = 0
        runs.append(
            {
                "rev": data.get("git_head") or entry.name,
                "dir": entry.name,
                "cells": len(cells),
                "expected_cells": expected,
                "complete": bool(expected) and len(cells) >= expected,
                "passed": sum(1 for c in cells if c.get("passed")),
                "updated_at": data.get("updated_at", ""),
            }
        )
    return runs


@register(
    "compliance_acceptance_currency",
    "HG. compliance acceptance has run at or after the last commit touching the module",
    order=198,
)
def check_compliance_acceptance_currency() -> tuple[str, str, list[dict]]:
    status, detail, findings = _compliance_acceptance_currency()
    if status == "FAIL" and not IN_SERVICE:
        return (
            "SKIP",
            f"compliance is pre-service (IN_SERVICE=False in "
            f"scripts/validation/compliance_acceptance.py) — no live run is asked for. "
            f"Underlying: {detail}",
            findings,
        )
    return status, detail, findings


def _compliance_acceptance_currency() -> tuple[str, str, list[dict]]:
    try:
        last_touch = _git("log", "-1", "--format=%H", "--", MODULE_PATH)
    except subprocess.SubprocessError as exc:
        return "FAIL", f"cannot read the module's history: {exc}", []
    if not last_touch:
        return "PASS", f"{MODULE_PATH} has no history in this checkout", []

    runs = _acceptance_runs()
    findings: list[dict[str, Any]] = [
        {"last_commit_touching_module": last_touch[:12], "acceptance_runs": len(runs)},
        *runs,
    ]
    if not runs:
        return (
            "FAIL",
            f"{MODULE_PATH} was last changed in {last_touch[:12]} and "
            f"reports/compliance/acceptance/ holds no run at all — run "
            "scripts/run_compliance_acceptance.sh",
            findings,
        )
    current = [r for r in runs if r["complete"] and _is_ancestor(last_touch, str(r["rev"]))]
    partial = [r for r in runs if not r["complete"] and _is_ancestor(last_touch, str(r["rev"]))]
    if not current and partial:
        newest = max(partial, key=lambda r: str(r["updated_at"]))
        return (
            "FAIL",
            f"the only acceptance run at or after {last_touch[:12]} is INCOMPLETE: "
            f"{newest['cells']} of {newest['expected_cells']} planned cell(s) in "
            f"{newest['dir'][:12]}. A stopped run is not currency — finish it, or "
            "re-run scripts/run_compliance_acceptance.sh",
            findings,
        )
    if not current:
        newest = max(runs, key=lambda r: str(r["updated_at"]))
        return (
            "FAIL",
            f"{MODULE_PATH} was last changed in {last_touch[:12]} and the newest acceptance "
            f"run is against {str(newest['rev'])[:12]}, which does not contain it — the "
            "module moved and nothing re-ran. Run scripts/run_compliance_acceptance.sh",
            findings,
        )
    return (
        "PASS",
        f"{len(current)} acceptance run(s) at or after {last_touch[:12]}",
        findings,
    )


def _pipeline_pin_template_identity(pinned: dict[str, Any]) -> tuple[str, str, list[dict]]:
    """HH against the pipeline-era pin: per seat, per engine on the seat's
    serving route, the live template must match the pin for THAT engine.

    The pre-service short-circuit above means this runs only once IN_SERVICE
    flips; its job that day is to refuse a push on which the primary engine's
    template moved underneath the campaign — the failure V1 could not see
    because it read the fallback's /api/show."""
    from tests.wfe.settings_audit import _template_sha, _template_sha_omlx

    findings: list[dict[str, Any]] = []
    drifted: list[str] = []
    seats = pinned.get("seats") or []
    if not seats:
        return "FAIL", "the pipeline pin records no seat", []
    for seat in seats:
        tag = str(seat.get("seat", ""))
        route = (seat.get("serving_route") or {}).get("route") or []
        if not route:
            drifted.append(f"{tag}: the pipeline pin records no serving route")
            continue
        for hop in route:
            engine, served = str(hop.get("engine")), str(hop.get("served_model"))
            recorded = hop.get("template") or {}
            pinned_sha = recorded.get("api_show_template_sha") or (
                recorded.get("tokenizer_config_chat_template")
            )
            if engine == "omlx":
                live = _template_sha_omlx(served)
                live_sha = (live or {}).get("tokenizer_config_chat_template")
            else:
                live_sha = _template_sha(served)
            findings.append(
                {
                    "seat": tag,
                    "backend": hop.get("backend"),
                    "engine": engine,
                    "served_model": served,
                    "pinned_template_sha": pinned_sha,
                    "live_template_sha": live_sha,
                }
            )
            if live_sha is None:
                drifted.append(f"{tag}: the {engine} template for {served} is unreadable")
            elif pinned_sha and live_sha != pinned_sha:
                drifted.append(
                    f"{tag} on {hop.get('backend')}: pinned {pinned_sha}, live {live_sha}"
                )
    if drifted:
        return (
            "FAIL",
            "a serving engine's chat template moved underneath the recorded runs — "
            + "; ".join(drifted)
            + ". Every acceptance result recorded against the pin is no longer "
            "comparable; re-run the preflight pin and the acceptance suite",
            findings,
        )
    return "PASS", f"{len(seats)} seat(s) certified per engine against the pipeline pin", findings


@register(
    "compliance_seat_template_identity",
    "HH. the compliance seat's live chat template matches the one the campaign pinned",
    order=199,
)
def check_compliance_seat_template_identity() -> tuple[str, str, list[dict]]:
    # Short-circuited pre-service, BEFORE the probe rather than after it. HG
    # downgrades its verdict because its evidence is already on disk and costs
    # nothing to read; HH's evidence is a live `/api/show` per seat, so the only
    # way not to spend it is not to ask. With the stack down or a seat tag
    # uninstalled that probe FAILs and blocks a push over a template belonging
    # to a module nothing depends on yet.
    if not IN_SERVICE:
        return (
            "SKIP",
            "compliance is pre-service (IN_SERVICE=False in "
            "scripts/validation/compliance_acceptance.py) — the live seat templates "
            "are not probed, so no push waits on Ollama for them",
            [],
        )
    return _compliance_seat_template_identity()


def _newest_per_run_pin() -> dict[str, Any] | None:
    """The newest acceptance run's own pin, when one was written — what THAT
    run was actually compared against."""
    for run in sorted(_acceptance_runs(), key=lambda r: str(r["updated_at"]), reverse=True):
        per_run = ACCEPTANCE_ROOT / str(run["dir"]) / "preflight.json"
        if per_run.is_file():
            try:
                return json.loads(per_run.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return None


def _read_pin(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _select_pinned() -> tuple[dict[str, Any] | None, str]:
    """The pin HH certifies against, and the failure detail when none reads.

    Precedence, per era (PIPELINE_ALIGNMENT_V1 §P5): a pipeline-era per-run
    pin outranks everything; else the pipeline-era campaign pin; else a
    native per-run pin; else the native campaign pin. A native pin never
    shadows a pipeline one — its shas certify the fallback engine only.
    """
    per_run = _newest_per_run_pin()
    candidates: list[tuple[Path, dict[str, Any] | None]] = []
    if (per_run or {}).get("path") == "pipeline":
        candidates.append((CAMPAIGN_PIN_V2, per_run))
    elif CAMPAIGN_PIN_V2.is_file():
        candidates.append((CAMPAIGN_PIN_V2, _read_pin(CAMPAIGN_PIN_V2)))
    elif per_run is not None:
        candidates.append((CAMPAIGN_PIN, per_run))
    elif CAMPAIGN_PIN.is_file():
        candidates.append((CAMPAIGN_PIN, _read_pin(CAMPAIGN_PIN)))
    for _path, pinned in candidates:
        if pinned is not None:
            return pinned, ""
    return None, (
        f"no campaign pin at {CAMPAIGN_PIN_V2} (preferred) or {CAMPAIGN_PIN} — run "
        "`uv run python -m tests.wfe.compliance_preflight --pin-v2 "
        "reports/compliance/SETTINGS_PREFLIGHT_V2.json` and commit it"
    )


def _compliance_seat_template_identity() -> tuple[str, str, list[dict]]:
    pinned, missing = _select_pinned()
    if pinned is None:
        return "FAIL", missing, []

    if pinned.get("path") == "pipeline":
        return _pipeline_pin_template_identity(pinned)

    from tests.wfe.settings_audit import _template_sha

    findings: list[dict[str, Any]] = []
    drifted: list[str] = []
    seats = (pinned or {}).get("seats") or []
    if not seats:
        return "FAIL", "the campaign pin records no seat", []
    for seat in seats:
        tag = str(seat.get("seat", ""))
        recorded = seat.get("template_sha")
        live = _template_sha(tag)
        findings.append({"seat": tag, "pinned_template_sha": recorded, "live_template_sha": live})
        if live is None:
            drifted.append(f"{tag}: the live template is unreadable (is the tag still installed?)")
        elif recorded and live != recorded:
            drifted.append(f"{tag}: pinned {recorded}, live {live}")
    if drifted:
        return (
            "FAIL",
            "the compliance seat's chat template moved underneath the recorded runs — "
            + "; ".join(drifted)
            + ". Every acceptance result recorded against the pinned sha is no longer "
            "comparable; re-run the preflight and the acceptance suite",
            findings,
        )
    return "PASS", f"{len(seats)} seat template sha(s) match the pin", findings
