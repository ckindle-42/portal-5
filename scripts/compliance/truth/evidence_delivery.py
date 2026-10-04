"""DATA_TRUTH D1a — did the fact-bearing evidence reach the reader?

Two measurements over one evidence set, per key entry:

* **Offline recall** — the fraction of required-fact evidence sections that a
  retrieval path returns, operator and governing sides separately, at
  recall@5/10/20, over three paths: unscoped search, requirement-scoped
  search, and rendered material (position-free, because a material payload has
  no ranking). This is the data path measured without a reader.
* **In-run delivery** — the same fraction inside a campaign run's tool
  outputs, parsed as JSON first (raw strings carry escaped ``\\n``), so the
  number matches what the model actually saw.

Every number is a LOWER BOUND (task L1): a key fact cites one valid section
set; other sections may support the same fact. The probe is the first 120
normalised characters of the key's own quote, the same probe
``p6/review/material_reach.py`` used, so numbers stay comparable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
KEY_PATH = (
    REPO_ROOT
    / "portal"
    / "modules"
    / "compliance"
    / "data"
    / "private"
    / "reading_truth"
    / "answer_key.yaml"
)
K_VALUES = (5, 10, 20)
PROBE_CHARS = 120


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def probe_of(text: str) -> str:
    normalized = norm(text)
    return normalized[:PROBE_CHARS] if len(normalized) > PROBE_CHARS else normalized


def load_key(path: Path | None = None) -> dict[str, dict[str, Any]]:
    import yaml

    key = yaml.safe_load((path or KEY_PATH).read_text(encoding="utf-8"))
    return {entry["question_id"]: entry for entry in key["entries"]}


def evidence_sets(entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(operator evidence ids, governing evidence ids) among REQUIRED facts."""
    required_ids: list[str] = []
    for fact in entry.get("facts") or []:
        if not fact.get("required", True):
            continue
        for section_id in fact.get("evidence") or []:
            if section_id not in required_ids:
                required_ids.append(section_id)
    operator_ids = []
    for item in entry.get("operator_evidence") or []:
        section_id = item["section_id"]
        if section_id in required_ids and section_id not in operator_ids:
            operator_ids.append(section_id)
    governing_ids = []
    for item in entry.get("governing") or []:
        section_id = item["section_id"]
        if section_id in required_ids and section_id not in governing_ids:
            governing_ids.append(section_id)
    return operator_ids, governing_ids


# ── retrieval paths ──────────────────────────────────────────────────────────


def _search_ranks(results: list[dict[str, Any]]) -> dict[str, int]:
    """section_id -> best rank (1-based) across a search result list.

    ``search_service.search`` rows are resolved store sections and carry
    ``section_id``; raw pipeline rows (used by findability) carry only
    ``chunk_id``, whose parent is the id before the ``#`` sub-unit suffix.
    """
    from portal.modules.compliance.core.section_index import parent_section_id

    ranks: dict[str, int] = {}
    for position, row in enumerate(results, start=1):
        section_id = str(row.get("section_id") or "").strip()
        if not section_id:
            section_id = parent_section_id(str(row.get("chunk_id", "")))
        if section_id and section_id not in ranks:
            ranks[section_id] = position
    return ranks


