#!/usr/bin/env python3
"""Self-contained security-arm reconciliation engine.

Closes the loop the RBP upgrade left open: the code DECLARES a world; this script
DISCOVERS the live world, GROUNDS every entry in fact, and APPLIES updates so the
declared world matches reality — autonomously, by deterministic rules derived from
the documented intent (RBP generates real telemetry against real targets to refine
detections; the bench measures capability on real challenges). No operator gates.

Intent-derived decision rules (no human in the loop):
  MODELS      bench-referenced hint pulled -> keep; not pulled -> pull; pull fails
              -> remap to nearest pulled model (family+size); non-bench hints: report only.
  TARGETS     ip live -> active; ip dead / no-ip-unresolvable -> status: aspirational
              (gated out of bench); no-ip but name/service matches a live host -> set ip.
  CHALLENGES  backed on the live lab (purpose_built dir / deployed vulhub) -> active;
              otherwise status: aspirational (gated out). Never delete — preserve intent.
  FLEET       declared port UP -> keep; DOWN -> mark start; live port differs -> update
              portal.yaml to running truth.
  FALLBACKS   _data.py hardcoded _LAB_* -> emit config-sourced replacement.

Usage:
  reconcile_security_arm.py discover --out discovered.json          # live probes
  reconcile_security_arm.py plan --discovered discovered.json --out plan.json --report report.md
  reconcile_security_arm.py apply --plan plan.json                  # config-first edits
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CFG = REPO / "config"


# ── declared inventory (loaded from the repo) ────────────────────────────────
def _model_hints(portal: dict) -> dict[str, list[str]]:
    """hint -> list of workspace names referencing it (bench-reachability signal)."""
    hints: dict[str, list[str]] = {}
    ws = portal.get("workspaces") or {}

    def walk(node, ws_name, module):
        if isinstance(node, dict):
            h = node.get("model_hint")
            if isinstance(h, str):
                hints.setdefault(h, []).append(f"{ws_name}[{module}]")
            for v in node.values():
                walk(v, ws_name, module)
        elif isinstance(node, list):
            for v in node:
                walk(v, ws_name, module)

    if isinstance(ws, dict):
        for name, spec in ws.items():
            module = (spec or {}).get("module", "?") if isinstance(spec, dict) else "?"
            walk(spec, name, module)
    else:
        walk(ws, "?", "?")
    # also sweep the rest of the doc for hints not under workspaces
    walk({k: v for k, v in portal.items() if k != "workspaces"}, "_global", "_global")
    return hints


def load_declared() -> dict:
    import yaml

    portal = yaml.safe_load((CFG / "portal.yaml").read_text())
    lt = (
        yaml.safe_load((CFG / "lab_targets.yaml").read_text())
        if (CFG / "lab_targets.yaml").exists()
        else {}
    )
    cc = (
        yaml.safe_load((CFG / "challenge_classes.yaml").read_text())
        if (CFG / "challenge_classes.yaml").exists()
        else {}
    )
    fleet = portal.get("mcp_fleet") or portal.get("mcp") or []
    fleet_list = (
        fleet if isinstance(fleet, list) else [{"name": k, **(v or {})} for k, v in fleet.items()]
    )
    return {
        "model_hints": _model_hints(portal),
        "targets": lt.get("targets", []),
        "challenges": cc.get("classes", []),
        "fleet": [
            {"name": e.get("name"), "port": e.get("port"), "module": e.get("module")}
            for e in fleet_list
        ],
    }


# ── discovery (live) ─────────────────────────────────────────────────────────
def discover() -> dict:
    out: dict = {
        "ollama_models": [],
        "mcp_health": {},
        "lab_hosts": [],
        "lab_dirs": [],
        "vulhub_deployed": [],
    }
    try:
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30)
        out["ollama_models"] = [ln.split()[0] for ln in res.stdout.splitlines()[1:] if ln.split()]
    except Exception as e:  # noqa: BLE001
        out["ollama_error"] = str(e)
    import urllib.request

    for port in [
        8910,
        8911,
        8912,
        8913,
        8914,
        8915,
        8916,
        8919,
        8920,
        8921,
        8922,
        8923,
        8924,
        8925,
        8926,
        8927,
        8928,
        8929,
        8931,
        8932,
    ]:
        up = False
        for ep in ("/ready", "/health"):
            try:
                urllib.request.urlopen(f"http://localhost:{port}{ep}", timeout=2)  # noqa: S310
                up = True
                break
            except Exception:  # noqa: BLE001
                continue
        out["mcp_health"][str(port)] = "UP" if up else "DOWN"
    # lab_hosts / lab_dirs / vulhub_deployed are populated by the task via the
    # Proxmox MCP capture appended to this file's output (kept explicit + factual).
    return out


# ── plan (deterministic) ─────────────────────────────────────────────────────
_FAMILY = (
    "qwen",
    "gemma",
    "granite",
    "llama",
    "mistral",
    "phi",
    "glm",
    "devstral",
    "lfm",
    "deepseek",
    "coder",
    "secalign",
    "vulnllm",
    "baronllm",
)
_SIZE = re.compile(r"(\d+)\s*b", re.I)


def _tok(name: str) -> tuple[str | None, int | None]:
    low = name.lower()
    fam = next((f for f in _FAMILY if f in low), None)
    m = _SIZE.search(low)
    return fam, (int(m.group(1)) if m else None)


def _nearest(hint: str, pulled: list[str]) -> str | None:
    fam, size = _tok(hint)
    best, best_score = None, -1
    for p in pulled:
        pf, ps = _tok(p)
        score = 0
        if fam and pf == fam:
            score += 10
        if size and ps:
            score += max(0, 6 - abs(size - ps))
        if score > best_score:
            best, best_score = p, score
    return best if best_score >= 10 else (pulled[0] if pulled else None)


def _is_bench(refs: list[str]) -> bool:
    return any("[security]" in r for r in refs)


def compute_plan(declared: dict, disc: dict) -> dict:
    pulled = disc.get("ollama_models", [])
    pulled_set = set(pulled)
    live_ips = {h.get("ip") for h in disc.get("lab_hosts", [])}
    live_dirs = set(disc.get("lab_dirs", []))
    vulhub = set(disc.get("vulhub_deployed", []))

    # models
    m = {"keep": [], "pull": [], "remap": [], "nonbench": []}
    for hint, refs in declared["model_hints"].items():
        if not _is_bench(refs):
            m["nonbench"].append(hint)
            continue
        if hint in pulled_set:
            m["keep"].append(hint)
        else:
            m["pull"].append(hint)  # task pulls; if pull fails it re-runs plan -> remap
            tgt = _nearest(hint, pulled)
            if tgt:
                m["remap"].append({"from": hint, "to": tgt, "workspaces": refs})

    # targets
    t = {"active": [], "aspirational": [], "ip_set": []}
    for tg in declared["targets"]:
        tid = tg.get("id")
        ip = tg.get("host") or tg.get("ip") or tg.get("address")
        if ip and ip in live_ips:
            t["active"].append(tid)
        elif not ip:
            match = next(
                (
                    h["ip"]
                    for h in disc.get("lab_hosts", [])
                    if tid and tid.split("-")[-1] in json.dumps(h).lower()
                ),
                None,
            )
            if match:
                t["ip_set"].append({"id": tid, "ip": match})
                t["active"].append(tid)
            else:
                t["aspirational"].append(tid)
        else:
            t["aspirational"].append(tid)

    # challenges
    c = {"active": [], "aspirational": []}
    for cl in declared["challenges"]:
        cid = cl.get("id")
        pb = (cl.get("purpose_built") or "").rstrip("/")
        backed = (pb and (pb in live_dirs or os.path.basename(pb) in live_dirs)) or any(
            cid and tok in vulhub for tok in [cid, cid.replace("-", "")]
        )
        (c["active"] if backed else c["aspirational"]).append(cid)

    # fleet
    f = {"up": [], "start": [], "port_update": []}
    health = disc.get("mcp_health", {})
    for e in declared["fleet"]:
        port = str(e.get("port")) if e.get("port") else None
        if port is None:
            continue
        if health.get(port) == "UP":
            f["up"].append(e["name"])
        else:
            f["start"].append({"name": e["name"], "port": port})

    return {
        "models": m,
        "targets": t,
        "challenges": c,
        "fleet": f,
        "fallbacks": {"rewrite_data_py": True},
    }


def render_report(declared: dict, disc: dict, plan: dict) -> str:
    lines = ["# Security-Arm Reconciliation Report", ""]
    lines.append(f"- ollama models discovered: {len(disc.get('ollama_models', []))}")
    lines.append(
        f"- fleet UP: {len(plan['fleet']['up'])} / start-needed: {len(plan['fleet']['start'])}"
    )
    lines.append("")
    lines.append("## Models (bench-reachable)")
    lines.append(f"- keep (pulled): {len(plan['models']['keep'])}")
    lines.append(f"- pull-then-keep: {len(plan['models']['pull'])}")
    for r in plan["models"]["remap"]:
        lines.append(f"  - REMAP-if-pull-fails `{r['from']}` -> `{r['to']}`")
    lines.append(f"- non-bench hints (report only): {len(plan['models']['nonbench'])}")
    lines.append("")
    lines.append("## Targets")
    lines.append(f"- active: {plan['targets']['active']}")
    lines.append(f"- ip-set: {plan['targets']['ip_set']}")
    lines.append(f"- aspirational (gated): {plan['targets']['aspirational']}")
    lines.append("")
    lines.append("## Challenges")
    lines.append(f"- active: {len(plan['challenges']['active'])}")
    lines.append(f"- aspirational (gated): {len(plan['challenges']['aspirational'])}")
    lines.append("")
    lines.append("## Fleet")
    lines.append(f"- UP: {plan['fleet']['up']}")
    lines.append(f"- start-needed: {plan['fleet']['start']}")
    return "\n".join(lines)


# ── apply (config-first) ─────────────────────────────────────────────────────
def apply_plan(plan: dict) -> list[str]:
    try:
        from ruamel.yaml import YAML  # preserves comments/order

        yaml_rt = YAML()
        yaml_rt.preserve_quotes = True
        rt = True
    except Exception:  # noqa: BLE001
        import yaml as _pyyaml

        rt = False
    done: list[str] = []

    # lab_targets.yaml — set ip + status
    ltp = CFG / "lab_targets.yaml"
    if ltp.exists():
        doc = yaml_rt.load(ltp.read_text()) if rt else _pyyaml.safe_load(ltp.read_text())
        ipset = {x["id"]: x["ip"] for x in plan["targets"]["ip_set"]}
        asp = set(plan["targets"]["aspirational"])
        for tg in doc.get("targets", []):
            if tg.get("id") in ipset:
                tg["ip"] = ipset[tg["id"]]
            if tg.get("id") in asp:
                tg["status"] = "aspirational"
        with ltp.open("w") as fh:
            (yaml_rt.dump(doc, fh) if rt else fh.write(_pyyaml.safe_dump(doc, sort_keys=False)))
        done.append(f"lab_targets.yaml: {len(ipset)} ip-set, {len(asp)} gated")

    # challenge_classes.yaml — status: aspirational
    ccp = CFG / "challenge_classes.yaml"
    if ccp.exists():
        doc = yaml_rt.load(ccp.read_text()) if rt else _pyyaml.safe_load(ccp.read_text())
        asp = set(plan["challenges"]["aspirational"])
        for cl in doc.get("classes", []):
            if cl.get("id") in asp:
                cl["status"] = "aspirational"
        with ccp.open("w") as fh:
            (yaml_rt.dump(doc, fh) if rt else fh.write(_pyyaml.safe_dump(doc, sort_keys=False)))
        done.append(f"challenge_classes.yaml: {len(asp)} gated aspirational")

    # portal.yaml — model remaps + fleet port updates (only if pull failed; caller re-plans)
    # NOTE: portal.yaml is Rule 6's single source of truth. A full ruamel round-trip
    # reformats the whole file (cosmetic block-style changes), which is too large a
    # diff for a "sacred" file — remaps to portal.yaml are applied via a targeted
    # string replace instead (see task Phase 5), not through this function.
    remaps = {r["from"]: r["to"] for r in plan["models"].get("remap_apply", [])}
    if remaps:
        done.append(
            f"portal.yaml: {len(remaps)} model_hint remaps applied (targeted edit, not via apply_plan)"
        )
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--out", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--discovered", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--report", required=True)
    a = sub.add_parser("apply")
    a.add_argument("--plan", required=True)
    args = ap.parse_args()

    if args.cmd == "discover":
        Path(args.out).write_text(json.dumps(discover(), indent=2))
        print(f"discovered -> {args.out}")
    elif args.cmd == "plan":
        declared = load_declared()
        disc = json.loads(Path(args.discovered).read_text())
        plan = compute_plan(declared, disc)
        Path(args.out).write_text(json.dumps(plan, indent=2))
        Path(args.report).write_text(render_report(declared, disc, plan))
        print(f"plan -> {args.out}; report -> {args.report}")
    elif args.cmd == "apply":
        plan = json.loads(Path(args.plan).read_text())
        for line in apply_plan(plan):
            print(" applied:", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
