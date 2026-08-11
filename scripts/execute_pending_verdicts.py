#!/usr/bin/env python3
"""Reclaim executor for verdicts recorded in config/PENDING_MODEL_VERDICTS.md.

Two-stage:

    --plan (default)         Write reports/RECLAIM_PLAN_<UTC>.md and touch
                             nothing else. The plan lists every decided
                             entry with safety flags applied.

    --execute --plan=<FILE>  Perform writes and print the ollama rm block.
                             Requires the exact plan filename; verifies the
                             file exists and is <24h old.

For each verdict, after safety checks:
    decline    -> write DROPPED unit-model-catalog stub (with re-pull
                  command), append to config/UNUSED_MODELS_<today>.md,
                  prune from config/model_inventory.snapshot, queue
                  ollama rm.
    promote    -> write PROMOTED stub, queue follow-on wiring instruction.
                  Never edits workspace_routing / model_hint.
    keep-open  -> append kept: exclusion note to today's UNUSED_MODELS doc.
    investigate/investigate-refresh -> log-only; ledger re-surfaces next
                  audit run.

Safety flags per declined tag:
    BLOCK still-routed  — bench-* workspace's model_hint or variants still
                          equals the tag. Removing would break BB.
    WARN  still-loaded  — ollama ps shows the tag loaded.
    WARN  recent-refs   — git log or docs mention the tag outside the
                          tracked evidence corpus.
    INFO  no-re-pull    — portal5/* local build; not registry-pullable.

Idempotent. Never calls ollama rm.

Usage:
    python3 scripts/execute_pending_verdicts.py
    python3 scripts/execute_pending_verdicts.py --execute --plan=RECLAIM_PLAN_<UTC>.md
"""

from __future__ import annotations

import datetime as _dt
import glob
import json
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "config" / "PENDING_MODEL_VERDICTS.md"
SNAPSHOT_PATH = REPO_ROOT / "config" / "model_inventory.snapshot"
PORTAL_PATH = REPO_ROOT / "config" / "portal.yaml"
CANONICAL_DIR = REPO_ROOT / "portal_wiki" / "canonical"
REPORTS_DIR = REPO_ROOT / "reports"

ENTRY_RE = re.compile(r"^- \[x\] `([^`]+)` — ([\d.]+) GB")
VERDICT_RE = re.compile(
    r"^  - verdict:\s*(decline|promote|keep-open|investigate|investigate-refresh)"
    r"(?:\s*[-—:(]?\s*(.*?))?$"
)

VALID_VERDICTS = ("decline", "promote", "keep-open", "investigate", "investigate-refresh")
PLAN_FRESHNESS_S = 86400


def today_stamp() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y%m%d")


def now_utc_stamp() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def slugify(tag: str) -> str:
    s = tag.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def parse_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    out = []
    lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        m = ENTRY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        tag, size = m.group(1), float(m.group(2))
        verdict = None
        reason = ""
        for j in range(i + 1, min(i + 12, len(lines))):
            if lines[j].startswith("- ["):
                break
            vm = VERDICT_RE.match(lines[j])
            if vm:
                verdict = vm.group(1)
                reason = (vm.group(2) or "").strip().rstrip(")").strip()
                break
        if verdict:
            out.append({"tag": tag, "size_gb": size, "verdict": verdict, "reason": reason})
        i += 1
    return out


# -------------------- safety layer --------------------


def _load_portal() -> dict:
    return yaml.safe_load(PORTAL_PATH.read_text(encoding="utf-8"))


def still_routed(tag: str, portal: dict) -> list[str]:
    """Return bench-* workspace slugs still routing to tag. Non-empty
    means reclaim would break the model_inventory (BB) validate check."""
    hits = []
    for slug, spec in portal.get("workspaces", {}).items():
        if not slug.startswith("bench-"):
            continue
        if spec.get("model_hint") == tag:
            hits.append(f"{slug}.model_hint")
            continue
        for vname, var in (spec.get("variants") or {}).items():
            if isinstance(var, dict) and var.get("model_hint") == tag:
                hits.append(f"{slug}.variants.{vname}")
    return hits


