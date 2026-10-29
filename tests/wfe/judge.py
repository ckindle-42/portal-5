#!/usr/bin/env python3
"""Blind pairwise WFE judge — two arms' transcripts, one LOCAL model, no labels.

Reported, never gated: `decision.py` reads no judgement and no pass rate, disposition
or curtailment depends on one. A suite opts in by giving its tasks a `rubric`; a pair is
judged only once both arms hold a recorded row for the same task and repeat. The order
is randomised per pair and the arm labels never reach the model — it sees A and B.

Usage:
  WFE_JUDGE_MODEL=<local tag> uv run python -m tests.wfe.judge --campaign wfe_live
  WFE_JUDGE_MODEL=<tag> WFE_JUDGE_URL=http://p40:11434 uv run python -m tests.wfe.judge \\
      --campaign wfe_live
  uv run python -m tests.wfe.campaign --campaign-id wfe_live --judge

The endpoint defaults to Ollama on this host and must be a loopback/LAN address; a public
host is refused unless WFE_JUDGE_ALLOW_REMOTE=1 says the operator owns it.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import ipaddress
import itertools
import json
import os
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from tests.wfe.runner import OLLAMA, load_suite
from tests.wfe.schema import INSTRUMENT_OUTCOMES, sha12

JUDGE_SCHEMA_VERSION = "wfe-judge-1"
DEFAULT_TIMEOUT_S = int(os.environ.get("WFE_JUDGE_TIMEOUT", "600"))

#: Public inference APIs. The judge is local by default and these are refused outright.
_CLOUD_HOSTS = frozenset(
    {
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "openrouter.ai",
        "api.mistral.ai",
        "api.groq.com",
        "api.cohere.com",
    }
)
_LAN_SUFFIXES = (".local", ".lan", ".internal", ".home", ".localhost")

SYSTEM_PROMPT = (
    "You are comparing two replies to the same user request. Judge only against the "
    "rubric and the conversation supplied. Do not reward length, formatting or confident "
    'tone. Reply with one JSON object: {"preference": "A" | "B" | "tie", '
    '"reason": "<one or two sentences>"}'
)


def judge_url(explicit: str | None = None) -> str:
    return (explicit or os.environ.get("WFE_JUDGE_URL") or OLLAMA).rstrip("/")


def judge_model(explicit: str | None = None) -> str:
    model = explicit or os.environ.get("WFE_JUDGE_MODEL")
    if not model:
        raise ValueError("no judge model: set WFE_JUDGE_MODEL to a local tag or pass --model")
    return model


def endpoint_is_local(url: str) -> bool:
    """A loopback or private/LAN host. A public name is never treated as local."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host or host in _CLOUD_HOSTS:
        return False
    if host == "localhost" or host.endswith(_LAN_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host  # a single-label LAN hostname, e.g. p40
    return ip.is_loopback or ip.is_private


def assert_local(url: str) -> None:
    if endpoint_is_local(url) or os.environ.get("WFE_JUDGE_ALLOW_REMOTE") == "1":
        return
    raise ValueError(
        f"judge endpoint {urllib.parse.urlparse(url).hostname!r} is not a local/LAN host; "
        "the judge is local by default (WFE_JUDGE_ALLOW_REMOTE=1 overrides deliberately)"
    )


def render_conversation(row: dict, task: dict | None = None) -> str:
    """What the user saw: each scripted user turn, then the answer and the tool names it
    produced. No arm, model, timing or checker field is included."""
    task = task or {}
    turns = task.get("turns") or []
    if not turns:
        return str(row.get("final_text") or row.get("final_text_head") or "").strip()
    entries = [t for t in row.get("transcript") or [] if t.get("content")]
    if not entries:
        return str(row.get("final_text") or "").strip()
    if not all("scripted_turn" in e for e in entries):
        return "\n\n".join(f"Assistant: {e.get('content', '')}" for e in entries)
    by_turn: dict[int, list[dict]] = defaultdict(list)
    for e in entries:
        by_turn[e["scripted_turn"]].append(e)
    lines = []
    for i, turn in enumerate(turns):
        lines.append(f"User: {turn.get('user', '')}")
        for e in by_turn.get(i, []):
            calls = ", ".join(str(c.get("name") or "") for c in (e.get("tool_calls") or []))
            lines.append(
                f"Assistant: {e.get('content', '')}" + (f"\n[tools: {calls}]" if calls else "")
            )
    return "\n\n".join(lines)


def judge_messages(rubric: str, text_a: str, text_b: str) -> list[dict]:
    body = f"RUBRIC\n{rubric}\n\nRESPONSE A\n{text_a}\n\nRESPONSE B\n{text_b}\n"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": body}]


def parse_verdict(text: str) -> tuple[str, str]:
    """(preference, reason) from the judge's reply: its JSON object when present, else the
    first standalone A / B / tie token. Raises when neither is there."""
    raw = text or ""
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", raw):
        with contextlib.suppress(json.JSONDecodeError):
            obj, _end = decoder.raw_decode(raw[m.start() :])
            if isinstance(obj, dict) and "preference" in obj:
                pref = {"a": "A", "b": "B", "tie": "tie"}.get(str(obj["preference"]).lower())
                if pref:
                    return pref, str(obj.get("reason") or "")[:800]
    m = re.search(r"\b(tie|A|B)\b", raw)
    if m:
        token = m.group(1)
        return ("tie" if token.lower() == "tie" else token.upper()), raw[:800]
    raise ValueError(f"judge reply carries no preference: {raw[:200]!r}")


def ask_judge(messages: list[dict], model: str, url: str, timeout: int = DEFAULT_TIMEOUT_S) -> str:
    """One judge completion from the local Ollama endpoint. The only network call here."""
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0, "seed": 7},
    }
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read() or b"{}")
    return str((out.get("message") or {}).get("content") or "")


