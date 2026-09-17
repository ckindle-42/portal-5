#!/usr/bin/env python3
"""The one live acceptance instrument for CIP-007-6. Live only.

TASK_COMPLIANCE_PROVE_CIP_007_V1 §P3. Seven live harnesses, 2,513 lines, each
abandoned the day the next generation began, and the mature one asserts a
retiring engine's vocabulary over 22 synthetic fixtures — documents that do not
exist. This one is deliberately narrow, and every narrowing is a lesson from one
of those seven:

* **Live only.** No unit test is evidence that the product works. Each of the
  four defects the last live readings found passed every unit test.
* **The DEPLOYED service**, at the port `config/portal.yaml` actually declares,
  discovered rather than hardcoded.
* **Artifacts under the git rev**, in the repo. A dated path in ``/tmp`` is how a
  run stops being evidence.
* **APPLIED settings, never requested ones.** Every row records the window the
  runner loaded, the prompt tokens it evaluated and the headroom that left.
* **A truncation guard per call.** Headroom ≤ 0, or a prompt at the ceiling,
  fails the run with that reason. A case must never pass on a truncated prompt.
* **An adapter per answer path.** `reader` and `legacy` run the same cases, so
  re-pointing `compliance_gaps` is measurable rather than destructive, and the
  next redesign costs an adapter rather than the suite.
* **A failing case names the assertion it failed**, so a failure can be
  attributed to a §P5 rung without a human re-reading the transcript.

Usage:
  uv run python scripts/compliance_acceptance.py --runs 3
  uv run python scripts/compliance_acceptance.py --case interval --runs 1
  uv run python scripts/compliance_acceptance.py --adapter legacy --runs 1
  uv run python scripts/compliance_acceptance.py --seat <tag> --seat <tag>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO = Path(__file__).resolve().parents[1]
CASES_PATH = REPO / "config" / "compliance" / "cases" / "cip_007_6.yaml"
LOCK = Path("/tmp/portal5-compliance-acceptance.lock")

sys.path.insert(0, str(REPO))


# ── the deployed service, discovered ────────────────────────────────────────


def mcp_base_url() -> str:
    """The compliance MCP's port, from ``config/portal.yaml``'s own fleet roster.

    Hardcoding it is how a health check ends up pointed at a port that serves
    something else entirely, and a stage that tests nothing reports success.
    """
    portal = yaml.safe_load((REPO / "config" / "portal.yaml").read_text()) or {}
    for entry in portal.get("mcp_fleet") or []:
        if str(entry.get("module") or entry.get("id")) == "compliance":
            return f"http://localhost:{int(entry['port'])}"
    raise RuntimeError("config/portal.yaml declares no compliance MCP in mcp_fleet")


def invoke(client: httpx.Client, base_url: str, tool: str, **arguments: Any) -> dict[str, Any]:
    response = client.post(f"{base_url}/tools/{tool}", json={"arguments": arguments})
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise TypeError(f"{tool} returned {type(body).__name__}, not an object")
    return body


# ── what each citation IS, which is what "both sides" means ─────────────────


def population_sides(ref: str) -> dict[str, str]:
    """``section_id -> side`` for the case's own scope.

    Side cannot be read off the id prefix: an operator NOTE is stored as a
    ``csection-`` id, so a prefix test would report the operator's own recorded
    decision as regulatory material.
    """
    from portal.modules.compliance.core import requirement_scope
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        population = requirement_scope.population(repo, ref)
        return {sid: str(e.get("side", "")) for sid, e in population["sections"].items()}
    finally:
        repo.close()


def resolve_sides(citations: list[dict[str, Any]], sides: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in citations:
        ref = str(entry.get("cited_ref", ""))
        side = sides.get(ref, "")
        if not side and entry.get("resolved"):
            # outside the population: fall back to what it resolved to
            resolves = str(entry.get("resolves_to", "")).lower()
            jurisdiction = str(entry.get("jurisdiction", "")).lower()
            if "operator" in resolves or jurisdiction == "internal":
                side = "operator"
            elif resolves or jurisdiction:
                side = "regulatory"
            side = f"{side} (outside scope)" if side else "unclassified"
        out.append({**entry, "side": side or "unresolvable"})
    return out


# ── the checks ──────────────────────────────────────────────────────────────
#
# Semantic, not string-equality: a `concept` passes on any member of a phrase
# FAMILY, a `quantity` uses the reader's own number extraction (which handles
# "thirty-five (35) calendar days"), and a citation check is evaluated against
# RESOLVED citations with their side, not against the raw text of the answer.


def _normalise(text: str) -> str:
    from portal.modules.compliance.core.reader import _DASHES

    return " ".join(text.translate(_DASHES).lower().split())


def _quantity_stated(answer: str, number: int, unit: str) -> bool:
    from portal.modules.compliance.core.reader import _quantity_in

    return _quantity_in(str(number), unit, answer)


def _concept(text: str, phrases: list[str]) -> str:
    for phrase in phrases:
        if _normalise(phrase) in text:
            return phrase
    return ""


def check_case(case: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Every assertion for one case, each naming itself when it fails."""
    answer = str(payload.get("answer", "") or "")
    text = _normalise(answer)
    closure = payload.get("closure_receipt") or {}
    sides = population_sides(str(case["ref"]))
    citations = resolve_sides(
        list((payload.get("verification") or {}).get("citations") or []), sides
    )
    resolved = {c["cited_ref"] for c in citations if c.get("resolved")}
    rows: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        rows.append({"assertion": name, "ok": bool(ok), "detail": detail})

    required = case.get("required_citations") or {}
    for ref in required.get("regulatory") or []:
        add(f"required_citation:{ref}", ref in resolved, "cited" if ref in resolved else "absent")
    any_of = required.get("operator_any") or []
    if any_of:
        hit = [r for r in any_of if r in resolved]
        add("required_citation:operator_any", bool(hit), hit or f"none of {any_of}")
    minimum = required.get("operator_min")
    if minimum:
        operator = [c["cited_ref"] for c in citations if c["side"].startswith("operator")]
        add(f"operator_citations>={minimum}", len(operator) >= minimum, operator)

    for ref in case.get("forbidden_citations") or []:
        add(f"forbidden_citation:{ref}", ref not in resolved, "cited" if ref in resolved else "ok")

    # Both sides, always. An answer about the operator's posture written only
    # from regulatory text is an answer about the standard.
    operator_cited = [c["cited_ref"] for c in citations if c["side"].startswith("operator")]
    add("cites_the_operator_side", bool(operator_cited), operator_cited)

    for spec in case.get("must_state") or []:
        kind = spec["kind"]
        if kind == "quantity":
            ok = _quantity_stated(answer, int(spec["number"]), str(spec["unit"]))
            add(f"must_state:{spec['id']}", ok, f"{spec['number']} {spec['unit']}")
        elif kind == "concept":
            hit = _concept(text, list(spec["any_of"]))
            add(f"must_state:{spec['id']}", bool(hit), hit or f"none of {spec['any_of']}")
        elif kind == "concept_all":
            missing = [group for group in spec["all_of"] if not _concept(text, list(group))]
            add(f"must_state:{spec['id']}", not missing, missing or "all present")
        else:
            add(f"must_state:{spec['id']}", False, f"unknown check kind {kind!r}")

    for spec in case.get("must_not_state") or []:
        hit = _concept(text, list(spec["any_of"]))
        add(f"must_not_state:{spec['id']}", not hit, hit or "absent")

    minimum_calls = int(case.get("tool_calls_min") or 0)
    made = int(closure.get("model_tool_calls") or 0)
    add(f"tool_calls>={minimum_calls}", made >= minimum_calls, made)

    add("reading_did_not_fail", not payload.get("failed"), payload.get("failure", ""))
    return rows


