#!/usr/bin/env python3
"""P6R dev campaign: pin a build and SQLite snapshot before each rep.

This driver never changes product settings. It restores the pinned canonical
store, saves any changed post-rep store locally, and counts external-index
versions and rows. External-index restoration is not implemented: a change
halts the campaign before another rep can read it. This limitation is explicit,
not a claim that SQLite restoration isolates a vector index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from scripts.compliance.truth import _local, store_snapshot  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]


def index_state() -> dict:
    """Full compliance table catalog, versions and counts; no index mutation."""
    from portal.platform.retrieval.store import RAG_DIR, get_db, table_names

    if not pathlib.Path(RAG_DIR).is_dir():
        return {"error": "retrieval index directory unavailable"}
    try:
        db = get_db()
        state = {
            name: {"version": db.open_table(name).version, "rows": db.open_table(name).count_rows()}
            for name in table_names(db)
            if name.startswith("compliance_")
        }
        state["sidecars"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in pathlib.Path(RAG_DIR).glob("compliance_*.meta.json")
        }
        return state
    except Exception as exc:  # noqa: BLE001 - an unrestorable store is named
        return {"error": str(exc)}


def prepare_rep(snapshot_path: pathlib.Path, db: pathlib.Path, expected: str) -> dict:
    """Refuse a moved campaign snapshot and prove restoration before inference."""
    if store_snapshot.digest(snapshot_path)["sha256"] != expected:
        raise RuntimeError("the pinned campaign snapshot changed")
    result = store_snapshot.restore(snapshot_path, db)
    if not result["restored"] or result["got"] != expected:
        raise RuntimeError("canonical store restoration failed its logical digest")
    return result


def _receipt_problems(out: pathlib.Path, suites: list[str]) -> list[str]:
    """Missing receipts and stale served configuration invalidate a rep."""
    problems = []
    for suite in suites:
        receipt_name = (
            "product_questions_family.json" if suite == "product" else "conversational_proof.json"
        )
        receipt_path = out / suite / receipt_name
        if not receipt_path.is_file():
            problems.append(f"{suite}: receipt missing")
            continue
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("provenance", {}).get("served_config", {}).get("matches_host") is not True:
            problems.append(f"{suite}: served configuration does not match host")
    return problems


def run_rep(out: pathlib.Path, key: pathlib.Path, build: str) -> dict:
    """Dev-only harness invocations; validate the final served model per turn."""
    reference = yaml.safe_load(key.read_text())
    if reference.get("status") not in ("AGENT_FINAL", "OPERATOR_REVIEWED"):
        raise RuntimeError("the campaign needs a final answer key")
    entries = reference["entries"]
    dev = [e["question_id"] for e in entries if e.get("split") == "dev"]
    product = [q.removeprefix("product:") for q in dev if q.startswith("product:")]
    conversational = [
        q.removeprefix("conversational:") for q in dev if q.startswith("conversational:")
    ]
    if len(product) + len(conversational) != len(dev):
        raise RuntimeError("dev split contains questions without a campaign harness")
    env = {**os.environ, "COMPLIANCE_MEASUREMENT_MODEL": build}
    commands = []
    if product:
        commands.append(
            (
                "product",
                [
                    "scripts/compliance/ask_product_questions.py",
                    "--standards",
                    ",".join(sorted({q.split(":")[0] for q in product})),
                    "--only",
                    ",".join(product),
                ],
            )
        )
    if conversational:
        commands.append(
            (
                "conversational",
                ["scripts/compliance/ask_conversational.py", "--only", ",".join(conversational)],
            )
        )
    problems = []
    for suite, args in commands:
        with (out / f"{suite}.log").open("w") as log:
            code = subprocess.run(
                ["uv", "run", "python", *args, "--out-dir", str(out / suite)],
                cwd=REPO,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
        # Exit 1 is a non-PASS receipt verdict, which the judge scores; only a crash invalidates.
        if code not in (0, 1):
            problems.append(f"{suite}: harness exit {code}")
    problems.extend(_receipt_problems(out, [suite for suite, _args in commands]))
    turns = [json.loads(p.read_text()) for p in out.glob("*/transcripts/*.json")]
    if len(turns) != len(dev):
        problems.append(f"transcript count {len(turns)} differs from dev count {len(dev)}")
    for n, turn in enumerate(turns):
        serving = turn.get("serving") or {}
        if turn.get("build_matches_declaration") is not True:
            problems.append(f"turn {n}: final served build differs from declaration")
        if serving.get("window_pressure") is None or serving.get("cascade") is None:
            problems.append(f"turn {n}: serving facts incomplete")
        if turn.get("tool_outputs_status") == "unavailable":
            problems.append(f"turn {n}: tool output capture unavailable")
    return {
        "valid": not problems,
        "problems": problems,
        "n_turns": len(turns),
        "window_pressure": [t.get("serving", {}).get("window_pressure") for t in turns],
        "window_exceeded": sum(t.get("serving", {}).get("window_exceeded") is True for t in turns),
    }


def _pin_indexes(snapshot: pathlib.Path, db: pathlib.Path, expected: str, indexes: dict) -> None:
    """One external-index pin shared by every arm using this SQLite snapshot."""
    index_pin = snapshot.with_suffix(snapshot.suffix + ".indexes.json")
    if index_pin.exists():
        pinned = json.loads(index_pin.read_text())
        if pinned["logical_sha256"] != expected or pinned["external_indexes"] != indexes:
            raise SystemExit("pinned campaign snapshot or external index state changed")
    else:
        if store_snapshot.digest(db)["sha256"] != expected:
            raise SystemExit(
                "pin external indexes while the live canonical store equals its snapshot"
            )
        index_pin.write_text(
            json.dumps({"logical_sha256": expected, "external_indexes": indexes}, indent=2)
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", type=pathlib.Path, required=True)
    ap.add_argument("--db", type=pathlib.Path, required=True)
    ap.add_argument(
        "--build", required=True, help="exact registered served-model id, not an aliased hint"
    )
    ap.add_argument("--out-dir", type=pathlib.Path, required=True)
    ap.add_argument(
        "--key", type=pathlib.Path, default=_local.PRIVATE / "reading_truth/answer_key.yaml"
    )
    ap.add_argument("--reps", type=int, default=3)
    args = ap.parse_args(argv)
    for path in (args.snapshot, args.out_dir):
        if refused := _local.refusal(path, "campaign state"):
            raise SystemExit(refused)
    if args.out_dir.exists() or args.reps < 1:
        raise SystemExit("use a fresh local run directory and a positive rep count")
    from portal.modules.compliance.core.repository import DEFAULT_DB_PATH

    if args.db.resolve() != DEFAULT_DB_PATH.resolve():
        raise SystemExit(
            "--db must be the configured canonical store, not a separate harness-only database"
        )
    expected = str(store_snapshot.digest(args.snapshot)["sha256"])
    indexes = index_state()
    if "error" in indexes:
        raise SystemExit(f"cannot measure external index writes: {indexes['error']}")
    _pin_indexes(args.snapshot, args.db, expected, indexes)
    args.out_dir.mkdir(parents=True)
    manifest = {
        "canonical_db": str(args.db),
        "declared_build": args.build,
        "snapshot": str(args.snapshot),
        "logical_sha256": expected,
        "external_indexes": indexes,
        "external_restore": "not implemented; halt on changed version/count",
    }
    (args.out_dir / "campaign.json").write_text(json.dumps(manifest, indent=2))
    # This is also the before-arm restoration; each rep repeats and proves it.
    for rep in range(1, args.reps + 1):
        out = args.out_dir / f"rep{rep}"
        out.mkdir()
        if index_state() != indexes:
            raise RuntimeError("external index drift: restore its pinned state before resuming")
        restored = prepare_rep(args.snapshot, args.db, expected)
        result = run_rep(out, args.key, args.build)
        after = store_snapshot.digest(args.db)
        if after["sha256"] != expected:
            store_snapshot.snapshot(args.db, out / "post_rep_store.sqlite")
        after_indexes = index_state()
        result.update(
            {
                "restore": restored,
                "store_after": after,
                "external_indexes_before": indexes,
                "external_indexes_after": after_indexes,
                "external_indexes_changed": after_indexes != indexes,
            }
        )
        (out / "isolation.json").write_text(json.dumps(result, indent=2))
        if not result["valid"] or result["external_indexes_changed"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