def pair_key(workspace: str, suite: str, task_id: str, repeat: int, arm_a: str, arm_b: str) -> str:
    first, second = sorted((arm_a, arm_b))
    return f"{workspace}|{suite}|{task_id}|r{repeat}|{first} vs {second}"


def order_flipped(key: str) -> bool:
    """True when the first arm takes slot B. A stable per-pair coin, recorded in the
    judgement so the mapping back is never guessed."""
    return hashlib.sha256(key.encode()).digest()[0] % 2 == 1


def _rubric_text(task: dict) -> str:
    rubric = task.get("rubric")
    if isinstance(rubric, list):
        return "\n".join(f"- {x}" for x in rubric)
    return str(rubric or "")


def _load_rows(campaign_dir: Path) -> list[dict]:
    rows = []
    for f in sorted((campaign_dir / "rows").glob("*.json")):
        with contextlib.suppress(Exception):
            rows.append(json.loads(f.read_text()))
    return rows


def _judgement_path(campaign_dir: Path, key: str) -> Path:
    return campaign_dir / "judgements" / f"{sha12(key)}.json"


def _already_judged(path: Path, rubric_sha: str, model: str, url: str) -> bool:
    """A recorded verdict stands while its rubric and judge are unchanged. An error is
    retried: the endpoint was down, the pair has not been judged."""
    if not path.is_file():
        return False
    with contextlib.suppress(Exception):
        rec = json.loads(path.read_text())
        return (
            not rec.get("error")
            and rec.get("rubric_sha") == rubric_sha
            and rec.get("judge_model") == model
            and rec.get("judge_url") == url
        )
    return False


def _judge_one(
    campaign_dir: Path,
    key: str,
    arms: tuple[str, str],
    texts: dict[str, str],
    rubric: str,
    model: str,
    url: str,
    meta: dict,
) -> dict:
    arm_a, arm_b = arms
    flipped = order_flipped(key)
    first, second = (arm_b, arm_a) if flipped else (arm_a, arm_b)
    record = {
        "schema": JUDGE_SCHEMA_VERSION,
        **meta,
        "key": key,
        "arms": {"A": first, "B": second},
        "order_flipped": flipped,
        "rubric_sha": sha12(rubric),
        "judge_model": model,
        "judge_url": url,
    }
    try:
        reply = ask_judge(judge_messages(rubric, texts[first], texts[second]), model, url)
        preference, reason = parse_verdict(reply)
        winner = None if preference == "tie" else record["arms"][preference]
        record.update(
            {"preference": preference, "winner": winner, "reason": reason, "raw": reply[:4000]}
        )
    except Exception as e:  # noqa: BLE001 - a judge failure is recorded, never a verdict
        record.update({"error": f"{type(e).__name__}: {e}", "preference": None, "winner": None})
    path = _judgement_path(campaign_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1))
    return record


def _task_for(
    task_cache: dict, suites: dict[str, str], workspace: str, suite: str, task_id: str
) -> dict | None:
    key = f"{workspace}|{suite}"
    if key not in task_cache:
        suite_path = suites.get(key) or suites.get(suite)
        try:
            task_cache[key] = {t["id"]: t for t in load_suite(suite_path)}
        except Exception:
            task_cache[key] = {}
    return task_cache[key].get(task_id)


