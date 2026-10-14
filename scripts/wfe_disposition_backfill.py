#!/usr/bin/env python3
"""Classify the model-fleet closeout register, and say what each removal costs.

WFE_ROOT_FIX program, Part 1 Phase 3 build step 8, corrected by P1R. The
closeout (`docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json`) is the authoritative
disposition register: every identity is INTEGRATED, RETAINED_FOR_PURPOSE or
REMOVED_CLOSED. It does not say whether a removal can be undone, or which
removals rest on a measurement the instrument audits found biased.

Whether a removal can be undone is a question for the registry, not for what
happened to be installed at closeout. For each removed Ollama identity this asks
the registry for the manifest of the tag `ollama pull` would fetch, and compares
its layers with the `model_layer_digests` the register recorded:

  verified      the registry serves the tag and its layers include the recorded
                digest(s): `ollama pull` restores the artifact that was measured;
  differs       the registry serves the tag, but not the build that was measured;
  unrecorded    the registry serves the tag; the register recorded no digest;
  unrestorable  the registry does not serve it (Portal's local `portal5/` tags,
                withdrawn tags), or it is an oMLX directory with no known source;
  unverified    the registry could not be asked. --write refuses while any
                removal is unverified.

Portal's `-ctxNk` tags are local: `models apply-params` creates them FROM a base
tag with `PARAMETER num_ctx`. Their recipe pulls the base and recreates the
variant, and the base is what the registry is asked about.

A removal that is not restorable enters `tests/wfe/candidate_queue.yaml` with
`available: false`, so every cell it could have had is MISSING and the
disposition it supports can only be NO_DECISION.

Usage:
    uv run python scripts/wfe_disposition_backfill.py                   # no network
    uv run python scripts/wfe_disposition_backfill.py --verify          # ask the registries
    uv run python scripts/wfe_disposition_backfill.py --verify --write  # receipt, queue, doc
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CLOSEOUT = REPO / "docs" / "MODEL_FLEET_CLOSEOUT_20260906.tasks.json"
RECEIPT = REPO / "docs" / "WFE_DISPOSITION_BACKFILL_20261014.json"
QUEUE = REPO / "tests" / "wfe" / "candidate_queue.yaml"
DOC = REPO / "docs" / "WFE_ROOT_CAUSES_20261013.md"
REGISTRY = os.environ.get("WFE_OLLAMA_REGISTRY", "https://registry.ollama.ai")
HF_REGISTRY = os.environ.get("WFE_HF_REGISTRY", "https://hf.co")
_CTX = re.compile(r"^(?P<base>.+)-ctx(?P<k>\d+)k$")

#: identity -> a pullable tag whose weights are the recorded digest, for removals
#: the register recorded without an upstream source. The verification below then
#: checks it like any other; an entry that fails it stays unrestorable.
RESTORE_SOURCES: dict[str, str] = {}

#: The removals the 2026-10-13 audits found resting on a biased measurement.
#: Four are judgment-probe-v6 stop-rule verdicts, one is the research probe.
#: Specified in docs/WFE_ROOT_CAUSES_20261013.md, "Decisions at risk".
AT_RISK = {
    "ollama:command-r:35b-08-2024-q4_K_M": "judgment probe v6: the stop rule's 'else REMOVED' fired",
    "ollama:granite4.1:8b-q8_0": "judgment probe v6: stop rule fired on +0.06 exact (about 2 of 30 tasks)",
    "ollama:granite4.2:30b-q4_K_M": "judgment probe v6: stop rule fired on a like-for-like comparator",
    "ollama:hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M": "judgment probe v6: duplicate-quant stop rule fired on exact parity",
    "ollama:portal5/xyz-aquila-mini:q4_k_m-ctx16k": "research probe: the lane instrument's checkers were weak (defect 10)",
}

#: Every classification the backfill assigns.
CLASSES = (
    "integrated",
    "retained_for_purpose",
    "removed_restorable",
    "removed_unrestorable",
    "removed_unverified",
)
RESTORABLE = ("verified", "differs", "unrecorded")


def pull_plan(identity: str) -> tuple[str, int | None]:
    """(the tag to pull, the num_ctx to recreate, or None) for an Ollama identity."""
    name, sep, tag = identity.rpartition(":")
    m = _CTX.match(tag) if sep else None
    if not m:
        return identity, None
    return f"{name}:{m['base']}", int(m["k"]) * 1024


def manifest_url(tag: str) -> str:
    """Where the registry `ollama pull` would use publishes this tag's manifest."""
    name, sep, ref = tag.rpartition(":")
    if not sep:
        name, ref = tag, "latest"
    if name.startswith("hf.co/"):
        return f"{HF_REGISTRY}/v2/{name.removeprefix('hf.co/')}/manifests/{ref}"
    return f"{REGISTRY}/v2/{name if '/' in name else 'library/' + name}/manifests/{ref}"


