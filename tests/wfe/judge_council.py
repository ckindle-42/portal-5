#!/usr/bin/env python3
"""Disagreement-only council. Diagnostic: decision.py never reads it, and it never gates a seat.

Usage:
  uv run python -m tests.wfe.judge_council --campaign CAMPAIGN --screen-only
  uv run python -m tests.wfe.judge_council --campaign CAMPAIGN
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
from collections import Counter
from pathlib import Path

import yaml

from tests.wfe import judge
from tests.wfe.canary import _TOOL_INFRA, ledger_signatures
from tests.wfe.judge_cloud import suite_refuses_cloud

_HTTP_REPLY = re.compile(r"backend returned http [45]\d\d")
_PIPELINE_REPLY = "pipeline stream error"


def third_config() -> dict:
    """profiles.council.third from judge.yaml, or {} when it is missing."""
    with contextlib.suppress(Exception):
        data = yaml.safe_load(judge.JUDGE_CONFIG_PATH.read_text()) or {}
        return ((data.get("profiles") or {}).get("council") or {}).get("third") or {}
    return {}


def resolve_third(suite: str) -> tuple[str, str, str | None]:
    """(model, url, api_key). A sensitive suite always gets a local member."""
    cfg = third_config()
    model = os.environ.get("WFE_JUDGE_COUNCIL_MODEL") or cfg.get("model")
    url = (os.environ.get("WFE_JUDGE_COUNCIL_URL") or cfg.get("url") or "").rstrip("/")
    if not model or not url:
        raise ValueError(
            "no council third judge: set profiles.council.third in tests/wfe/judge.yaml"
        )
    key_env = cfg.get("api_key_env")
    remote = bool(key_env) or not judge.endpoint_is_local(url)
    if suite_refuses_cloud(suite) and remote:
        local_url = judge.judge_url()
        judge.assert_local(local_url)
        return judge.judge_model(), local_url, None
    if remote:
        key_env = key_env or "OPENAI_API_KEY"
        key = os.environ.get(key_env)
        if not key:
            raise ValueError(f"no council API key: set {key_env}")
        return str(model), url, key
    judge.assert_local(url)
    return str(model), url, None


def reply_blob(row: dict) -> str:
    """Note, tool output, and assistant text for one arm."""
    transcript = " ".join(str(entry.get("content") or "") for entry in row.get("transcript") or [])
    tools = " ".join(str(entry.get("output") or "") for entry in row.get("tool_call_log") or [])
    note = str(row.get("notes") or row.get("note") or "")
    return "\n".join((note, str(row.get("final_text") or ""), tools, transcript))


def setup_marker(text: str) -> str | None:
    """The first pipeline or tool-infrastructure signature in a reply, if any."""
    low = text.lower()
    for sig in _TOOL_INFRA:
        if sig in low:
            return sig
    if _PIPELINE_REPLY in low:
        return _PIPELINE_REPLY
    match = _HTTP_REPLY.search(low)
    if match:
        return match.group(0)
    for sig in ledger_signatures():
        if sig and sig in low:
            return sig
    return None


def _repeat(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _by_key(records: list[dict]) -> dict[str, dict]:
    return {rec["key"]: rec for rec in records if rec.get("key")}


def _profiles(campaign_dir: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    return _by_key(judge.load(campaign_dir, "local")), _by_key(judge.load(campaign_dir, "cloud"))


def _comparable(left: dict, right: dict) -> bool:
    if left.get("error") or right.get("error"):
        return False
    if left.get("rubric_sha") != right.get("rubric_sha"):
        return False
    if left.get("arms") != right.get("arms"):
        return False
    pref_left, pref_right = left.get("preference"), right.get("preference")
    return bool(pref_left) and bool(pref_right) and pref_left != pref_right


def _disagreements(local: dict[str, dict], cloud: dict[str, dict]) -> list[tuple[dict, dict]]:
    pairs = []
    for key in sorted(set(local) & set(cloud)):
        left, right = local[key], cloud[key]
        if _comparable(left, right):
            pairs.append((left, right))
    return pairs


def _arm_index(rows: list[dict]) -> dict[tuple, dict]:
    out = {}
    for row in rows:
        key = (
            row.get("workspace"),
            row.get("suite"),
            row.get("task_id"),
            _repeat(row.get("repeat")),
            row.get("arm"),
        )
        out[key] = row
    return out


def _pair_rows(rec: dict, idx: dict) -> tuple[dict | None, dict | None]:
    arms = rec.get("arms") or {}
    base = (rec.get("workspace"), rec.get("suite"), rec.get("task_id"), _repeat(rec.get("repeat")))
    return idx.get((*base, arms.get("A"))), idx.get((*base, arms.get("B")))


def _pair_marker(rec: dict, idx: dict) -> str | None:
    for row in _pair_rows(rec, idx):
        if not row:
            continue
        marker = setup_marker(reply_blob(row))
        if marker:
            return marker
    return None


def disagreement_screen(campaign_dir: Path) -> dict:
    """How many local/cloud splits there are, and how many a setup reply removes."""
    local, cloud = _profiles(campaign_dir)
    pairs = _disagreements(local, cloud)
    idx = _arm_index(judge._load_rows(campaign_dir))
    markers: dict[str, int] = {}
    excluded = 0
    for left, _right in pairs:
        marker = _pair_marker(left, idx)
        if not marker:
            continue
        excluded += 1
        markers[marker] = markers.get(marker, 0) + 1
    return {"disagreements": len(pairs), "excluded_setup": excluded, "markers": markers}


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    with contextlib.suppress(Exception):
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    return None


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1))


def _done_setup(path: Path, rubric_sha: object) -> bool:
    rec = _read(path)
    return bool(
        rec
        and rec.get("excluded") == "setup"
        and rec.get("rubric_sha") == rubric_sha
        and not rec.get("error")
    )


def _done_vote(path: Path, rubric_sha: object, model: str) -> bool:
    rec = _read(path)
    if not rec or rec.get("error") or rec.get("excluded"):
        return False
    return (
        rec.get("rubric_sha") == rubric_sha
        and rec.get("judge_model") == model
        and bool(rec.get("preference"))
    )


def _base(left: dict) -> dict:
    return {
        "schema": judge.JUDGE_SCHEMA_VERSION,
        "workspace": left.get("workspace"),
        "suite": left.get("suite"),
        "task_id": left.get("task_id"),
        "repeat": left.get("repeat"),
        "key": left.get("key"),
        "arms": left.get("arms"),
        "order_flipped": left.get("order_flipped"),
        "rubric_sha": left.get("rubric_sha"),
        "judge_profile": "council",
    }


def _member(profile: str, rec: dict) -> dict:
    return {
        "profile": profile,
        "preference": rec.get("preference"),
        "reason": rec.get("reason") or "",
        "judge_model": rec.get("judge_model"),
    }


def _excluded_record(left: dict, right: dict, marker: str) -> dict:
    record = _base(left)
    record.update(
        {
            "judge_model": None,
            "judge_url": None,
            "preference": None,
            "winner": None,
            "reason": f"excluded: setup ({marker})",
            "raw": "",
            "members": [_member("local", left), _member("cloud", right)],
            "excluded": "setup",
        }
    )
    return record


def _error_record(left: dict, right: dict, model: str, url: str, message: str) -> dict:
    record = _base(left)
    record.update(
        {
            "judge_model": model,
            "judge_url": url,
            "preference": None,
            "winner": None,
            "reason": "",
            "raw": "",
            "error": message,
            "members": [_member("local", left), _member("cloud", right)],
            "excluded": None,
        }
    )
    return record


def _majority(votes: list[str]) -> str:
    top, count = Counter(votes).most_common(1)[0]
    return top if count >= 2 else "tie"


def _reason_for(preference: str, left: dict, right: dict) -> str:
    for rec in (left, right):
        if rec.get("preference") == preference:
            return str(rec.get("reason") or "")
    return ""


def _majority_record(
    left: dict, right: dict, model: str, url: str, third_pref: str, third_reason: str, raw: str
) -> dict:
    preference = _majority([left["preference"], right["preference"], third_pref])
    arms = left.get("arms") or {}
    winner = arms.get(preference) if preference in ("A", "B") else None
    reason = third_reason if third_pref == preference else _reason_for(preference, left, right)
    record = _base(left)
    record.update(
        {
            "judge_model": model,
            "judge_url": url,
            "preference": preference,
            "winner": winner,
            "reason": reason,
            "raw": raw[:4000],
            "members": [
                _member("local", left),
                _member("cloud", right),
                {
                    "profile": "third",
                    "preference": third_pref,
                    "reason": third_reason,
                    "judge_model": model,
                },
            ],
            "excluded": None,
        }
    )
    return record


def _index_suites(campaign_dir: Path, suites: dict) -> None:
    manifest = json.loads((campaign_dir / "manifest.json").read_text())
    for row in manifest.get("rows") or []:
        suites[f"{row['workspace']}|{row['suite']}"] = row["suite_path"]


def _rubric_and_task(rec: dict, suites: dict, tasks: dict) -> tuple[str, dict]:
    task = judge._task_for(
        tasks, suites, rec.get("workspace"), rec.get("suite"), rec.get("task_id")
    )
    return judge._rubric_text(task or {}), task or {}


def _ask_third(messages: list[dict], model: str, url: str, api_key: str | None, ask) -> str:
    if ask is not None:
        return ask(messages, model, url, api_key)
    if api_key:
        from tests.wfe.judge_cloud import ask_cloud_judge

        return ask_cloud_judge(messages, model, url, api_key)
    return judge.ask_judge(messages, model, url)


def _third_for(
    suite: str, cache: dict[str, tuple[str, str, str | None]]
) -> tuple[str, str, str | None]:
    if suite not in cache:
        cache[suite] = resolve_third(suite)
    return cache[suite]


def _vote(left, right, idx, rubric, task, model, url, api_key, ask) -> dict:
    if judge.sha12(rubric) != left.get("rubric_sha"):
        return _error_record(left, right, model, url, "rubric changed since the member votes")
    row_a, row_b = _pair_rows(left, idx)
    if not row_a or not row_b:
        return _error_record(left, right, model, url, "missing arm reply")
    text_a = judge.render_conversation(row_a, task)
    text_b = judge.render_conversation(row_b, task)
    if not text_a.strip() or not text_b.strip():
        return _error_record(left, right, model, url, "missing arm reply")
    try:
        raw = _ask_third(judge.judge_messages(rubric, text_a, text_b), model, url, api_key, ask)
        pref, reason = judge.parse_verdict(raw)
    except Exception as exc:  # noqa: BLE001 — a judge failure is recorded, never a verdict
        return _error_record(left, right, model, url, f"{type(exc).__name__}: {exc}")
    return _majority_record(left, right, model, url, pref, reason, raw)


def _one_pair(campaign_dir, left, right, idx, suites, tasks, thirds, ask, res) -> None:
    path = judge._judgement_path(campaign_dir, left["key"], "council")
    rubric_sha = left.get("rubric_sha")
    marker = _pair_marker(left, idx)
    if marker:
        res["excluded_setup"] += 1
        res["markers"][marker] = res["markers"].get(marker, 0) + 1
        if _done_setup(path, rubric_sha):
            res["skipped"] += 1
            return
        _write(path, _excluded_record(left, right, marker))
        return
    model, url, api_key = _third_for(str(left.get("suite") or ""), thirds)
    if _done_vote(path, rubric_sha, model):
        res["skipped"] += 1
        return
    rubric, task = _rubric_and_task(left, suites, tasks)
    record = _vote(left, right, idx, rubric, task, model, url, api_key, ask)
    _write(path, record)
    res["judged"] += 1
    if record.get("error"):
        res["errors"] += 1


def council_campaign(campaign_dir: Path, ask=None) -> dict:
    """Write judgements/council/<sha12>.json for every comparable split. No synthesizer."""
    local, cloud = _profiles(campaign_dir)
    pairs = _disagreements(local, cloud)
    idx = _arm_index(judge._load_rows(campaign_dir))
    suites: dict = {}
    _index_suites(campaign_dir, suites)
    res = {
        "disagreements": len(pairs),
        "excluded_setup": 0,
        "judged": 0,
        "skipped": 0,
        "errors": 0,
        "markers": {},
    }
    thirds: dict[str, tuple[str, str, str | None]] = {}
    tasks: dict = {}
    for left, right in pairs:
        _one_pair(campaign_dir, left, right, idx, suites, tasks, thirds, ask, res)
    return res


def checker_agreement(campaign_dir: Path) -> tuple[int, int]:
    """(agreed, n) on council verdicts where exactly one arm's outcome is PASS."""
    idx = _arm_index(judge._load_rows(campaign_dir))
    agreed = 0
    counted = 0
    for rec in judge.load(campaign_dir, "council"):
        if rec.get("excluded") or rec.get("error") or not rec.get("preference"):
            continue
        row_a, row_b = _pair_rows(rec, idx)
        if not row_a or not row_b:
            continue
        passed = [row.get("arm") for row in (row_a, row_b) if row.get("outcome") == "PASS"]
        if len(passed) != 1:
            continue
        counted += 1
        if rec.get("winner") == passed[0]:
            agreed += 1
    return agreed, counted


def format_checker_agreement(agreed: int, counted: int) -> str:
    if not counted:
        return "Council vs checker (exactly one arm passed): 0/0"
    return (
        f"Council vs checker (exactly one arm passed): {agreed}/{counted} = {agreed / counted:.2%}"
    )


def format_screen(res: dict) -> str:
    lines = [
        f"local/cloud disagreements: {res['disagreements']}",
        f"setup screen excludes: {res['excluded_setup']}",
    ]
    if "judged" in res:
        lines.append(
            f"judged: {res['judged']}, already recorded: {res['skipped']}, errors: {res['errors']}"
        )
    for name, count in sorted(
        (res.get("markers") or {}).items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"  {count} {name}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--campaigns-root", type=Path)
    ap.add_argument(
        "--screen-only",
        action="store_true",
        help="count disagreements and setup exclusions; do not call a judge",
    )
    args = ap.parse_args(argv)
    from tests.wfe import campaign as camp

    root = args.campaigns_root or camp.CAMPAIGNS
    campaign_dir = root / args.campaign
    res = disagreement_screen(campaign_dir) if args.screen_only else council_campaign(campaign_dir)
    print(format_screen(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
