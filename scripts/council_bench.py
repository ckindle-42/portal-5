"""Quality-and-time bench for the public ``auto-council`` review path.

The set is fixed and human-labelled: ``tests/fixtures/council/cases.json`` holds
the review submissions, the outcome a correct review must reach, and the key
issue it must name. This script sends one submission at a time through the
pipeline (``model: auto-council``) and scores the response mechanically — no
LLM-as-judge and no live calls from the unit tests.

What is recorded per case: the coded decision, whether it matches the label,
whether the key issue was named (and where), the seats' votes, per-stage timing
when the pipeline exposes it, and wall time. The summary reports accuracy,
key-issue recall, and median/p90 wall time for the configuration under test.

Configurations
--------------
One invocation measures one configuration. Pass the council override as JSON
(inline or ``@path``); the runner sends it in the request body under
``portal_council_config``, which the council path is expected to merge over the
workspace's ``council`` block. Without an override the workspace default is
measured. The runner never assumes the override took effect: if the response
does not echo the requested keys it reports ``override_status`` as
``unverified`` (no echo) or ``not_applied`` (an echo with different values).

Per-stage timing
----------------
The council's per-stage metadata is read tolerantly. A stage list is accepted under
``portal_council.timings``, ``portal_council.stage_timings`` or
``portal_council.stages`` (as a list, or as a dict containing ``stages`` /
``seats`` / ``reviewers`` plus an optional ``synthesizer``), or per reviewer in
``portal_council.reviewers``. Stage keys are normalised to ``role``,
``member_id``, ``model``, ``cold_load_s``, ``prefill_s``, ``decode_s``,
``tokens`` and ``wall_s``; common spellings are accepted. A
``portal_timings`` block, if present, supplies the total only.

Answers stay out of the request
-------------------------------
Only ``case.submission`` is sent. The case id, category, expected outcome, key
issue and markers never enter a request, and the fixture loader rejects a case
whose markers already appear in its own submission — a marker present in the
material cannot distinguish a review that found the issue from one that
paraphrased the prompt.

Usage
-----
    uv run python scripts/council_bench.py --json-out reports/council.json
    uv run python scripts/council_bench.py --config '{"mode": "early_quorum"}' --label early-quorum
    uv run python scripts/council_bench.py --json-out reports/council.json --append \\
        --config '{"mode": "single_model", "single_model": {"model": "qwen3.8:27b"}}'
    uv run python scripts/council_bench.py --dry-run --limit 1   # no network call

Exit status is 1 when any case errored, so a broken run is visible to a caller.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = REPO_ROOT / "tests/fixtures/council/cases.json"
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline-key")
DEFAULT_TIMEOUT_S = float(os.environ.get("COUNCIL_BENCH_TIMEOUT", "900"))
WORKSPACE = "auto-council"
OVERRIDE_KEY = "portal_council_config"

_OUTCOMES = frozenset({"SUPPORT", "REVISE", "REJECT"})
_DECISIONS = frozenset({"SUPPORT", "REVISE", "REJECT", "ESCALATE"})
_ACCEPTED_OUTCOMES = _OUTCOMES | {"ESCALATE"}
_VOTE_NAMES = ("SUPPORT", "REVISE", "REJECT")

_STAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "cold_load_s": ("cold_load_s", "cold_load", "load_s", "model_load_s", "cold_start_s"),
    "prefill_s": ("prefill_s", "prefill", "prompt_eval_s", "prompt_s"),
    "decode_s": ("decode_s", "decode", "eval_s", "generation_s", "output_s"),
    "tokens": ("tokens", "output_tokens", "completion_tokens", "eval_count", "decode_tokens"),
    "wall_s": ("wall_s", "total_s", "elapsed_s", "duration_s", "latency_s"),
}


@dataclass(frozen=True)
class Case:
    """One labelled review case."""

    id: str
    category: str
    submission: str
    expected_outcome: str
    key_issue: str
    key_issue_markers: tuple[str, ...]
    acceptable_outcomes: tuple[str, ...] = ()

    @property
    def accepted(self) -> tuple[str, ...]:
        """Outcomes scored as correct; defaults to the single expected outcome."""
        return self.acceptable_outcomes or (self.expected_outcome,)


# ── Fixture loading ──────────────────────────────────────────────────────────


def _normalise(text: str) -> str:
    """Lowercase, treat hyphens as spaces, and collapse whitespace."""
    return " ".join(text.lower().replace("-", " ").split())


def _case_from_dict(raw: dict[str, Any], index: int) -> Case:
    where = f"case #{index}"
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected an object")
    case_id = str(raw.get("id") or "").strip()
    if not case_id:
        raise ValueError(f"{where}: missing id")
    submission = raw.get("submission")
    if not isinstance(submission, str) or not submission.strip():
        raise ValueError(f"case {case_id}: missing submission")
    expected = str(raw.get("expected_outcome") or "").upper()
    if expected not in _OUTCOMES:
        raise ValueError(f"case {case_id}: expected_outcome must be one of {sorted(_OUTCOMES)}")
    markers = raw.get("key_issue_markers")
    if not isinstance(markers, list) or not markers:
        raise ValueError(f"case {case_id}: key_issue_markers must be a non-empty list")
    cleaned = tuple(str(marker).lower().strip() for marker in markers)
    if any(not marker for marker in cleaned):
        raise ValueError(f"case {case_id}: empty key-issue marker")
    accepted_raw = raw.get("acceptable_outcomes") or [expected]
    if not isinstance(accepted_raw, list):
        raise ValueError(f"case {case_id}: acceptable_outcomes must be a list")
    accepted = tuple(str(item).upper() for item in accepted_raw)
    if expected not in accepted:
        raise ValueError(f"case {case_id}: acceptable_outcomes must include expected_outcome")
    if set(accepted) - _ACCEPTED_OUTCOMES:
        raise ValueError(f"case {case_id}: unknown acceptable outcome")
    body = _normalise(submission)
    leaked = [marker for marker in cleaned if _normalise(marker) in body]
    if leaked:
        raise ValueError(f"case {case_id}: markers already appear in the submission: {leaked}")
    return Case(
        id=case_id,
        category=str(raw.get("category") or "uncategorised"),
        submission=submission.strip(),
        expected_outcome=expected,
        key_issue=str(raw.get("key_issue") or "").strip(),
        key_issue_markers=cleaned,
        acceptable_outcomes=accepted,
    )


def load_cases(path: str | Path = DEFAULT_CASES) -> list[Case]:
    """Load and validate the labelled set; unknown fields are ignored."""
    payload = json.loads(Path(path).read_text())
    raw_cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{path}: expected a non-empty 'cases' list")
    cases = [_case_from_dict(raw, index) for index, raw in enumerate(raw_cases, start=1)]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate case ids")
    return cases


# ── Request building ─────────────────────────────────────────────────────────


def build_request(case: Case, override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the public-path request. Only the submission is sent, never a label."""
    body: dict[str, Any] = {
        "model": WORKSPACE,
        "stream": False,
        "messages": [{"role": "user", "content": case.submission}],
    }
    if override:
        body[OVERRIDE_KEY] = override
    return body


