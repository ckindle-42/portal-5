"""DATA_TRUTH D1a / Amendment 1 DD1 — did the fact-bearing evidence reach the reader?

Three measurements over one evidence set, per key entry:

* **Offline recall** — the fraction of required-fact evidence sections that a
  retrieval path returns, operator and governing sides separately, at
  recall@5/10/20, over three paths: unscoped search, requirement-scoped
  search, and rendered material (position-free, because a material payload has
  no ranking). This is the data path measured without a reader.
* **In-run delivery** — the same fraction inside a campaign run's tool
  outputs, parsed as JSON first (raw strings carry escaped ``\\n``), so the
  number matches what the model actually saw. This is the task's GATE metric.
* **Use** — the answer quotes delivered text exactly (a contiguous
  normalised run of at least ``USE_MIN_QUOTE_WORDS`` words) and names the
  right document. Reported, never gated (delivery is not use).

Scoring (Amendment 1 DD1, after the G7 probe lessons):

* governing items are scored on the **strict probe** (first 120 normalised
  characters of the key's quote — which opens with the applicability column,
  so it under-counts) *and* on the **normative anchor span** (the
  ``requirement_sections`` ``relation='governing'`` slice for the item's
  ref — the requirement's own normative words). Both are reported; the
  DD6 gate reads the normative-span number.
* operator items are scored on the strict probe *and* on the **longest
  delivered run** — the longest contiguous run of the quote's words found in
  the delivered text — so partial delivery is visible instead of a bare 0.

Every number is a LOWER BOUND (task L1): a key fact cites one valid section
set; other sections may support the same fact.
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
# A contiguous normalised run of at least this many quote words in the answer
# counts as "the answer quotes delivered text exactly" (DD1 (d)). Below this a
# match is a stray phrase, not a quotation.
USE_MIN_QUOTE_WORDS = 8


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def probe_of(text: str) -> str:
    normalized = norm(text)
    return normalized[:PROBE_CHARS] if len(normalized) > PROBE_CHARS else normalized


def load_key(path: Path | None = None) -> dict[str, dict[str, Any]]:
    import yaml

    key = yaml.safe_load((path or KEY_PATH).read_text(encoding="utf-8"))
    return {entry["question_id"]: entry for entry in key["entries"]}


def required_items(entry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(operator evidence items, governing items) among REQUIRED facts.

    The key's evidence blocks may list the same section twice (cited under two
    facts); one section is one evidence item, so repeats are dropped — the
    gate denominators (27 operator / 24 governing on dev) are deduplicated.
    """
    required_ids: list[str] = []
    for fact in entry.get("facts") or []:
        if not fact.get("required", True):
            continue
        for section_id in fact.get("evidence") or []:
            if section_id not in required_ids:
                required_ids.append(section_id)

    def _items(side: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in entry.get(side) or []:
            section_id = item["section_id"]
            if section_id in required_ids and section_id not in seen:
                seen.add(section_id)
                items.append(item)
        return items

    return _items("operator_evidence"), _items("governing")


def evidence_sets(entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(operator evidence ids, governing evidence ids) among REQUIRED facts."""
    operator_items, governing_items = required_items(entry)
    return (
        [item["section_id"] for item in operator_items],
        [item["section_id"] for item in governing_items],
    )


# ── text-in-text scoring ─────────────────────────────────────────────────────


def longest_run_words(quote_norm: str, blob_norm: str) -> int:
    """The longest contiguous run of the quote's words present in the blob.

    Binary search on the run length: if some window of L quote words appears
    in the blob, so does every shorter window, so containment is monotone.
    """
    words = quote_norm.split()
    if not words:
        return 0

    def has_run(length: int) -> bool:
        if length == 0:
            return True
        for start in range(len(words) - length + 1):
            if " ".join(words[start : start + length]) in blob_norm:
                return True
        return False

    low, high = 0, len(words)
    while low < high:
        mid = (low + high + 1) // 2
        if has_run(mid):
            low = mid
        else:
            high = mid - 1
    return low


def normative_anchor_spans(repo: Any, refs: list[str]) -> dict[str, list[str]]:
    """ref -> normalised governing-anchor span texts (every anchor row).

    The span is the ``requirement_sections`` ``relation='governing'`` slice of
    the source document's full text — the requirement's own normative words,
    without the applicability column the key's quote opens with.
    """
    refs = sorted({ref for ref in refs if ref})
    if not refs:
        return {}
    placeholders = ",".join("?" * len(refs))
    rows = repo._conn.execute(
        "SELECT requirement_id, revision_id, char_start, char_end FROM requirement_sections"
        f" WHERE relation='governing' AND requirement_id IN ({placeholders})",
        refs,
    ).fetchall()
    texts: dict[str, str] = {}
    spans: dict[str, list[str]] = {ref: [] for ref in refs}
    for requirement_id, revision_id, char_start, char_end in rows:
        if revision_id not in texts:
            texts[revision_id] = repo.get_document_text(revision_id) or ""
        span = norm(texts[revision_id][char_start:char_end])
        if span and span not in spans[requirement_id]:
            spans[requirement_id].append(span)
    return spans


def use_hit(answer_norm: str, text_norm: str, document: str) -> dict[str, Any]:
    """Did the answer quote this text exactly and name its document? (DD1 d)"""
    quote_words = longest_run_words(text_norm, answer_norm)
    quote_used = text_norm in answer_norm or quote_words >= USE_MIN_QUOTE_WORDS
    document_norm = norm(document)
    document_named = bool(document_norm) and document_norm in answer_norm
    return {
        "quote_words": quote_words,
        "quote_used": quote_used,
        "document_named": document_named,
        "use": quote_used and document_named,
    }


def score_evidence(
    entry: dict[str, Any],
    blob: str,
    anchor_spans: dict[str, list[str]],
    answer_norm: str = "",
) -> dict[str, Any]:
    """Score one entry's required evidence against one delivered-text blob.

    Pure: no store, no index. ``anchor_spans`` comes from
    ``normative_anchor_spans`` (callers cache it across entries).
    """
    operator_items, governing_items = required_items(entry)
    operator_rows: list[dict[str, Any]] = []
    governing_rows: list[dict[str, Any]] = []
    for item in operator_items:
        text_norm = norm(str(item.get("text") or ""))
        strict = bool(text_norm) and probe_of(str(item.get("text") or "")) in blob
        row: dict[str, Any] = {
            "section_id": item["section_id"],
            "delivered": strict,
            "strict": strict,
            "run_words": longest_run_words(text_norm, blob),
            "quote_words": len(text_norm.split()),
        }
        if answer_norm:
            use = use_hit(answer_norm, text_norm, str(item.get("document") or ""))
            use["use"] = use["use"] and row["delivered"]  # use presupposes delivery
            row["use"] = use
        operator_rows.append(row)
    for item in governing_items:
        text = str(item.get("text") or "")
        text_norm = norm(text)
        ref = str(item.get("ref") or "")
        spans = anchor_spans.get(ref) or []
        anchor = any(span and span in blob for span in spans)
        strict = bool(text_norm) and probe_of(text) in blob
        row = {
            "section_id": item["section_id"],
            "ref": ref,
            "delivered": strict or anchor,
            "strict": strict,
            "anchor": anchor,
            "anchor_spans": len(spans),
        }
        if answer_norm:
            standard = ref.split()[0] if ref else ""
            # the answer quotes the delivered text: for an anchor-delivered
            # governing item that is the normative span, not the applicability
            # column the key's own quote opens with
            quote_text = spans[0] if spans else text_norm
            use = use_hit(answer_norm, quote_text, standard)
            use["use"] = use["use"] and row["delivered"]  # use presupposes delivery
            row["use"] = use
        governing_rows.append(row)
    return {"operator": operator_rows, "governing": governing_rows}


def summarize_scored(scored: dict[str, Any]) -> dict[str, Any]:
    """Counting summary over ``score_evidence`` output (one blob)."""
    summary: dict[str, Any] = {}
    operator_rows = scored["operator"]
    governing_rows = scored["governing"]
    summary["operator"] = _count(operator_rows, "delivered")
    summary["operator_run_words"] = {
        "delivered_run_words": sum(row["run_words"] for row in operator_rows),
        "quote_words": sum(row["quote_words"] for row in operator_rows),
    }
    summary["governing_strict"] = _count(governing_rows, "strict")
    summary["governing_anchor"] = _count(governing_rows, "anchor")
    summary["governing_delivered"] = _count(governing_rows, "delivered")
    summary["refs_without_anchor"] = sorted(
        {row["ref"] for row in governing_rows if row["ref"] and row["anchor_spans"] == 0}
    )
    for side, rows in (("operator", operator_rows), ("governing", governing_rows)):
        delivered = [row for row in rows if row["delivered"] and "use" in row]
        summary[f"use_{side}"] = {
            "delivered": len(delivered),
            "quoted": sum(1 for row in delivered if row["use"]["quote_used"]),
            "document_named": sum(1 for row in delivered if row["use"]["document_named"]),
            "use": sum(1 for row in delivered if row["use"]["use"]),
        }
    return summary


def _count(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return {"hits": sum(1 for row in rows if row[field]), "total": len(rows)}


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

    # the DD3 dual-document payload — the delivery path whose in-run numbers
    # DD5 compares against (the legacy material above stays as a diagnostic)
    from portal.modules.compliance.core import dual_document

    payload_blob = ""
    payload_windows: list[dict[str, Any]] = []
    payload_errors: list[str] = []
    for ref in governing_refs:
        built = dual_document.build(repo, requirement_ref=ref)
        if built.get("error"):
            payload_errors.append(f"{ref}: {built['error']}")
            continue
        payload_blob += " " + norm(str(built.get("text") or ""))
        payload_windows.append(built.get("window") or {})
    out["dd3_payload"] = {
        "blob": payload_blob,
        "windows": payload_windows,
        "errors": payload_errors,
    }
    out["anchor_spans"] = normative_anchor_spans(repo, governing_refs)
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


def material_anchor_hits(
    blob: str, entry: dict[str, Any], anchor_spans: dict[str, list[str]]
) -> tuple[int, int]:
    """Governing items whose normative anchor span appears in the blob."""
    _operator_items, governing_items = required_items(entry)
    hits = 0
    for item in governing_items:
        spans = anchor_spans.get(str(item.get("ref") or "")) or []
        if any(span and span in blob for span in spans):
            hits += 1
    return hits, len(governing_items)


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
    anchor_spans = measured.get("anchor_spans") or {}
    hits, total = material_anchor_hits(blob, entry, anchor_spans)
    rows["material.governing_anchor"] = {"hits": hits, "total": total}
    _operator_items, governing_items = required_items(entry)
    operator_runs = [
        longest_run_words(norm(_section_quote(entry, section_id)), blob)
        for section_id in operator_ids
    ]
    rows["material.operator_run_words"] = {
        "delivered_run_words": sum(operator_runs),
        "quote_words": sum(
            len(norm(_section_quote(entry, section_id)).split()) for section_id in operator_ids
        ),
    }
    payload_blob = (measured.get("dd3_payload") or {}).get("blob", "")
    for side, ids in (("operator", operator_ids), ("governing", governing_ids)):
        hits, total = material_hits(payload_blob, entry, ids)
        rows[f"payload.{side}"] = {"hits": hits, "total": total}
    hits, total = material_anchor_hits(payload_blob, entry, anchor_spans)
    rows["payload.governing_anchor"] = {"hits": hits, "total": total}
    rows["payload.operator_run_words"] = {
        "delivered_run_words": sum(
            longest_run_words(norm(_section_quote(entry, section_id)), payload_blob)
            for section_id in operator_ids
        ),
        "quote_words": sum(
            len(norm(_section_quote(entry, section_id)).split()) for section_id in operator_ids
        ),
    }
    rows["material_chars"] = (measured.get("material") or {}).get("chars", 0)
    rows["material_fixed_chars"] = (measured.get("material") or {}).get("fixed_chars", 0)
    errors = (measured.get("material") or {}).get("errors") or []
    errors += measured.get("search_scoped_errors") or []
    errors += (measured.get("dd3_payload") or {}).get("errors") or []
    missing_anchors = sorted(
        {
            str(item.get("ref") or "")
            for item in governing_items
            if item.get("ref") and not (anchor_spans.get(str(item["ref"])) or [])
        }
    )
    if missing_anchors:
        errors += [f"no governing anchor row: {ref}" for ref in missing_anchors]
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
    # product transcripts are named <standard>__<kind> — by filename, not by
    # directory (the harnesses' layouts differ: <rep>/product/transcripts/ in
    # the A3-era runs, <rep>/transcripts/ in the DD5 runs)
    if "__" in stem:
        standard, kind = stem.split("__", 1)
        return f"product:{standard}:{kind}"
    return f"conversational:{stem}"


def transcript_rep(path: Path) -> str:
    """The rep directory a transcript sits in.

    Both run layouts are supported: ``<runs>/rep1/<suite>/transcripts/x.json``
    (ask_conversational / ask_product_questions --out-dir) and the probe
    layout ``<runs>/rep1/transcripts/x.json``.
    """
    for parent in path.parents[1:3]:
        if parent.name.startswith("rep"):
            return parent.name
    return ""


def score_transcript(
    entry: dict[str, Any],
    transcript: dict[str, Any],
    anchor_spans: dict[str, list[str]],
) -> dict[str, Any]:
    """Score one transcript: tool-output delivery plus answer use."""
    blob = tool_output_blob(transcript)
    answer_norm = norm(str(transcript.get("answer") or ""))
    scored = score_evidence(entry, blob, anchor_spans, answer_norm=answer_norm)
    return {
        "summary": summarize_scored(scored),
        "detail": scored,
        "tool_output_chars": len(blob),
        "answer_chars": len(answer_norm),
    }


def run_inrun(
    runs_dir: Path,
    split: str,
    key_path: Path | None = None,
    repo: Any = None,
) -> list[dict[str, Any]]:
    entries = load_key(key_path)
    owns_repo = repo is None
    if owns_repo:
        from portal.modules.compliance.core.repository import Repository

        repo = Repository()
    try:
        anchor_cache: dict[tuple[str, ...], dict[str, list[str]]] = {}
        per_question: dict[str, list[dict[str, Any]]] = {}
        transcripts = sorted(
            {
                *runs_dir.glob("rep*/*/transcripts/*.json"),
                *runs_dir.glob("rep*/transcripts/*.json"),
            }
        )
        for transcript_path in transcripts:
            question_id = transcript_question_id(transcript_path)
            entry = entries.get(question_id)
            if entry is None or entry.get("split") != split:
                continue
            _operator_items, governing_items = required_items(entry)
            refs = sorted({str(item.get("ref") or "") for item in governing_items} - {""})
            cache_key = tuple(refs)
            if cache_key not in anchor_cache:
                anchor_cache[cache_key] = normative_anchor_spans(repo, refs)
            spans = anchor_cache[cache_key]
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            scored = score_transcript(entry, transcript, spans)
            per_question.setdefault(question_id, []).append(
                {
                    "transcript": str(transcript_path),
                    "rep": transcript_rep(transcript_path),
                    **scored["summary"],
                    "detail": scored["detail"],
                }
            )
        out = []
        for question_id, reps in sorted(per_question.items()):
            out.append(
                {
                    "question_id": question_id,
                    "reps": len(reps),
                    **_summarize_reps(reps),
                }
            )
        return out
    finally:
        if owns_repo:
            repo.close()


def _summarize_reps(reps: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals over a question's rep rows, plus the per-rep rows verbatim."""

    def _add_counts(target: dict[str, int], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, int):
                target[key] = target.get(key, 0) + value

    totals: dict[str, Any] = {}
    for field in (
        "operator",
        "operator_run_words",
        "governing_strict",
        "governing_anchor",
        "governing_delivered",
        "use_operator",
        "use_governing",
    ):
        if field == "operator":
            totals[field] = {
                "hits": sum(r["operator"]["hits"] for r in reps),
                "total": sum(r["operator"]["total"] for r in reps),
            }
            continue
        merged: dict[str, int] = {}
        for rep in reps:
            _add_counts(merged, rep[field])
        totals[field] = merged
    totals["refs_without_anchor"] = sorted(
        {ref for rep in reps for ref in rep["refs_without_anchor"]}
    )
    totals["by_rep"] = [
        {
            "rep": rep["rep"],
            "transcript": rep["transcript"],
            "operator": rep["operator"],
            "governing_strict": rep["governing_strict"],
            "governing_anchor": rep["governing_anchor"],
            "governing_delivered": rep["governing_delivered"],
            "use_operator": rep["use_operator"],
            "use_governing": rep["use_governing"],
        }
        for rep in reps
    ]
    return totals


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
    def _side_summary(rows: list[dict[str, Any]], field: str, hits_key: str = "hits") -> dict:
        hits = sum(row[field]["hits"] for row in rows)
        total = sum(row[field]["total"] for row in rows)
        return {
            "hits": hits,
            "total": total,
            "recall": round(hits / total, 4) if total else None,
        }

    summary: dict[str, Any] = {
        "operator": _side_summary(rows, "operator"),
        "operator_run_words": {
            key: sum(row["operator_run_words"][key] for row in rows)
            for key in ("delivered_run_words", "quote_words")
        },
        "governing_strict": _side_summary(rows, "governing_strict"),
        "governing_anchor": _side_summary(rows, "governing_anchor"),
        "governing_delivered": _side_summary(rows, "governing_delivered"),
    }
    for side in ("operator", "governing"):
        summary[f"use_{side}"] = {
            key: sum(row[f"use_{side}"][key] for row in rows)
            for key in ("delivered", "quoted", "document_named", "use")
        }
    # per-rep totals: the DD6 gate is evaluated per rep (>=5 of 6 reps)
    rep_names = sorted(
        {rep["rep"] for row in rows for rep in row["by_rep"]},
        key=lambda name: (len(name), name),
    )
    by_rep: dict[str, Any] = {}
    for rep_name in rep_names:
        rep_rows: list[dict[str, Any]] = []
        for row in rows:
            matching = [rep for rep in row["by_rep"] if rep["rep"] == rep_name]
            rep_rows.extend(matching)
        by_rep[rep_name] = {
            "operator": _side_summary(rep_rows, "operator"),
            "governing_strict": _side_summary(rep_rows, "governing_strict"),
            "governing_anchor": _side_summary(rep_rows, "governing_anchor"),
            "governing_delivered": _side_summary(rep_rows, "governing_delivered"),
            "use_operator": {
                key: sum(rep["use_operator"][key] for rep in rep_rows)
                for key in ("delivered", "quoted", "document_named", "use")
            },
            "use_governing": {
                key: sum(rep["use_governing"][key] for rep in rep_rows)
                for key in ("delivered", "quoted", "document_named", "use")
            },
        }
    summary["by_rep"] = by_rep
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