def still_loaded(tag: str) -> bool | None:
    """Query ollama /api/ps. Returns True/False if reachable, None if not
    (the operator handles verification manually)."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=3) as r:
            data = json.load(r)
    except Exception:
        return None
    loaded = {m.get("model") or m.get("name") for m in data.get("models", [])}
    return tag in loaded


def recent_references(tag: str, days: int = 90) -> list[str]:
    """Return recent sources mentioning the tag outside the tracked evidence
    corpus. Recent git log commits + docs/**/*.md + CHANGELOG + README."""
    refs = []
    try:
        r = subprocess.run(
            ["git", "log", f"--since={days} days ago", "--pretty=format:%h %s"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        for line in r.stdout.splitlines():
            if tag.lower() in line.lower():
                refs.append(f"git: {line[:120]}")
    except Exception:
        pass
    for pattern in ("README.md", "CHANGELOG.md", "docs/**/*.md"):
        for path in glob.glob(str(REPO_ROOT / pattern), recursive=True):
            try:
                if tag.lower() in Path(path).read_text(errors="ignore").lower():
                    refs.append(f"file: {Path(path).relative_to(REPO_ROOT)}")
            except OSError:
                pass
    return refs


def re_pull_hint(tag: str) -> str:
    """Operator-facing command to re-pull if the decline turns out wrong."""
    if tag.startswith("portal5/"):
        return "(local build — reconstruct via ./launch.sh apply-model-params or the original derivation task; not registry-pullable)"
    if tag.startswith("hf.co/") or "/" in tag.split(":")[0]:
        return f"ollama pull '{tag}'"
    if ":" in tag:
        return f"ollama pull '{tag}'"
    return f"ollama pull '{tag}'  # verify tag exists in registry"


def safety_check(tag: str, verdict: str, portal: dict) -> dict:
    """Full safety envelope for a proposed action on tag. Returns
    {block: bool, flags: [{level, name, detail}]}. Only decline is
    fully gated; other verdicts get minimal checks."""
    flags = []
    block = False
    if verdict == "decline":
        routed = still_routed(tag, portal)
        if routed:
            block = True
            flags.append(
                {
                    "level": "BLOCK",
                    "name": "still-routed",
                    "detail": ", ".join(routed),
                }
            )
        loaded = still_loaded(tag)
        if loaded is True:
            flags.append(
                {
                    "level": "WARN",
                    "name": "still-loaded",
                    "detail": "ollama ps shows model loaded — stop or wait before ollama rm",
                }
            )
        elif loaded is None:
            flags.append(
                {
                    "level": "INFO",
                    "name": "ollama-unreachable",
                    "detail": "could not query ollama /api/ps — operator verifies not-loaded",
                }
            )
        refs = recent_references(tag)
        if refs:
            flags.append(
                {
                    "level": "WARN",
                    "name": "recent-refs",
                    "detail": f"{len(refs)} recent references outside tracked evidence: {refs[0]}"
                    + (f" (+{len(refs) - 1} more)" if len(refs) > 1 else ""),
                }
            )
        if tag.startswith("portal5/"):
            flags.append(
                {
                    "level": "INFO",
                    "name": "no-re-pull",
                    "detail": "portal5/* local build; not registry-pullable",
                }
            )
    return {"block": block, "flags": flags, "re_pull": re_pull_hint(tag)}


# -------------------- catalog + docs writers --------------------


def existing_catalog_unit_for(tag: str, verdict: str) -> Path | None:
    base = f"unit-model-catalog-{slugify(tag)}"
    marker = "-dropped" if verdict == "decline" else "-promoted"
    for p in CANONICAL_DIR.glob(f"{base}*.md"):
        if marker in p.name:
            return p
    return None


def emit_catalog_stub(
    tag: str, size_gb: float, verdict: str, reason: str, safety: dict, execute: bool
) -> Path | None:
    if verdict == "decline":
        marker = "dropped"
        title_suffix = f"DROPPED (evaluated, not adopted — {reason or 'reclaimed via TASK_MODEL_DISK_RECLAIM_V1'})"
    elif verdict == "promote":
        marker = "promoted"
        title_suffix = f"PROMOTED (candidate — wire per follow-on task; {reason or 'see PENDING_MODEL_VERDICTS.md'})"
    else:
        return None
    existing = existing_catalog_unit_for(tag, verdict)
    if existing:
        print(f"    skip catalog stub (exists): {existing.name}")
        return existing
    slug = slugify(tag)
    fname = f"unit-model-catalog-{slug}-{marker}-{today_stamp()}.md"
    path = CANONICAL_DIR / fname
    yaml_title = f'"MODEL_CATALOG — `{tag}` — {title_suffix}"'
    re_pull_line = safety.get("re_pull", "") if verdict == "decline" else ""
    body = f"""---