def registry_layers(tag: str, opener=urllib.request.urlopen) -> tuple[str, set[str]]:
    """("found" | "absent (…)" | "unreachable (…)", the manifest's layer digests)."""
    req = urllib.request.Request(
        manifest_url(tag),
        headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
    )
    try:
        with opener(req, timeout=30) as r:
            doc = json.load(r)
    except urllib.error.HTTPError as e:
        # 403 is a proxy or a gated repo, not "the registry does not serve it".
        state = "absent" if e.code in (401, 404) else "unreachable"
        return f"{state} (HTTP {e.code})", set()
    except Exception as e:
        return f"unreachable ({e})", set()
    return "found", {str(x["digest"]) for x in doc.get("layers") or [] if x.get("digest")}


def recipe(identity: str, pull: str, ctx: int | None) -> str:
    """The exact commands that restore one identity."""
    if not ctx:
        return f"ollama pull {pull}"
    mf = "/tmp/" + re.sub(r"[^A-Za-z0-9._-]", "_", identity) + ".Modelfile"
    return (
        f"ollama pull {pull} && printf 'FROM {pull}\\nPARAMETER num_ctx {ctx}\\n' > {mf}"
        f" && ollama create {identity} -f {mf}"
    )


def _verdict(cls: str, restorable: str, how: str, verification: str = "n/a") -> dict:
    return {"class": cls, "restorable": restorable, "recipe": how, "verification": verification}


def classify(item: dict, lookup=None) -> dict:
    """Class, restorability, the exact recipe, and how restorability was settled.
    `lookup(tag)` asks a registry; without one, a removal stays unverified."""
    disposition = str(item.get("final_disposition") or "")
    kind = str(item.get("kind") or "")
    identity = str(item.get("exact_identity") or item.get("item_id") or "")
    digests = {d for d in item.get("model_layer_digests") or [] if d}
    if disposition == "INTEGRATED":
        return _verdict("integrated", "n/a", "in service; nothing to restore")
    if disposition == "RETAINED_FOR_PURPOSE":
        return _verdict(
            "retained_for_purpose", "n/a", "kept for a named purpose; nothing to restore"
        )
    source = RESTORE_SOURCES.get(identity)
    if "ollama" not in kind and not source:
        why = f"a {kind} directory: the register records no upstream source to re-obtain it from"
        return _verdict("removed_unrestorable", "unrestorable", why)
    pull, ctx = pull_plan(source or identity)
    how = recipe(identity, pull, ctx)
    if lookup is None:
        return _verdict("removed_unverified", "unverified", how, "not asked (run with --verify)")
    status, layers = lookup(pull)
    where = manifest_url(pull)
    if status.startswith("unreachable"):
        return _verdict("removed_unverified", "unverified", how, f"{where}: {status}")
    if status != "found":
        return _verdict(
            "removed_unrestorable",
            "unrestorable",
            f"no registry serves {pull}",
            f"{where}: {status}",
        )
    state = "unrecorded" if not digests else "verified" if digests <= layers else "differs"
    return _verdict("removed_restorable", state, how, f"{where}: {state}")


def backfill(lookup=None) -> dict:
    register = json.loads(CLOSEOUT.read_text())
    items = register["items"]
    rows = []
    for item in items:
        rows.append(
            {
                "item_id": item["item_id"],
                "exact_identity": item.get("exact_identity"),
                "kind": item.get("kind"),
                "disposition": item.get("final_disposition"),
                **classify(item, lookup),
                "at_risk": AT_RISK.get(item["item_id"]),
                "logical_bytes": item.get("logical_bytes") or item.get("logical_referenced_bytes"),
            }
        )
    return {
        "source": str(CLOSEOUT.relative_to(REPO)),
        "determination_ref": register.get("determination_ref"),
        "determination_date": register.get("determination_date"),
        "verified_utc": dt.datetime.now(dt.UTC).isoformat() if lookup else None,
        "item_count": len(items),
        "classes": dict(sorted(collections.Counter(r["class"] for r in rows).items())),
        "restorability": dict(sorted(collections.Counter(r["restorable"] for r in rows).items())),
        "at_risk_first": [r for r in rows if r["at_risk"]],
        "unrestorable": [r for r in rows if r["restorable"] == "unrestorable"],
        "unverified": [r for r in rows if r["restorable"] == "unverified"],
        "rows": rows,
    }