def offline_entry(repo: Any, entry: dict[str, Any]) -> dict[str, Any]:
    """One entry's recall over the three paths. Runs the live retrieval stack."""
    from portal.modules.compliance.core import reading_material, search_service

    question = str(entry["question"])
    operator_ids, governing_ids = evidence_sets(entry)
    governing_refs = sorted({str(g["ref"]) for g in entry.get("governing") or []})

    out: dict[str, Any] = {
        "operator_ids": operator_ids,
        "governing_ids": governing_ids,
        "governing_refs": governing_refs,
    }

    unscoped = search_service.search(repo, question, top_k=max(K_VALUES))
    out["search_unscoped"] = _search_ranks(list(unscoped.get("results") or []))

    scoped_ranks: dict[str, int] = {}
    scoped_errors: list[str] = []
    for ref in governing_refs:
        try:
            body = search_service.search(repo, question, requirement=ref, top_k=max(K_VALUES))
        except Exception as exc:  # noqa: BLE001 - a refused scope is a finding
            scoped_errors.append(f"{ref}: {exc}")
            continue
        for section_id, rank in _search_ranks(list(body.get("results") or [])).items():
            if section_id not in scoped_ranks or rank < scoped_ranks[section_id]:
                scoped_ranks[section_id] = rank
    out["search_scoped"] = scoped_ranks
    out["search_scoped_errors"] = scoped_errors

    material_chars = 0
    material_fixed = 0
    material_blob = ""
    material_errors: list[str] = []
    for ref in governing_refs:
        try:
            payload = reading_material.render(repo, ref, citation="quote")
        except Exception as exc:  # noqa: BLE001
            material_errors.append(f"{ref}: {exc}")
            continue
        payload.pop("contract", None)
        if payload.get("error"):
            material_errors.append(f"{ref}: {payload['error']}")
            continue
        material_chars += int(payload.get("chars") or 0)
        material_fixed += int(payload.get("fixed_chars") or 0)
        material_blob += " " + norm(str(payload.get("text") or ""))
    out["material"] = {
        "blob": material_blob,
        "chars": material_chars,
        "fixed_chars": material_fixed,
        "errors": material_errors,
    }
    return out


def recall_at(ranks: dict[str, int], ids: list[str], k: int) -> tuple[int, int]:
    hits = sum(1 for section_id in ids if ranks.get(section_id, 10**9) <= k)
    return hits, len(ids)


def material_hits(blob: str, entry: dict[str, Any], ids: list[str]) -> tuple[int, int]:
    if not ids:
        return 0, 0
    hits = 0
    for section_id in ids:
        text = _section_quote(entry, section_id)
        if text and probe_of(text) in blob:
            hits += 1
    return hits, len(ids)


def _section_quote(entry: dict[str, Any], section_id: str) -> str:
    for side in ("operator_evidence", "governing"):
        for item in entry.get(side) or []:
            if item["section_id"] == section_id:
                return str(item.get("text") or "")
    return ""


def score_offline(entry: dict[str, Any], measured: dict[str, Any]) -> dict[str, Any]:
    operator_ids, governing_ids = evidence_sets(entry)
    rows: dict[str, Any] = {}
    for path in ("search_unscoped", "search_scoped"):
        ranks = measured.get(path) or {}
        for side, ids in (("operator", operator_ids), ("governing", governing_ids)):
            for k in K_VALUES:
                hits, total = recall_at(ranks, ids, k)
                rows[f"{path}.{side}@{k}"] = {"hits": hits, "total": total}
    blob = (measured.get("material") or {}).get("blob", "")
    for side, ids in (("operator", operator_ids), ("governing", governing_ids)):
        hits, total = material_hits(blob, entry, ids)
        rows[f"material.{side}"] = {"hits": hits, "total": total}
    rows["material_chars"] = (measured.get("material") or {}).get("chars", 0)
    rows["material_fixed_chars"] = (measured.get("material") or {}).get("fixed_chars", 0)
    errors = (measured.get("material") or {}).get("errors") or []
    errors += measured.get("search_scoped_errors") or []
    if errors:
        rows["errors"] = errors
    return rows


def run_offline(split: str, key_path: Path | None = None) -> list[dict[str, Any]]:
    from portal.modules.compliance.core.repository import Repository

    entries = load_key(key_path)
    repo = Repository()
    try:
        out = []
        for question_id, entry in sorted(entries.items()):
            if entry.get("split") != split:
                continue
            measured = offline_entry(repo, entry)
            out.append({"question_id": question_id, **score_offline(entry, measured)})
        return out
    finally:
        repo.close()


# ── in-run delivery ──────────────────────────────────────────────────────────


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def tool_output_blob(transcript: dict[str, Any]) -> str:
    """Everything the model saw from tools, JSON-parsed then flattened."""
    parts: list[str] = []
    for output in transcript.get("tool_outputs") or []:
        raw = output.get("output", "")
        try:
            parts.extend(_strings(json.loads(raw)))
        except Exception:  # noqa: BLE001 - raw strings carry escaped newlines
            parts.append(raw)
    return " ".join(norm(part) for part in parts)


