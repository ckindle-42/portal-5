#!/usr/bin/env python3
"""Ground-truth preflight for the three execute suites (bench, sec, acceptance).

Read-only. Prints current counts and vocabularies so an execute agent confirms
reality instead of trusting doc-baked numbers. Run at the start of every
bench/sec/acceptance session.

    python3 scripts/execute_preflight.py            # human-readable
    python3 scripts/execute_preflight.py --json      # machine-readable
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import yaml

RETIRED_ALIASES = [
    "auto-coding-agentic",
    "auto-coding-northmini",
    "auto-coding-uncensored",
    "auto-coding-uncensored-agentic",
    "auto-agentic",
    "auto-agentic-lite",
    "auto-agentic-ornith",
    "auto-security-uncensored",
    "auto-pentest",
    "auto-blueteam",
    "auto-redteam",
    "auto-redteam-deep",
    "auto-purpleteam",
    "auto-purpleteam-deep",
    "auto-purpleteam-exec",
    "auto-devstral",
    "auto-glm",
    "auto-glm-thinking",
    "auto-mistral",
    "auto-phi4",
    "auto-gemma-e4b",
    "auto-gemma-fast",
    "auto-gemma-vision",
]


def _load_yaml(path: str) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def gather() -> dict:
    d = _load_yaml("config/portal.yaml")
    ws = d["workspaces"]
    prod = sorted(w for w, c in ws.items() if (c or {}).get("module") != "eval")
    ev = sorted(w for w, c in ws.items() if (c or {}).get("module") == "eval")
    personas = sorted(
        _load_yaml(f).get("slug", os.path.basename(f)[:-5])
        for f in glob.glob("config/personas/*.yaml")
    )
    # security canonical variants (base::variant) the sec bench addresses
    sec_variants = []
    sec = (ws.get("auto-security") or {}).get("variants") or {}
    for v in sec:
        sec_variants.append(f"auto-security::{v}")
    # model_pin personas (served-model correctness — from the intent fix)
    pinned = []
    for f in glob.glob("config/personas/*.yaml"):
        p = _load_yaml(f)
        if p.get("model_pin"):
            pinned.append((p.get("slug"), p["model_pin"]))
    return {
        "production_workspaces": prod,
        "eval_workspaces": ev,
        "personas": personas,
        "security_variants": sorted(sec_variants),
        "model_pin_personas": sorted(pinned),
        "counts": {
            "production": len(prod),
            "eval": len(ev),
            "total": len(ws),
            "personas": len(personas),
            "mcp_fleet": len(d["mcp_fleet"]),
        },
    }


def check_no_retired_aliases() -> list[str]:
    """Fail loud if a retired alias reappears as a workspace id."""
    d = _load_yaml("config/portal.yaml")
    return [a for a in RETIRED_ALIASES if a in d["workspaces"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    g = gather()
    leaked = check_no_retired_aliases()
    if args.json:
        g["retired_alias_leak"] = leaked
        print(json.dumps(g, indent=2))
        return 1 if leaked else 0
    c = g["counts"]
    print("=" * 60)
    print("PORTAL 5 EXECUTE PREFLIGHT — current ground truth")
    print("=" * 60)
    print(f"Production workspaces (acceptance/UAT scope, eval OFF): {c['production']}")
    print(f"Eval/bench workspaces (need PORTAL_ENABLE_EVAL=1):      {c['eval']}")
    print(f"Total workspaces:                                       {c['total']}")
    print(f"Personas:                                               {c['personas']}")
    print(f"MCP fleet:                                              {c['mcp_fleet']}")
    print()
    print("Production workspaces:")
    for w in g["production_workspaces"]:
        print(f"  {w}")
    print()
    print("Security canonical variants (sec-bench --workspaces targets):")
    for v in g["security_variants"]:
        print(f"  {v}")
    print()
    print(
        f"model_pin personas (served-model-corrected, verify these serve the pin): {len(g['model_pin_personas'])}"
    )
    for slug, pin in g["model_pin_personas"]:
        print(f"  {slug} -> {pin}")
    print()
    if leaked:
        print("!!! RETIRED ALIAS LEAK — these should not exist as workspaces:")
        for a in leaked:
            print(f"    {a}")
        print("    STOP — the surface regressed; do not run the suite.")
        return 1
    print("No retired aliases present. Surface is canonical. OK to run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