def queue_entries(rows: list[dict]) -> dict:
    """The removals that cannot be restored, as queue entries with `available: false`."""
    out: dict = {}
    for r in rows:
        if r["restorable"] != "unrestorable":
            continue
        identity = str(r["exact_identity"] or r["item_id"])
        entry = {
            "lineage": identity.split(":")[0],
            "available": False,
            "intended": [],
            "removed_at_closeout": True,
            "note": r["recipe"],
        }
        if r["at_risk"]:
            entry["at_risk"] = r["at_risk"]
        out[identity] = entry
    return out


def merge_queue(entries: dict, path: Path = QUEUE) -> tuple[int, int]:
    """Write the backfill's entries; drop the backfill's earlier ones the registry
    now shows are restorable. Entries the backfill did not write are left alone."""
    doc = yaml.safe_load(path.read_text()) or {}
    models = doc.setdefault("models", {})
    stale = [
        m for m, e in models.items() if (e or {}).get("removed_at_closeout") and m not in entries
    ]
    for m in stale:
        del models[m]
    added = sum(1 for m in entries if m not in models)
    for identity, entry in entries.items():
        models.setdefault(identity, {}).update(entry)
    path.write_text(yaml.safe_dump(doc, sort_keys=True, width=100))
    return added, len(stale)


def render_at_risk(report: dict) -> str:
    """The doc's "Decisions at risk" section, from a verified report."""
    r = report["restorability"]
    lines = [
        "## Decisions at risk",
        "",
        "`scripts/wfe_disposition_backfill.py --verify` classifies every identity in the closeout",
        "register and asks the registry whether each removal can be pulled again, comparing the",
        "registry's layers with the digests the register recorded (receipt",
        f"`{RECEIPT.relative_to(REPO)}`, verified {report['verified_utc']}). Of"
        f" {report['item_count']} items: {report['classes']}.",
        "",
        "**The five removals that rest on a measurement one of the 2026-10-13 audits found",
        "biased.** None is reversed here. A restorable one can be measured again with the recipe",
        "below; an unrestorable one is in the queue with `available: false`, so every cell it",
        "could have had is MISSING and its disposition can only be NO_DECISION.",
        "",
        "| Removal | Why it is at risk | Restorable | Restore |",
        "|---|---|---|---|",
    ]
    for x in report["at_risk_first"]:
        lines.append(
            f"| `{x['item_id']}` | {x['at_risk']} | **{x['restorable']}** | `{x['recipe']}` |"
        )
    lines += [
        "",
        f"Restorable removals: {sum(r.get(k, 0) for k in RESTORABLE)} ({r.get('verified', 0)}"
        f" verified as the measured build, {r.get('differs', 0)} where the registry now serves a"
        f" different build, {r.get('unrecorded', 0)} with no recorded digest). Unrestorable:"
        f" {r.get('unrestorable', 0)}, in `tests/wfe/candidate_queue.yaml` with `available: false`.",
        "",
    ]
    return "\n".join(lines)


def write_doc_section(report: dict, doc: Path = DOC) -> None:
    text = doc.read_text()
    start = text.index("## Decisions at risk\n")
    end = text.index("\n## ", start + 1)
    doc.write_text(text[:start] + render_at_risk(report) + text[end + 1 :])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true", help="ask the registries (network)")
    ap.add_argument("--write", action="store_true", help="write the receipt, queue and doc")
    args = ap.parse_args()
    report = backfill(registry_layers if args.verify else None)
    print(f"classified {report['item_count']} item(s): {report['classes']}")
    print(f"restorability: {report['restorability']}")
    print(f"\nmeasurement-based removals ({len(report['at_risk_first'])}):")
    for r in report["at_risk_first"]:
        print(f"  {r['item_id']}\n      {r['at_risk']}\n      {r['restorable']}: {r['recipe']}")
        print(f"      {r['verification']}")
    if not args.write:
        return 0
    if report["unverified"]:
        print(f"\nrefusing to write: {len(report['unverified'])} removal(s) are unverified")
        for r in report["unverified"][:10]:
            print(f"  {r['item_id']}: {r['verification']}")
        return 1
    RECEIPT.write_text(json.dumps(report, indent=1) + "\n")
    added, dropped = merge_queue(queue_entries(report["rows"]))
    write_doc_section(report)
    print(f"\nwrote {RECEIPT.relative_to(REPO)}; queue +{added} -{dropped}; doc section rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