def transcript_question_id(path: Path) -> str:
    stem = path.stem
    if "/product/" in str(path) or "\\product\\" in str(path):
        standard, kind = stem.split("__")
        return f"product:{standard}:{kind}"
    return f"conversational:{stem}"


def run_inrun(runs_dir: Path, split: str, key_path: Path | None = None) -> list[dict[str, Any]]:
    entries = load_key(key_path)
    per_question: dict[str, list[dict[str, Any]]] = {}
    for transcript_path in sorted(runs_dir.glob("rep*/*/transcripts/*.json")):
        question_id = transcript_question_id(transcript_path)
        entry = entries.get(question_id)
        if entry is None or entry.get("split") != split:
            continue
        blob = tool_output_blob(json.loads(transcript_path.read_text(encoding="utf-8")))
        operator_ids, governing_ids = evidence_sets(entry)
        operator_hits = sum(1 for s in operator_ids if probe_of(_section_quote(entry, s)) in blob)
        governing_hits = sum(1 for s in governing_ids if probe_of(_section_quote(entry, s)) in blob)
        per_question.setdefault(question_id, []).append(
            {
                "transcript": str(transcript_path),
                "operator_hits": operator_hits,
                "operator_total": len(operator_ids),
                "governing_hits": governing_hits,
                "governing_total": len(governing_ids),
            }
        )
    out = []
    for question_id, reps in sorted(per_question.items()):
        out.append(
            {
                "question_id": question_id,
                "reps": len(reps),
                "operator_hits": sum(r["operator_hits"] for r in reps),
                "operator_total": sum(r["operator_total"] for r in reps),
                "governing_hits": sum(r["governing_hits"] for r in reps),
                "governing_total": sum(r["governing_total"] for r in reps),
            }
        )
    return out


# ── aggregation and CLI ──────────────────────────────────────────────────────


def aggregate_offline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [k for k in rows[0] if isinstance(rows[0][k], dict) and "hits" in rows[0][k]]
    summary = {}
    for metric in metrics:
        hits = sum(row[metric]["hits"] for row in rows)
        total = sum(row[metric]["total"] for row in rows)
        summary[metric] = {
            "hits": hits,
            "total": total,
            "recall": round(hits / total, 4) if total else None,
        }
    return summary


def aggregate_inrun(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {}
    for side in ("operator", "governing"):
        hits = sum(row[f"{side}_hits"] for row in rows)
        total = sum(row[f"{side}_total"] for row in rows)
        summary[side] = {
            "hits": hits,
            "total": total,
            "recall": round(hits / total, 4) if total else None,
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    offline = sub.add_parser("offline", help="recall@5/10/20 over the retrieval paths")
    offline.add_argument("--split", choices=("dev", "holdout"), default="dev")
    offline.add_argument("--key", type=Path, default=None)
    offline.add_argument("--out", type=Path, default=None)
    offline.add_argument(
        "--quiet", action="store_true", help="write the file, print nothing (sealing)"
    )
    inrun = sub.add_parser("inrun", help="delivery inside a run's tool outputs")
    inrun.add_argument("--runs", type=Path, required=True)
    inrun.add_argument("--split", choices=("dev", "holdout"), default="dev")
    inrun.add_argument("--key", type=Path, default=None)
    inrun.add_argument("--out", type=Path, default=None)
    inrun.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.command == "offline":
        rows = run_offline(args.split, args.key)
        result = {
            "measurement": "offline",
            "split": args.split,
            "entries": rows,
            "summary": aggregate_offline(rows),
        }
    else:
        rows = run_inrun(args.runs, args.split, args.key)
        result = {
            "measurement": "inrun",
            "split": args.split,
            "runs": str(args.runs),
            "entries": rows,
            "summary": aggregate_inrun(rows),
        }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    if not args.quiet:
        print(json.dumps(result["summary"], indent=1))
        per_entry = [
            {
                "question_id": row["question_id"],
                **{k: v for k, v in row.items() if isinstance(v, dict) and v.get("total")},
            }
            for row in rows
        ]
        print(json.dumps(per_entry, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