def _pairs(
    rows: list[dict], suites: dict[str, str], tasks: dict
) -> list[tuple[str, tuple[str, str], dict[str, str], dict, str]]:
    """(key, (arm, arm), {arm: text}, meta, rubric) for every judged-ready pair. A pair is
    ready only when both rows are measurable and the task carries a rubric."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("outcome") in INSTRUMENT_OUTCOMES:
            continue
        groups[(r["workspace"], r["suite"], r["task_id"], r.get("repeat", 0))].append(r)
    out = []
    for (workspace, suite, task_id, repeat), group in sorted(groups.items()):
        if len({r["arm"] for r in group}) < 2:
            continue
        task = _task_for(tasks, suites, workspace, suite, task_id)
        rubric = _rubric_text(task or {})
        if not rubric.strip():
            continue
        texts = {r["arm"]: render_conversation(r, task) for r in group}
        for arm_a, arm_b in itertools.combinations(sorted(texts), 2):
            if not texts[arm_a].strip() or not texts[arm_b].strip():
                continue
            key = pair_key(workspace, suite, task_id, repeat, arm_a, arm_b)
            meta = {
                "workspace": workspace,
                "suite": suite,
                "task_id": task_id,
                "repeat": repeat,
            }
            out.append(
                (key, (arm_a, arm_b), {arm_a: texts[arm_a], arm_b: texts[arm_b]}, meta, rubric)
            )
    return out


def judge_campaign(
    campaign_dir: Path,
    model: str | None = None,
    url: str | None = None,
    limit: int | None = None,
) -> dict:
    """Judge every task pair that now has a row from both arms; resumable, idempotent."""
    model = judge_model(model)
    url = judge_url(url)
    assert_local(url)
    manifest = json.loads((campaign_dir / "manifest.json").read_text())
    suites: dict[str, str] = {}
    for m in manifest.get("rows") or []:
        suites[f"{m['workspace']}|{m['suite']}"] = m["suite_path"]
    tasks: dict = {}
    res = {
        "campaign": campaign_dir.name,
        "model": model,
        "url": url,
        "judged": 0,
        "skipped": 0,
        "errors": 0,
        "pairs": 0,
    }
    pairs = _pairs(_load_rows(campaign_dir), suites, tasks)
    res["pairs"] = len(pairs)
    for key, arms, texts, meta, rubric in pairs:
        if limit is not None and res["judged"] >= limit:
            break
        path = _judgement_path(campaign_dir, key)
        if _already_judged(path, sha12(rubric), model, url):
            res["skipped"] += 1
            continue
        record = _judge_one(campaign_dir, key, arms, texts, rubric, model, url, meta)
        res["judged"] += 1
        if record.get("error"):
            res["errors"] += 1
    return res


def load(campaign_dir: Path) -> list[dict]:
    out = []
    for f in sorted((campaign_dir / "judgements").glob("*.json")):
        with contextlib.suppress(Exception):
            out.append(json.loads(f.read_text()))
    return out


def summary(campaign_dir: Path) -> dict:
    """Per-cell blind preferences: {arm: wins}, ties and n, keyed by sorted arm pair."""
    records = load(campaign_dir)
    cells: dict[str, dict] = {}
    for rec in records:
        if rec.get("error"):
            continue
        arms = rec.get("arms") or {}
        pair = sorted(a for a in (arms.get("A"), arms.get("B")) if a)
        if len(pair) != 2:
            continue
        arm_a, arm_b = pair
        key = f"{rec.get('workspace')}|{rec.get('suite')}|{arm_a}|{arm_b}"
        cell = cells.setdefault(key, {"wins": defaultdict(int), "ties": 0, "n": 0, "reasons": []})
        cell["n"] += 1
        winner = rec.get("winner")
        if winner:
            cell["wins"][winner] += 1
        else:
            cell["ties"] += 1
        if rec.get("reason") and len(cell["reasons"]) < 5:
            cell["reasons"].append(
                {
                    "task_id": rec.get("task_id"),
                    "repeat": rec.get("repeat"),
                    "winner": winner,
                    "reason": rec["reason"],
                }
            )
    return {
        "records": len(records),
        "errors": sum(1 for r in records if r.get("error")),
        "judge_models": sorted({r.get("judge_model") for r in records if r.get("judge_model")}),
        "cells": {
            k: {"wins": dict(v["wins"]), "ties": v["ties"], "n": v["n"], "reasons": v["reasons"]}
            for k, v in cells.items()
        },
    }


def cell_for(
    judge_summary: dict, workspace: str, suite: str, arm_a: str, arm_b: str
) -> dict | None:
    """The cell's preferences from whatever arm order the caller holds."""
    first, second = sorted((arm_a, arm_b))
    return (judge_summary.get("cells") or {}).get(f"{workspace}|{suite}|{first}|{second}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--campaigns-root", type=Path)
    ap.add_argument("--model")
    ap.add_argument("--url")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    from tests.wfe import campaign as camp

    root = args.campaigns_root or camp.CAMPAIGNS
    res = judge_campaign(root / args.campaign, args.model, args.url, args.limit)
    print(
        f"{res['campaign']}: {res['judged']} judged, {res['skipped']} already recorded, "
        f"{res['errors']} error(s), {res['pairs']} pair(s) ready ({res['model']} @ {res['url']})"
    )
    return 0 if not res["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