def truncation_guard(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """A case must never pass on a truncated prompt.

    On Ollama 0.34.0 an oversized prompt is refused rather than truncated, so the
    guard has two jobs: catch a prompt sitting AT the ceiling (the last state
    before a refusal, and the state where the next turn dies), and catch a window
    the runner did not actually serve.
    """
    fit = payload.get("context_fit") or {}
    applied = payload.get("applied_settings") or {}
    rows: list[dict[str, Any]] = []
    window = int(fit.get("num_ctx") or 0)
    prompt_tokens = int(fit.get("actual_prompt_tokens") or 0)
    headroom = fit.get("headroom_tokens")
    served = applied.get("num_ctx_applied")

    # An unevaluable guard is a FAILURE, never a skip. Measured on the live
    # `parent` cell: the call died with an Ollama HTTP 500 after 1,522 s, so the
    # payload carried no `context_fit` and no `applied_settings` at all — and
    # every one of the four guards below read its missing input as a zero and
    # reported OK. A truncation guard that passes when nothing was measured is
    # worse than no guard, because it certifies the one run that has no
    # evidence. This is the same rule the module applies elsewhere and the same
    # failure this task exists to stop.
    if payload.get("error") or not fit or not applied:
        return [
            {
                "assertion": "the call produced measurements to guard",
                "ok": False,
                "detail": {
                    "error": payload.get("error", ""),
                    "context_fit": bool(fit),
                    "applied_settings": bool(applied),
                },
            }
        ]

    rows.append(
        {
            "assertion": "applied_num_ctx == requested",
            "ok": not served or int(served) == window,
            "detail": {"requested": window, "applied": served},
        }
    )
    rows.append(
        {
            "assertion": "headroom > 0",
            "ok": headroom is None or int(headroom) > 0,
            "detail": headroom,
        }
    )
    rows.append(
        {
            "assertion": "prompt below the ceiling",
            "ok": not (window and prompt_tokens and prompt_tokens >= window),
            "detail": {"prompt_eval_count": prompt_tokens, "num_ctx": window},
        }
    )
    rows.append(
        {
            "assertion": "runner did not refuse the prompt",
            "ok": "context ceiling" not in str(payload.get("failure", "")),
            "detail": payload.get("failure", ""),
        }
    )
    return rows


# ── the two answer paths ────────────────────────────────────────────────────


def adapter_reader(
    client: httpx.Client, base_url: str, case: dict[str, Any], seat: str
) -> dict[str, Any]:
    """The agentic reader, through `compliance_ask` on the deployed service.

    ``store=False`` is the only place this differs from a production reading,
    and it is the difference between three observations and one observation
    repeated into its own input. `compliance_ask` projects an answer into the
    corpus as a derived source and proposes candidate links from it; the next
    reading of the same question then receives its predecessor's answer through
    `compliance_links`. Measured on Part 2.4: run 2's prompt grew by 105 tokens
    over run 1's and PASSED a case run 1 failed, at temperature 0.0. The receipt
    is still retained — what is suppressed is projection, not the record.
    """
    started = time.monotonic()
    payload = invoke(
        client,
        base_url,
        "compliance_ask",
        question=str(case["question"]).strip(),
        ref=str(case["ref"]),
        model=seat,
        store=False,
    )
    payload["_wall_s"] = round(time.monotonic() - started, 1)
    return payload


def adapter_legacy(
    client: httpx.Client, base_url: str, case: dict[str, Any], seat: str
) -> dict[str, Any]:
    """The retiring coverage path, through `compliance_gaps`, run on the SAME
    cases so F1's re-point is measurable rather than destructive.

    It answers in coverage rows, not prose, so the semantic checks do not apply
    to it. What IS comparable is recorded: which Parts it covered and which
    section ids it put in front of a conclusion.
    """
    ref = str(case["ref"])
    standard = ref.split(" R")[0]
    requirement = ref[len(standard) :].strip()
    started = time.monotonic()
    start = invoke(
        client,
        base_url,
        "compliance_gaps",
        standard=standard,
        requirement=requirement,
        operation="start",
    )
    run_id = str(start.get("run_id", ""))
    result: dict[str, Any] = start
    # The run's own vocabulary, read from `assessment_runs.TERMINAL_STATES`
    # rather than guessed: the key is `status`, not `state`, and INTERRUPTED is
    # terminal too — a poller that waits for "finished" waits for ever.
    terminal = {"COMPLETE", "FAILED", "CANCELLED", "INTERRUPTED"}
    deadline = time.monotonic() + 3600
    last_status: dict[str, Any] = {}
    while run_id and time.monotonic() < deadline:
        time.sleep(15)
        last_status = invoke(client, base_url, "compliance_gaps", operation="status", run_id=run_id)
        if str(last_status.get("status", "")).upper() in terminal:
            result = invoke(client, base_url, "compliance_gaps", operation="result", run_id=run_id)
            break
    return {
        "adapter": "legacy",
        "ref": ref,
        "run_id": run_id,
        "start": start,
        "last_status": last_status,
        "result": result,
        "_wall_s": round(time.monotonic() - started, 1),
    }


def legacy_comparable(result: dict[str, Any]) -> dict[str, Any]:
    """The part of a coverage answer that can be compared with a reading: which
    identities it spoke about, and which section ids it rested on."""
    rows = (result.get("result") or {}).get("rows") or []
    blob = json.dumps(result, default=str)
    return {
        "requirements_covered": sorted(
            {str(r.get("requirement") or r.get("requirement_id") or "") for r in rows} - {""}
        ),
        "section_ids": sorted(set(re.findall(r"\b(?:c|i)section-[0-9a-f]{20}", blob))),
        "row_count": len(rows),
    }


# ── the runner ──────────────────────────────────────────────────────────────


def environment(base_url: str) -> dict[str, Any]:
    from tests.wfe.compliance_preflight import free_memory_mb

    def get(path: str) -> Any:
        try:
            with httpx.Client(timeout=10) as client:
                return client.get(f"http://localhost:11434{path}").json()
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            return {"error": str(exc)}

    return {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ollama_version": (get("/api/version") or {}).get("version"),
        "ollama_ps": (get("/api/ps") or {}).get("models"),
        "free_memory_mb": free_memory_mb(),
        "mcp_base_url": base_url,
    }


def run_cell(
    client: httpx.Client,
    base_url: str,
    case: dict[str, Any],
    seat: str,
    adapter: str,
    run_index: int,
    out_dir: Path,
) -> dict[str, Any]:
    name = f"{adapter}__{_slug(seat)}__{case['id']}__run{run_index}"
    path = out_dir / f"{name}.json"
    exit_path = out_dir / f"{name}.exit"
    if exit_path.is_file() and path.is_file():
        record = json.loads(path.read_text())
        record["resumed"] = True
        return record

    before = environment(base_url)
    record: dict[str, Any] = {
        "cell": name,
        "adapter": adapter,
        "seat": seat,
        "case": case["id"],
        "ref": case["ref"],
        "question": str(case["question"]).strip(),
        "run_index": run_index,
        "environment_before": before,
    }
    try:
        if adapter == "legacy":
            payload = adapter_legacy(client, base_url, case, seat)
            record["payload"] = payload
            record["comparable"] = legacy_comparable(payload)
            record["checks"] = []
            record["guard"] = []
            # `honest-BLOCKED` is an answer, not a crash: the legacy path
            # refuses when the asset scope is undeclared, and that refusal is
            # exactly the kind of thing the comparison exists to surface.
            outcome = payload.get("result") or {}
            record["passed"] = not outcome.get("error")
            record["legacy_status"] = outcome.get("status") or payload.get("last_status", {}).get(
                "status"
            )
        else:
            payload = adapter_reader(client, base_url, case, seat)
            record["payload"] = payload
            record["prompt_version"] = payload.get("prompt_version")
            record["prompt_sha"] = payload.get("prompt_sha")
            record["applied_settings"] = payload.get("applied_settings")
            record["context_fit"] = payload.get("context_fit")
            record["thinking_chars"] = payload.get("thinking_chars")
            record["latency"] = payload.get("latency")
            record["closure_receipt"] = payload.get("closure_receipt")
            record["citations"] = resolve_sides(
                list((payload.get("verification") or {}).get("citations") or []),
                population_sides(str(case["ref"])),
            )
            record["comparable"] = {
                "requirements_covered": [str(case["ref"])],
                "section_ids": sorted(
                    {str(c["cited_ref"]) for c in record["citations"] if c.get("resolved")}
                ),
                "row_count": 0,
            }
            guard = truncation_guard(payload)
            record["guard"] = guard
            record["checks"] = check_case(case, payload) if all(g["ok"] for g in guard) else []
            record["passed"] = all(g["ok"] for g in guard) and all(
                c["ok"] for c in record["checks"]
            )
    except Exception as exc:  # noqa: BLE001 - a transport failure is a recorded result
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["passed"] = False

    record["environment_after"] = environment(base_url)
    record["failed_assertions"] = [
        row["assertion"]
        for row in [*record.get("guard", []), *record.get("checks", [])]
        if not row["ok"]
    ]
    path.write_text(json.dumps(record, indent=1, default=str))
    exit_path.write_text("0\n" if record["passed"] else "1\n")
    return record


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")


def write_status(out_dir: Path, rev: str, rows: list[dict[str, Any]]) -> None:
    (out_dir / "status.json").write_text(
        json.dumps(
            {
                "git_head": rev,
                "dirty_paths": len(
                    subprocess.check_output(
                        ["git", "-C", str(REPO), "status", "--porcelain"], text=True
                    ).splitlines()
                ),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "cells": [
                    {
                        "cell": r["cell"],
                        "passed": r.get("passed"),
                        "failed_assertions": r.get("failed_assertions", []),
                        "error": r.get("error", ""),
                    }
                    for r in rows
                ],
            },
            indent=1,
        )
    )


def main() -> int:
    from portal.modules.compliance.core.runtime_config import reading_seat

    parser = argparse.ArgumentParser()
    parser.add_argument("--seat", action="append", default=[])
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--adapter", action="append", default=[], choices=["reader", "legacy"])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--http-timeout", type=float, default=5400.0)
    parser.add_argument("--out", default="")
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="skip the §P0 seat pin (for a smoke run against an already-pinned seat)",
    )
    args = parser.parse_args()

    # One worker at a time: a second live suite invalidates both, and the
    # machine cannot hold two 27B seats without evicting one mid-run.
    if LOCK.exists():
        owner = LOCK.read_text().strip()
        try:
            os.kill(int(owner), 0)
        except (ValueError, ProcessLookupError):
            LOCK.unlink(missing_ok=True)
        else:
            print(f"ABORT: acceptance worker already running (pid {owner})")
            return 2
    LOCK.write_text(str(os.getpid()))

    try:
        manifest = yaml.safe_load(CASES_PATH.read_text())
        cases = [c for c in manifest["cases"] if not args.case or c["id"] in args.case]
        seats = args.seat or [reading_seat()]
        adapters = args.adapter or ["reader"]
        rev = subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
        ).strip()
        out_dir = Path(args.out) if args.out else REPO / "reports/compliance/acceptance" / rev
        out_dir.mkdir(parents=True, exist_ok=True)
        base_url = mcp_base_url()

        (out_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "git_head": rev,
                    "cases": [c["id"] for c in cases],
                    "seats": seats,
                    "adapters": adapters,
                    "runs": args.runs,
                    "mcp_base_url": base_url,
                    "case_meta": manifest["meta"],
                },
                indent=1,
            )
        )

        # §P0.5/§P0.6: the campaign is pinned BEFORE the first case, and a seat
        # that is not GO does not run. The pin is what a later check compares
        # the live template sha against, so a run whose template moved
        # underneath it is detectable rather than merely wrong.
        if not args.no_preflight:
            from tests.wfe.compliance_preflight import run as preflight_run

            pin = preflight_run(seats)
            (out_dir / "preflight.json").write_text(json.dumps(pin, indent=1, default=str))
            blocked = [s for s in pin["seats"] if not s["go"]]
            if blocked:
                for seat in blocked:
                    print(f"NO-GO  {seat['seat']}: {'; '.join(seat['no_go_reasons'])}")
                print("honest-BLOCKED: §P0.6 go/no-go failed; no case was run")
                return 3

        rows: list[dict[str, Any]] = []
        with httpx.Client(timeout=args.http_timeout) as client:
            for adapter in adapters:
                for seat in seats:
                    for case in cases:
                        for index in range(1, args.runs + 1):
                            record = run_cell(client, base_url, case, seat, adapter, index, out_dir)
                            rows.append(record)
                            mark = "PASS" if record.get("passed") else "FAIL"
                            print(
                                f"{mark}  {record['cell']}  "
                                f"{record.get('failed_assertions') or record.get('error', '')}",
                                flush=True,
                            )
                            write_status(out_dir, rev, rows)
        print(f"\nartifacts: {out_dir}")
        return 0 if all(r.get("passed") for r in rows) else 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
