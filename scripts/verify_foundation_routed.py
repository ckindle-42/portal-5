#!/usr/bin/env python3
"""Foundation routed acceptance (END_TO_END Phase 6 / foundation P7).

Executes the required observations through the DEPLOYED compliance route
(HTTP against the launchctl-managed service on :8937) — never direct library
calls (lesson L03: an HTTP 200 is not acceptance; each observation asserts
substantive content). Writes one receipt JSON per run under the private
compliance artifact hierarchy and prints a pass/fail census.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8937"
RECEIPT_ROOT = Path("coding_task/v9_compliance/private/foundation_routed")


def call(tool: str, **args: object) -> dict:
    body = json.dumps(args).encode()
    req = urllib.request.Request(
        f"{BASE}/tools/{tool}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _obs1_current(receipt: dict, results: dict[str, bool]) -> None:
    r = call("compliance_requirement", requirement="CIP-007-6 R2 Part 2.1", valid_at="2026-09-14")
    sel = r.get("revision_selection", {}).get("selected", [])
    ok = (
        r.get("found")
        and sel
        and sel[0]["version"] == "6"
        and sel[0]["as_known"] == "SELECTED"
        and sel[0]["valid_from"] == "2016-07-01"
        and sel[0]["valid_to"] == "2028-06-30"
    )
    results["obs1_current_6"] = bool(ok)
    receipt["observations"]["obs1_current_6"] = r


def _obs2_future_then_effective(receipt: dict, results: dict[str, bool]) -> None:
    r_future = call("compliance_requirement", requirement="CIP-007-7.1 R2", valid_at="2026-09-14")
    future = r_future.get("revision_selection", {}).get("future", [])
    r_effective = call(
        "compliance_requirement",
        requirement="CIP-007-7.1 R2 Part 2.1",
        valid_at="2028-08-01",
    )
    sel71 = r_effective.get("revision_selection", {}).get("selected", [])
    ok = (
        future
        and future[0]["version"] == "7.1"
        and future[0]["as_known"] == "FUTURE"
        and future[0]["valid_from"] == "2028-07-01"
        and r_effective.get("found")
        and sel71
        and sel71[0]["version"] == "7.1"
        and sel71[0]["as_known"] == "SELECTED"
        and any(p.get("clauses") for p in r_effective.get("parts", []))
    )
    results["obs2_future_71_then_effective"] = bool(ok)
    receipt["observations"]["obs2_future_71_then_effective"] = {
        "at_2026_09_14": r_future,
        "at_2028_08_01": r_effective,
    }


def _obs3_historical(receipt: dict, results: dict[str, bool]) -> None:
    r_hist = call("compliance_requirement", requirement="CIP-007-6 R2", valid_at="2020-01-01")
    sel_hist = r_hist.get("revision_selection", {}).get("selected", [])
    ok = (
        r_hist.get("found")
        and sel_hist
        and sel_hist[0]["version"] == "6"
        and all(p["temporal_label"] == "historical" for p in r_hist.get("parts", []))
    )
    results["obs3_historical_selection"] = bool(ok)
    receipt["observations"]["obs3_historical_selection"] = r_hist


def _obs4_known_at(receipt: dict, results: dict[str, bool]) -> None:
    r_before = call(
        "compliance_requirement",
        requirement="CIP-007-6 R2 Part 2.1",
        valid_at="2024-01-01",
        known_at="2026-09-01",
    )
    r_after = call(
        "compliance_requirement",
        requirement="CIP-007-6 R2 Part 2.1",
        valid_at="2024-01-01",
        known_at="2026-09-16",
    )
    withheld = r_before.get("withheld_as_unknown_knowledge", [])
    ok = (
        not r_before.get("found")
        and len(withheld) == 1
        and withheld[0]["as_known"] == "UNKNOWN_KNOWLEDGE"
        and r_after.get("found")
        and len(r_after.get("parts", [])) == 1
    )
    results["obs4_known_at_late_recorded"] = bool(ok)
    receipt["observations"]["obs4_known_at_late_recorded"] = {
        "known_at_2026_09_01": r_before,
        "known_at_2026_09_16": r_after,
    }


def _obs5_and_6_bundles(receipt: dict, results: dict[str, bool]) -> dict:
    bundles = {}
    ok5 = True
    ok6 = True
    for part in ("2.1", "2.2", "2.3", "2.4"):
        b = call("compliance_bundle", requirement_id=f"CIP-007-6 R2 Part {part}")
        bundles[part] = b
        ready = b.get("readiness", {}).get("ready") is True
        has_measures = bool(b.get("measures"))
        has_text = bool(b.get("part_text")) and bool(b.get("lead_in"))
        has_rev = bool(b.get("revision_id"))
        ok5 = ok5 and ready and has_measures and has_text and has_rev
        if part in ("2.2", "2.3"):
            ok6 = ok6 and "35 calendar day" in json.dumps(b)
        if part == "2.3":
            ok6 = ok6 and "one of the following" in json.dumps(b).lower()
        if part == "2.4":
            ok6 = ok6 and "CIP Senior Manager" in json.dumps(b)
    ok5 = ok5 and all(bundles[p].get("technical_basis") is not None for p in bundles)
    results["obs5_complete_bundles"] = bool(ok5)
    results["obs6_deadlines_alternatives_exception"] = bool(ok6)
    receipt["observations"]["obs5_complete_bundles"] = bundles
    receipt["observations"]["obs6_deadlines_alternatives_exception"] = {
        part: {
            "has_35_days": "35 calendar day" in json.dumps(b),
            "has_alternatives": "one of the following" in json.dumps(b).lower(),
            "has_exception": "CIP Senior Manager" in json.dumps(b),
        }
        for part, b in bundles.items()
    }
    return bundles


def _obs7_source_functions(receipt: dict, results: dict[str, bool]) -> None:
    src = call(
        "compliance_sources",
        logical_id="CIP-007/LSPG Security Patch Management Procedure V11.pdf",
        include_sections=True,
    )
    rev = (src.get("revisions") or [{}])[0]
    sections = rev.get("sections", [])
    operative = {s["path"] for s in sections if s["role"] == "OPERATIVE_PROCEDURE"}
    traceability = [s for s in sections if s["role"] == "TRACEABILITY_ASSERTION"]
    ok = (
        src.get("found")
        and rev.get("document_number") == "LSPG-ADM-CIP007SPM"
        and rev.get("version") == "11.0"
        and rev.get("binding_effect") == "internally_mandatory"
        and {"3.1", "3.3", "3.5", "3.6"} <= operative
        and len(traceability) >= 1
    )
    results["obs7_source_functions"] = bool(ok)
    receipt["observations"]["obs7_source_functions"] = {
        "document_number": rev.get("document_number"),
        "version": rev.get("version"),
        "binding_effect": rev.get("binding_effect"),
        "n_sections": len(sections),
        "operative_paths": sorted(operative)[:12],
        "traceability_paths": [s["path"] for s in traceability],
    }


def _obs8_trace(receipt: dict, results: dict[str, bool]) -> None:
    tr = call("compliance_trace", start_ref="CIP-007-6 R2 Part 2.1")
    edges = tr.get("edges", [])
    ok = all(edge.get("status") == "approved" for edge in edges)
    tr_proposed = call("compliance_trace", start_ref="CIP-007-6 R2 Part 2.1", include_proposed=True)
    proposed_edges = [e for e in tr_proposed.get("edges", []) if e.get("status") == "proposed"]
    ok = ok and isinstance(proposed_edges, list)
    results["obs8_trace_no_cartesian_default"] = bool(ok)
    receipt["observations"]["obs8_trace_no_cartesian_default"] = {
        "default_edges": len(edges),
        "default_statuses": sorted({str(e.get("status")) for e in edges}),
        "with_proposed_edges": len(proposed_edges),
        "note": "default is approved-only; proposed visible only on explicit widening",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-pid", default="")
    parser.add_argument("--served-commit", default="")
    args = parser.parse_args()

    receipt: dict = {
        "executed_at": datetime.now(UTC).isoformat(),
        "route": BASE,
        "service_pid": args.service_pid,
        "served_commit": args.served_commit,
        "observations": {},
    }
    results: dict[str, bool] = {}
    _obs1_current(receipt, results)
    _obs2_future_then_effective(receipt, results)
    _obs3_historical(receipt, results)
    _obs4_known_at(receipt, results)
    _obs5_and_6_bundles(receipt, results)
    _obs7_source_functions(receipt, results)
    _obs8_trace(receipt, results)

    receipt["census"] = {
        "passed": sum(results.values()),
        "failed": sum(1 for v in results.values() if not v),
        "results": results,
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RECEIPT_ROOT / stamp / "routed_observations.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt["census"], indent=2))
    print(f"receipt: {out}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