# ── Scoring ──────────────────────────────────────────────────────────────────


def _contains_any(parts: list[str], markers: tuple[str, ...]) -> bool:
    text = _normalise(" ".join(parts))
    return any(_normalise(marker) in text for marker in markers)


def _finding_text(finding: dict[str, Any]) -> str:
    parts = [str(finding.get("claim") or ""), str(finding.get("action") or "")]
    evidence = finding.get("evidence")
    if isinstance(evidence, list):
        parts.extend(str(item) for item in evidence)
    elif evidence:
        parts.append(str(evidence))
    return " ".join(parts)


def key_issue_hit(
    case: Case,
    reviewers: list[dict[str, Any]],
    synthesis: str,
) -> tuple[bool, str, bool]:
    """Return ``(hit, source, evidence_backed)`` for the case's key issue."""
    everything: list[str] = []
    backed: list[str] = []
    for reviewer in reviewers:
        findings = reviewer.get("findings")
        for finding in findings if isinstance(findings, list) else []:
            if not isinstance(finding, dict):
                continue
            text = _finding_text(finding)
            everything.append(text)
            if finding.get("evidence"):
                backed.append(text)
        missing = reviewer.get("missing_evidence")
        if isinstance(missing, list):
            everything.extend(str(item) for item in missing)
        everything.append(str(reviewer.get("strongest_objection") or ""))
        conditions = reviewer.get("conditions_to_change")
        if isinstance(conditions, list):
            everything.extend(str(item) for item in conditions)
    markers = case.key_issue_markers
    if _contains_any(everything, markers):
        return True, "reviewers", _contains_any(backed, markers)
    if _contains_any([synthesis], markers):
        return True, "synthesis", False
    return False, "", False