id: unit-model-catalog-{slug}-{marker}-{today_stamp()}
kind: what
title: {yaml_title}
sources:
- type: code
  path: config/PENDING_MODEL_VERDICTS.md
- type: code
  path: config/model_inventory.snapshot
last_generated_commit: pending-spine-sweep
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 0.0
updated_at: 0.0
---

`{tag}` ({size_gb:.1f} GB) — {title_suffix}. Recorded via
TASK_MODEL_DISK_RECLAIM_V1 from an operator verdict in
`config/PENDING_MODEL_VERDICTS.md`. The wiki drift-gate will re-ground this
unit into its full pinned form on the next spine sweep.

## Why

Reason recorded by operator: {reason or "(none — see the ledger's verdict line)"}

## Re-pull (if this decision reverses)

```
{re_pull_line or "(promoted — no re-pull needed; see follow-on wiring task)"}
```
"""
    if execute:
        path.write_text(body)
        print(f"    wrote {path.relative_to(REPO_ROOT)}")
    else:
        print(f"    [would write] {path.relative_to(REPO_ROOT)}")
    return path


def append_unused_models_entry(entries: list[dict], execute: bool) -> Path:
    path = REPO_ROOT / "config" / f"UNUSED_MODELS_{today_stamp()}.md"
    marker = "TASK_MODEL_DISK_RECLAIM_V1 addendum"
    if path.exists() and marker in path.read_text(encoding="utf-8"):
        print(f"  skip UNUSED_MODELS append (marker present): {path.relative_to(REPO_ROOT)}")
        return path
    header = f"# Unused models — {marker} ({today_stamp()})\n\n"
    body = [
        header,
        "Reclaimed via operator verdicts recorded inline in\n"
        "`config/PENDING_MODEL_VERDICTS.md`. Verdicts and reasons quoted verbatim.\n",
    ]
    body.append("\n## Declined (removed from disk)\n\n")
    body.append("| Tag | Size | Reason |\n|---|---|---|\n")
    dec_gb = 0.0
    declined = [e for e in entries if e["verdict"] == "decline"]
    for e in declined:
        body.append(f"| `{e['tag']}` | {e['size_gb']:.1f} GB | {e['reason'] or '(none)'} |\n")
        dec_gb += e["size_gb"]
    body.append(f"\n**Total declined: {len(declined)} models, {dec_gb:.1f} GB.**\n")

    kept = [e for e in entries if e["verdict"] == "keep-open"]
    if kept:
        body.append("\n## Kept — active investigations (not deleted)\n\n")
        body.append("| Tag | Size | Reason |\n|---|---|---|\n")
        for e in kept:
            body.append(f"| `{e['tag']}` | {e['size_gb']:.1f} GB | {e['reason'] or '(none)'} |\n")

    prom = [e for e in entries if e["verdict"] == "promote"]
    if prom:
        body.append("\n## Promoted — separate wiring task required\n\n")
        for e in prom:
            body.append(f"- `{e['tag']}` — {e['reason'] or 'follow-on wiring task pending'}\n")

    text = "".join(body)
    if execute:
        path.write_text(text)
        print(f"  wrote {path.relative_to(REPO_ROOT)}")
    else:
        print(f"  [would write] {path.relative_to(REPO_ROOT)}")
    return path


def prune_snapshot(decline_tags: list[str], execute: bool) -> int:
    if not SNAPSHOT_PATH.exists():
        print(f"  no snapshot at {SNAPSHOT_PATH}, skipping prune")
        return 0
    lines = SNAPSHOT_PATH.read_text(encoding="utf-8").splitlines()
    to_drop = set(decline_tags)
    kept = [ln for ln in lines if ln.strip() not in to_drop]
    dropped = len(lines) - len(kept)
    if dropped == 0:
        print("  snapshot: no matching tags (already pruned or never present)")
        return 0
    if execute:
        SNAPSHOT_PATH.write_text("\n".join(kept) + ("\n" if kept else ""))
        print(f"  pruned {dropped} line(s) from {SNAPSHOT_PATH.relative_to(REPO_ROOT)}")
    else:
        print(f"  [would prune] {dropped} line(s) from snapshot")
    return dropped


# -------------------- plan writer --------------------


def render_plan(decided: list[dict], portal: dict) -> tuple[str, list[dict], list[dict]]:
    """Build the plan document. Returns (markdown, actionable_decisions,
    blocked_decisions). Actionable = safe to include in the execute pass."""
    actionable = []
    blocked = []
    lines = [
        f"# Reclaim plan — {now_utc_stamp()}",
        "",
        "Generated by `scripts/execute_pending_verdicts.py --plan`. Review this doc",
        f"before invoking `--execute --plan=RECLAIM_PLAN_{now_utc_stamp()}.md`.",
        "",
        f"**{len(decided)} decided ledger entries.**",
        "",
    ]

    hist_lines = ["## Verdict histogram", ""]
    hist = Counter(e["verdict"] for e in decided)
    for v, n in sorted(hist.items()):
        gb = sum(e["size_gb"] for e in decided if e["verdict"] == v)
        hist_lines.append(f"- {v}: {n} models, {gb:.1f} GB")
    lines.extend(hist_lines + [""])

    lines.append("## Per-entry plan\n")
    for e in decided:
        safety = safety_check(e["tag"], e["verdict"], portal)
        e_full = dict(e, safety=safety)
        if e["verdict"] == "decline" and safety["block"]:
            blocked.append(e_full)
        else:
            actionable.append(e_full)
        lines.append(f"### `{e['tag']}` — {e['size_gb']:.1f} GB")
        lines.append("")
        lines.append(f"- verdict: **{e['verdict']}** — {e['reason'] or '(no reason recorded)'}")
        if e["verdict"] == "decline":
            if safety["block"]:
                lines.append("- **STATUS: BLOCKED — will not be actioned by --execute**")
            else:
                lines.append("- status: actionable")
            for f in safety["flags"]:
                lines.append(f"  - `{f['level']}` **{f['name']}**: {f['detail']}")
            lines.append(f"  - re-pull: `{safety['re_pull']}`")
        lines.append("")

    dec_actionable = [e for e in actionable if e["verdict"] == "decline"]
    if dec_actionable:
        lines.append("## Delete plan — ollama rm block (reference only)")
        lines.append("")
        lines.append("```")
        for e in dec_actionable:
            lines.append(f"ollama rm '{e['tag']}'")
        lines.append("```")
        lines.append("")
        lines.append(
            f"({len(dec_actionable)} model(s), ~{sum(e['size_gb'] for e in dec_actionable):.1f} GB)"
        )
        lines.append("")

    if blocked:
        lines.append("## Blocked declines — resolve before rerun")
        lines.append("")
        lines.append("A `bench-*` workspace in `config/portal.yaml` still routes to each of")
        lines.append("these tags. Deleting would fail `validate_system` check BB. Either:")
        lines.append("")
        lines.append("- retire the bench workspace (remove the `bench-*` block from")
        lines.append("  `config/portal.yaml`, run `./launch.sh sync-config`, commit) then")
        lines.append("  rerun this task's Phase 2/3 — or —")
        lines.append("- flip the ledger verdict from `decline` to `keep-open` (the bench")
        lines.append("  slot is worth keeping).")
        lines.append("")
        for e in blocked:
            lines.append(f"- `{e['tag']}` — routed by:")
            for f in e["safety"]["flags"]:
                if f["name"] == "still-routed":
                    for src in f["detail"].split(", "):
                        lines.append(f"  - `{src}`")

    return "\n".join(lines), actionable, blocked


def _find_plan_file(name: str) -> Path | None:
    p = Path(name)
    if not p.is_absolute():
        p = REPORTS_DIR / p.name
    if not p.exists():
        return None
    age_s = time.time() - p.stat().st_mtime
    if age_s > PLAN_FRESHNESS_S:
        print(
            f"ERROR: plan file is {age_s / 3600:.1f}h old (max 24h); rerun --plan and review the fresh one"
        )
        return None
    return p


# -------------------- main --------------------


def main() -> int:
    # Hand-rolled argv scan — argparse can't cleanly express our two-mode CLI
    # where --plan is both a bare (dry-run) flag and a value-taking arg to
    # --execute, without renaming one of them.
    raw = sys.argv[1:]
    if "--help" in raw or "-h" in raw:
        print(__doc__)
        return 0
    exec_mode = "--execute" in raw
    plan_file = None
    for a in raw:
        if a.startswith("--plan="):
            plan_file = a.split("=", 1)[1]

    decided = parse_ledger()
    print(f"Parsed {len(decided)} decided ledger entries")
    if not decided:
        print("Nothing to do — no `- [x]` entries with a `verdict:` line.")
        return 0

    portal = _load_portal()
    plan_md, actionable, blocked = render_plan(decided, portal)

    if not exec_mode:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        plan_name = f"RECLAIM_PLAN_{now_utc_stamp()}.md"
        plan_path = REPORTS_DIR / plan_name
        plan_path.write_text(plan_md)
        print(f"\nWrote plan: {plan_path.relative_to(REPO_ROOT)}")
        print(f"  actionable: {len(actionable)}")
        print(f"  BLOCKED (still-routed): {len(blocked)}")
        if blocked:
            print("  → resolve the blocked entries before running --execute, or reduce their scope")
        print("\nReview the plan, then run:")
        print(f"  python3 scripts/execute_pending_verdicts.py --execute --plan={plan_name}")
        return 0

    # execute mode
    if not plan_file:
        print("ERROR: --execute requires --plan=<FILE> pointing at a plan from a prior --plan run")
        return 2
    p = _find_plan_file(plan_file)
    if not p:
        print(f"ERROR: plan file not found or stale: {plan_file}")
        return 2
    print(f"Using plan: {p.relative_to(REPO_ROOT)}")

    if blocked:
        print(f"\nSkipping {len(blocked)} BLOCKED decline(s) — see plan for details.")
        for e in blocked:
            print(f"  BLOCK  `{e['tag']}`")

    print("\nEmitting catalog stubs...")
    for e in actionable:
        if e["verdict"] in ("decline", "promote"):
            print(f"  `{e['tag']}` ({e['verdict']}):")
            emit_catalog_stub(
                e["tag"], e["size_gb"], e["verdict"], e["reason"], e["safety"], execute=True
            )

    print("\nUpdating UNUSED_MODELS doc...")
    append_unused_models_entry(actionable, execute=True)

    print("\nPruning snapshot...")
    decline_tags = [e["tag"] for e in actionable if e["verdict"] == "decline"]
    prune_snapshot(decline_tags, execute=True)

    if decline_tags:
        print("\n" + "=" * 72)
        print("OPERATOR ACTION — run these on the box to reclaim disk:")
        print("=" * 72)
        for t in decline_tags:
            print(f"ollama rm '{t}'")
        print("=" * 72)
        print(f"({len(decline_tags)} model(s) — verify with `ollama list` after)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
