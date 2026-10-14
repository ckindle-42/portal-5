"""WFE production tool mode (root-fix Part 2a).

A workspace listed in tests/wfe/tool_modes.yaml with `tool_mode: production` runs its
OWN tools through the pipeline under an evaluation scope (portal.platform.mcp_host.
eval_scope), instead of the harness's sandbox tools: no harness tools, no harness note,
fixtures staged in the run's namespace, creation receipts validated, and a
receipt-based cleanup that deletes only what the row owns.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

import yaml

from portal.platform.mcp_host import eval_scope

TOOL_MODES = Path(__file__).resolve().parent / "tool_modes.yaml"
OUTPUT_ROOT = Path(os.environ.get("AI_OUTPUT_DIR") or Path.home() / "AI_Output")
DATA_MCP_URL = os.environ.get("WFE_DATA_MCP_URL", "http://localhost:8939").rstrip("/")


def mode_for(workspace: str) -> dict | None:
    """The workspace's production tool mode ({tool_mode, allow}), or None for sandbox."""
    modes = (yaml.safe_load(TOOL_MODES.read_text()) or {}).get("workspaces") or {}
    m = modes.get(workspace)
    return m if m and m.get("tool_mode") == "production" else None


def tokens(campaign_id: str, run_id: str) -> tuple[str, str]:
    """Bounded physical identifiers; the logical run_id contains | : / and long model ids."""
    camp = "wfe_" + hashlib.sha256(campaign_id.encode()).hexdigest()[:16]
    run = "wfe_" + hashlib.sha256(f"{campaign_id}\0{run_id}".encode()).hexdigest()[:40]
    return camp, run


def _inventory(root: Path) -> dict[str, str]:
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def prepare(pipe: bool, r: dict, manifest: dict, task: dict, wsc: dict, harness: dict):
    """(task, wsc, ctx). In production mode: the scope goes in the harness, the prompt loses
    the harness note, fixtures are staged in the run's `in/`, and the pre-run inventory is
    taken. Otherwise everything is returned unchanged with ctx None."""
    m = mode_for(r["workspace"]) if pipe else None
    if not m:
        return task, wsc, None
    camp, run = tokens(manifest["campaign_id"], r["run_id"])
    scope = {"campaign": camp, "run": run, "allow": sorted(m["allow"])}
    root = eval_scope.run_root(OUTPUT_ROOT, scope)
    cleanup({"scope": scope, "root": root, "inventory": {}}, None, r)  # a re-run starts clean
    root = eval_scope.run_root(OUTPUT_ROOT, scope)
    for rel, body in (task.get("seed") or {}).items():
        dest = eval_scope.confine(OUTPUT_ROOT, scope, rel, sub="in")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body)
    ctx = {"scope": scope, "root": root, "inventory": _inventory(root)}
    harness["pipeline_eval"] = scope
    wsc = {
        **wsc,
        "system_prompt_pipeline": wsc["system_prompt_base"],
        "tool_surface": sorted(m["allow"]),
    }
    return {**task, "_eval": ctx}, wsc, ctx


def receipts(ctx: dict) -> list[dict]:
    """Creation receipts that hold: inside the run's out/, absent before the run, unchanged."""
    f = ctx["root"] / ".receipts.jsonl"
    out = []
    for line in f.read_text().splitlines() if f.exists() else []:
        rec = json.loads(line)
        # The MCP's `path` is in its own filesystem view (a container mount); `rel` is not.
        p = (ctx["root"] / rec["rel"]).resolve() if rec.get("rel") else Path(rec["path"]).resolve()
        rec["host_path"] = str(p)
        if (ctx["root"] / "out") not in p.parents or not p.is_file():
            rec["valid"] = "outside out/ or missing"
        elif str(p) in ctx["inventory"]:
            rec["valid"] = "existed before the row"
        elif hashlib.sha256(p.read_bytes()).hexdigest() != rec["sha256"]:
            rec["valid"] = "changed after creation"
        else:
            rec["valid"] = True
        out.append(rec)
    return out


def finish(ctx: dict | None, out: dict, campaign_dir: Path, r: dict) -> dict:
    """Record receipts, keep receipted artifacts in the campaign, then clean up the row."""
    if not ctx:
        return out
    recs = receipts(ctx)
    keep = campaign_dir / "artifacts" / hashlib.sha256(r["run_id"].encode()).hexdigest()[:12]
    for rec in (x for x in recs if x["valid"] is True):
        keep.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rec["host_path"], keep / Path(rec["host_path"]).name)
    # In evidence, which is persisted: ResultRow drops keys it does not declare.
    ev = {
        **(out.get("evidence") or {}),
        "receipts": recs,
        "tool_mode": "production",
        "eval_scope": ctx["scope"],
    }
    out = {**out, "evidence": ev}
    cleanup(ctx, campaign_dir, r)
    return out


DATA_TOOLS = ("attach_source", "run_sql", "profile_table", "list_session")


def close_data_session(scope: dict) -> str | None:
    """Close and delete the run's data session through the data MCP's scope-only route."""
    req = urllib.request.Request(
        f"{DATA_MCP_URL}/eval/close_session",
        data=json.dumps({"eval": scope}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # noqa: BLE001
        return str(e)
    return None


def cleanup(ctx: dict, campaign_dir: Path | None, r: dict) -> list[str]:
    """Write the inventory first, then delete exactly it; the data session goes through the
    data MCP's own scope-only route. Never deletes outside the run root."""
    root, scope = ctx["root"], ctx["scope"]
    listed = sorted(str(p) for p in root.rglob("*") if p.is_file())
    if campaign_dir is not None:
        d = campaign_dir / "cleanup"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{scope['run']}.json").write_text(
            json.dumps({"run_id": r["run_id"], "files": listed}, indent=1)
        )
    if any(t in scope["allow"] for t in DATA_TOOLS):
        err = close_data_session(scope)
        if err:
            listed.append(f"data session not closed: {err}")
    for f in listed:
        p = Path(f)
        if p.is_file() and root in p.resolve().parents:
            p.unlink()
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        d.rmdir() if not any(d.iterdir()) else None
    for d in (
        root,
        root.parent,
    ):  # the run, then its campaign directory; never the shared wfe/ root
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return listed