def _seat(reviewer: dict[str, Any]) -> dict[str, Any]:
    recommendation = str(reviewer.get("recommendation") or "ABSTAIN").upper()
    valid = bool(reviewer.get("valid"))
    return {
        "member_id": str(reviewer.get("member_id") or ""),
        "model": str(reviewer.get("model") or ""),
        "recommendation": recommendation,
        "valid": valid,
        "participated": valid and recommendation != "ABSTAIN",
        "error": str(reviewer.get("error") or ""),
    }


def _synthesis(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _empty_record(
    case: Case, wall_s: float, message: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": case.id,
        "category": case.category,
        "expected_outcome": case.expected_outcome,
        "acceptable_outcomes": list(case.accepted),
        "decision": "",
        "outcome_ok": False,
        "key_issue": case.key_issue,
        "key_issue_hit": False,
        "key_issue_source": "",
        "key_issue_evidence_backed": False,
        "votes": dict.fromkeys(_VOTE_NAMES, 0),
        "participation": None,
        "participating": 0,
        "roster": 0,
        "dissent": [],
        "seats": [],
        "wall_s": round(wall_s, 3),
        "timings": extract_timings(payload),
        "error": message,
    }


def score_case(case: Case, payload: dict[str, Any], wall_s: float) -> dict[str, Any]:
    """Score one response against its label; malformed responses are misses."""
    portal = payload.get("portal_council")
    if not isinstance(portal, dict):
        return _empty_record(case, wall_s, "response has no portal_council block", payload)
    aggregate = portal.get("aggregate")
    if not isinstance(aggregate, dict) or aggregate.get("decision") not in _DECISIONS:
        return _empty_record(case, wall_s, "response has no valid council decision", payload)
    reviewers = [
        reviewer for reviewer in portal.get("reviewers") or [] if isinstance(reviewer, dict)
    ]
    decision = str(aggregate["decision"])
    hit, source, backed = key_issue_hit(case, reviewers, _synthesis(payload))
    votes = aggregate.get("votes")
    votes = votes if isinstance(votes, dict) else {}
    return {
        "id": case.id,
        "category": case.category,
        "expected_outcome": case.expected_outcome,
        "acceptable_outcomes": list(case.accepted),
        "decision": decision,
        "outcome_ok": decision in case.accepted,
        "key_issue": case.key_issue,
        "key_issue_hit": hit,
        "key_issue_source": source,
        "key_issue_evidence_backed": backed,
        "votes": {name: int(votes.get(name) or 0) for name in _VOTE_NAMES},
        "participation": aggregate.get("participation"),
        "participating": int(aggregate.get("participating") or 0),
        "roster": int(aggregate.get("roster") or 0),
        "dissent": [str(item) for item in aggregate.get("dissent") or []],
        "seats": [_seat(reviewer) for reviewer in reviewers],
        "wall_s": round(wall_s, 3),
        "timings": extract_timings(payload),
        "error": "",
    }


# ── Per-stage timing extraction ──────────────────────────────────────────────


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _has_stage_fields(raw: dict[str, Any]) -> bool:
    return any(name in raw for names in _STAGE_FIELDS.values() for name in names)


def _normalise_stage(raw: dict[str, Any], default_role: str) -> dict[str, Any]:
    stage: dict[str, Any] = {
        "role": default_role,
        "member_id": None,
        "model": None,
        "cold_load_s": None,
        "prefill_s": None,
        "decode_s": None,
        "tokens": None,
        "wall_s": None,
    }
    for field, names in _STAGE_FIELDS.items():
        for name in names:
            if name in raw:
                stage[field] = _number(raw[name])
                break
    stage["role"] = str(raw.get("role") or default_role)
    member = raw.get("member_id") or raw.get("seat") or raw.get("id")
    stage["member_id"] = str(member) if member else None
    model = raw.get("model")
    stage["model"] = str(model) if model else None
    return stage


def _stage_list(container: Any) -> tuple[list[dict[str, Any]], float | None]:
    """Normalise one timing container into ``(stages, total_wall_s)``."""
    if isinstance(container, list):
        stages = [_normalise_stage(item, "unknown") for item in container if isinstance(item, dict)]
        return stages, None
    if not isinstance(container, dict):
        return [], None
    total = _number(container.get("total_s") or container.get("wall_s"))
    for key in ("stages", "seats", "reviewers"):
        listed = container.get(key)
        if isinstance(listed, list):
            stages = [
                _normalise_stage(item, "reviewer") for item in listed if isinstance(item, dict)
            ]
            synthesizer = container.get("synthesizer")
            if isinstance(synthesizer, dict):
                stages.append(_normalise_stage(synthesizer, "synthesizer"))
            return stages, total
    stages = [
        _normalise_stage(value, name)
        for name, value in container.items()
        if isinstance(value, dict)
    ]
    return stages, total


def extract_timings(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the council's per-stage timings in one normalised shape, if present."""
    portal = payload.get("portal_council")
    portal = portal if isinstance(portal, dict) else {}
    total_only: tuple[str, float] | None = None
    for key in ("timings", "stage_timings", "stages"):
        container = portal.get(key)
        stages, total = _stage_list(container)
        if stages:
            return {
                "source": f"portal_council.{key}",
                "stages": stages,
                "total_wall_s": total,
            }
        if total is not None and total_only is None:
            total_only = (f"portal_council.{key}", total)
    reviewer_stages = [
        _normalise_stage(reviewer, "reviewer")
        for reviewer in portal.get("reviewers") or []
        if isinstance(reviewer, dict) and _has_stage_fields(reviewer)
    ]
    if reviewer_stages:
        return {
            "source": "portal_council.reviewers",
            "stages": reviewer_stages,
            "total_wall_s": total_only[1] if total_only else None,
        }
    if total_only is not None:
        return {"source": total_only[0], "stages": [], "total_wall_s": total_only[1]}
    engine = payload.get("portal_timings")
    total = (
        _number(engine.get("total_s") or engine.get("wall_s")) if isinstance(engine, dict) else None
    )
    return {
        "source": "portal_timings" if total is not None else "",
        "stages": [],
        "total_wall_s": total,
    }


# ── Aggregation ──────────────────────────────────────────────────────────────


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (``p`` in (0, 100]); no interpolation."""
    if not values:
        return None
    if not 0 < p <= 100:
        raise ValueError("p must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(p / 100 * len(ordered))
    return ordered[max(0, rank - 1)]


def _rate_block(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    walls = [float(record["wall_s"]) for record in records]
    return {
        "cases": total,
        "accuracy": round(sum(record["outcome_ok"] for record in records) / total, 3),
        "key_issue_recall": round(sum(record["key_issue_hit"] for record in records) / total, 3),
        "median_wall_s": round(statistics.median(walls), 2),
        "p90_wall_s": round(percentile(walls, 90) or 0.0, 2),
        "errors": sum(bool(record["error"]) for record in records),
    }


def _seat_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, dict[str, Any]] = {}
    for record in records:
        for seat in record["seats"]:
            entry = stats.setdefault(
                seat["member_id"],
                {"appearances": 0, "participated": 0, "invalid": 0, "votes": {}},
            )
            entry["appearances"] += 1
            entry["participated"] += int(seat["participated"])
            entry["invalid"] += int(not seat["valid"])
            if seat["recommendation"] in _VOTE_NAMES:
                votes = entry["votes"]
                votes[seat["recommendation"]] = votes.get(seat["recommendation"], 0) + 1
    for entry in stats.values():
        entry["participation_rate"] = round(entry["participated"] / max(1, entry["appearances"]), 3)
    return dict(sorted(stats.items()))


def summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Accuracy, key-issue recall, and median/p90 wall time for one configuration."""
    if not records:
        raise ValueError("no cases were scored")
    total = len(records)
    walls = [float(record["wall_s"]) for record in records]
    buckets: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        buckets.setdefault(record["category"], []).append(record)
    by_category = {category: _rate_block(bucket) for category, bucket in sorted(buckets.items())}
    return {
        "cases": total,
        "accuracy": round(sum(record["outcome_ok"] for record in records) / total, 3),
        "key_issue_recall": round(sum(record["key_issue_hit"] for record in records) / total, 3),
        "median_wall_s": round(statistics.median(walls), 2),
        "p90_wall_s": round(percentile(walls, 90) or 0.0, 2),
        "errors": sum(bool(record["error"]) for record in records),
        "timings_captured": sum(bool(record["timings"]["stages"]) for record in records),
        "by_category": by_category,
        "seats": _seat_summary(records),
    }


# ── Configuration echo ───────────────────────────────────────────────────────


def override_echo(payload: dict[str, Any], override: dict[str, Any]) -> str:
    """Report whether the response echoes the requested council configuration."""
    portal = payload.get("portal_council")
    if not isinstance(portal, dict):
        return "unverified"
    buckets = [portal, portal.get("config"), portal.get("applied_config")]
    seen = False
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        if all(bucket.get(key) == value for key, value in override.items()):
            return "applied"
        seen = seen or any(key in bucket for key in override)
    return "not_applied" if seen else "unverified"


def _merge_echo(current: str, status: str) -> str:
    """Fold one case's echo status into the run-level status."""
    if "not_applied" in (current, status):
        return "not_applied"
    if current == "unverified":
        return status
    if status == "unverified":
        return "partially_applied"
    return "applied" if current == status == "applied" else current


# ── Running ──────────────────────────────────────────────────────────────────

Post = Callable[[dict[str, Any]], dict[str, Any]]


def run_bench(
    cases: list[Case],
    *,
    post: Post,
    label: str,
    override: dict[str, Any] | None,
    started_at: str | None = None,
    cases_path: str = "",
) -> dict[str, Any]:
    """Send each case through ``post`` once and return the scored run record."""
    records: list[dict[str, Any]] = []
    echo_status = "unverified"
    for case in cases:
        body = build_request(case, override)
        started = time.monotonic()
        try:
            payload = post(body)
        except Exception as exc:  # a failed case is measurement data, not a crash
            record = _empty_record(
                case, time.monotonic() - started, f"{type(exc).__name__}: {exc}", {}
            )
        else:
            record = score_case(case, payload, time.monotonic() - started)
            if override:
                echo_status = _merge_echo(echo_status, override_echo(payload, override))
        records.append(record)
        print(
            f"[{case.id}] {case.category}: decision={record['decision'] or 'ERROR'} "
            f"ok={record['outcome_ok']} key_issue={record['key_issue_hit']} "
            f"wall={record['wall_s']:.1f}s",
            flush=True,
        )
    summary = summarise(records)
    summary["override_status"] = echo_status if override else "not_requested"
    return {
        "schema_version": 1,
        "configuration": {"label": label, "override": override},
        "started_at": started_at,
        "cases_path": cases_path,
        "cases": records,
        "summary": summary,
    }


# ── Reporting ────────────────────────────────────────────────────────────────


def _configuration_line(run: dict[str, Any]) -> str:
    override = run["configuration"]["override"]
    return json.dumps(override, sort_keys=True) if override else "workspace default"


def render_markdown(runs: list[dict[str, Any]], current: int = -1) -> str:
    """Render one or more runs; multiple runs give the per-configuration table."""
    run = runs[current]
    summary = run["summary"]
    lines = [
        f"# Council bench — {run['configuration']['label']}",
        "",
        f"Configuration: `{_configuration_line(run)}`",
        "",
        f"- Cases: {summary['cases']} · accuracy {summary['accuracy']:.3f} · "
        f"key-issue recall {summary['key_issue_recall']:.3f}",
        f"- Time: median {summary['median_wall_s']:.2f} s · p90 {summary['p90_wall_s']:.2f} s",
        f"- Errors: {summary['errors']} · per-stage timings captured: "
        f"{summary['timings_captured']}/{summary['cases']}",
        f"- Override status: {summary['override_status']}",
        "",
    ]
    if len(runs) > 1:
        lines.extend(
            [
                "## Configurations",
                "",
                "| Configuration | Cases | Accuracy | Key-issue recall | Median s | p90 s |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for entry in runs:
            cost = entry["summary"]
            lines.append(
                f"| `{entry['configuration']['label']}` | {cost['cases']} | "
                f"{cost['accuracy']:.3f} | {cost['key_issue_recall']:.3f} | "
                f"{cost['median_wall_s']:.2f} | {cost['p90_wall_s']:.2f} |"
            )
        lines.append("")
    lines.extend(
        [
            "## By category",
            "",
            "| Category | Cases | Accuracy | Key-issue recall | Median s |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for category, block in summary["by_category"].items():
        lines.append(
            f"| {category} | {block['cases']} | {block['accuracy']:.3f} | "
            f"{block['key_issue_recall']:.3f} | {block['median_wall_s']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Seats",
            "",
            "| Seat | Appearances | Participated | Rate | SUPPORT/REVISE/REJECT |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for seat, block in summary["seats"].items():
        votes = block["votes"]
        lines.append(
            f"| {seat} | {block['appearances']} | {block['participated']} | "
            f"{block['participation_rate']:.3f} | "
            f"{votes.get('SUPPORT', 0)}/{votes.get('REVISE', 0)}/{votes.get('REJECT', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Category | Expected | Decision | OK | Key issue | Votes SUPPORT/REVISE/REJECT | Wall s |",
            "|---|---|---|---|---|---:|---|---:|",
        ]
    )
    for record in run["cases"]:
        key_issue = "hit" if record["key_issue_hit"] else "miss"
        if record["key_issue_hit"]:
            key_issue = f"hit ({record['key_issue_source']})"
        votes = record["votes"]
        lines.append(
            f"| `{record['id']}` | {record['category']} | {record['expected_outcome']} | "
            f"{record['decision'] or 'ERROR'} | {'yes' if record['outcome_ok'] else 'no'} | "
            f"{key_issue} | {votes['SUPPORT']}/{votes['REVISE']}/{votes['REJECT']} | "
            f"{record['wall_s']:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _load_override(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    text = Path(value[1:]).read_text() if value.startswith("@") else value
    override = json.loads(text)
    if not isinstance(override, dict):
        raise ValueError("--config must be a JSON object")
    return override


def _http_post(client: httpx.Client, url: str, api_key: str) -> Post:
    def post(body: dict[str, Any]) -> dict[str, Any]:
        response = client.post(
            f"{url.rstrip('/')}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("pipeline returned a non-object response")
        return payload

    return post


def _write_runs(path: Path, runs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "runs": runs}, indent=2) + "\n")


def _default_label(override: dict[str, Any] | None) -> str:
    if not override:
        return "default"
    return str(override.get("mode") or "override")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bench auto-council quality and time")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--pipeline-url", default=PIPELINE_URL)
    parser.add_argument("--api-key", default=PIPELINE_API_KEY)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--config", help="council override as JSON, or @path to a JSON file")
    parser.add_argument("--label", help="configuration label (default: derived from --config)")
    parser.add_argument("--only", action="append", default=[], help="restrict to these case ids")
    parser.add_argument(
        "--category", action="append", default=[], help="restrict to these categories"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true", help="print request bodies; no network")
    parser.add_argument("--json-out", type=Path, help="write run records here")
    parser.add_argument("--append", action="store_true", help="merge with --json-out by label")
    parser.add_argument("--report-out", type=Path)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    if args.only:
        cases = [case for case in cases if case.id in set(args.only)]
    if args.category:
        cases = [case for case in cases if case.category in set(args.category)]
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        parser.error("no cases matched")

    try:
        override = _load_override(args.config)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(f"invalid --config: {exc}")
    label = args.label or _default_label(override)

    if args.dry_run:
        for case in cases:
            print(f"# {case.id} ({case.category})")
            print(json.dumps(build_request(case, override), indent=2, ensure_ascii=False))
        return 0

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with httpx.Client(timeout=args.timeout) as client:
        post = _http_post(client, args.pipeline_url, args.api_key)
        run = run_bench(
            cases,
            post=post,
            label=label,
            override=override,
            started_at=started_at,
            cases_path=str(args.cases),
        )

    runs = [run]
    if args.json_out:
        if args.append and args.json_out.exists():
            existing = json.loads(args.json_out.read_text()).get("runs") or []
            runs = [entry for entry in existing if entry["configuration"]["label"] != label] + [run]
        _write_runs(args.json_out, runs)

    report = render_markdown(runs, current=-1)
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(report)
    print(report)
    if override and run["summary"]["override_status"] != "applied":
        print(
            f"WARNING: council override {json.dumps(override, sort_keys=True)} was "
            f"{run['summary']['override_status']} — the pipeline may not honour {OVERRIDE_KEY}.",
            flush=True,
        )
    return 1 if run["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
