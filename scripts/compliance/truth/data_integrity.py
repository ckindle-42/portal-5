"""DATA_TRUTH D1b — the committed integrity check over the compliance data path.

TASK_COMPLIANCE_DATA_TRUTH_V1 L11: the canonical store is the source of truth
and every derived view (the Lance index, the default revision scope, the
declared windows, the relationship edges) is regenerable and verifiable. This
module computes that verification in one report; the registered
``validate_system`` check (``scripts/validation/compliance_data_truth.py``)
wraps it, and the CLI prints the same report standalone:

    uv run python scripts/compliance/truth/data_integrity.py [--json]

Failure classes are predeclared by the task, not chosen here: an unindexed
section without a recorded exclusion reason, an index id that does not
resolve, a future or inactive revision inside the default scope, a declared
window that differs from the served one, and a TOC/furniture section carrying
an IMPLEMENTS edge. The unit-shape census is reported, not gated: fragments
and furniture are the D2/D3 re-cut's input, not a defect in themselves.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The exclusion table: which section classes are deliberately not indexed,
#: and why. Committed data (no operator text), edited by D4's decision —
#: never assumed. A class with ``"decision": "pending"`` does not clear a
#: section; the check stays red until every class is decided with a reason.
EXCLUSION_TABLE_PATH = (
    REPO_ROOT / "portal" / "modules" / "compliance" / "data" / "index_exclusions.json"
)

LANCE_RAG_DIR = Path(
    __import__("os").environ.get("PORTAL5_LANCE_RAG_DIR", "/Volumes/data01/portal5_lance/rag")
)
TEXT_TABLES = ("compliance_nerc_corpus", "compliance_operator_corpus", "compliance_operator_notes")

FURNITURE_RE = re.compile(r"PRIVATE\s+[–-]\s+FOR INTERNAL USE ONLY|^Page \d+ of \d+\b", re.M)
TOC_TITLE_RE = re.compile(r"table of contents", re.I)
TOC_PATH_RE = re.compile(r"(^|/)toc\.|^contents$")
FRAGMENT_CHARS = 120


@dataclass
class CheckResult:
    name: str
    status: str  # pass | fail | warn
    detail: str
    findings: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "findings": self.findings,
        }


def _store_path() -> Path:
    return REPO_ROOT / "portal" / "modules" / "compliance" / "data" / "compliance_store.db"


def _connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path or _store_path()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _lance_rows() -> dict[str, list[dict[str, Any]]]:
    import lancedb

    db = lancedb.connect(str(LANCE_RAG_DIR))
    out: dict[str, list[dict[str, Any]]] = {}
    for name in TEXT_TABLES:
        try:
            out[name] = (
                db.open_table(name)
                .to_arrow()
                .select(
                    [
                        "chunk_id",
                        "text",
                        "headings",
                        "logical_id",
                        "revision_id",
                        "effective_from",
                        "effective_to",
                        "is_superseded",
                        "unit_kind",
                    ]
                )
                .to_pylist()
            )
        except Exception as exc:  # noqa: BLE001 - an absent corpus is a finding
            out[name] = []
            out[f"__error__{name}"] = [{"error": str(exc)}]  # type: ignore[assignment]
    return out


def _full_texts(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(r["revision_id"]): str(r["full_text"] or "")
        for r in conn.execute("select revision_id, full_text from document_texts")
    }


def section_text(conn: sqlite3.Connection, full: dict[str, str], section_id: str) -> str:
    row = conn.execute(
        "select revision_id, char_start, char_end from source_sections where section_id=?",
        (section_id,),
    ).fetchone()
    if row is None:
        return ""
    text = full.get(str(row["revision_id"]), "")
    start, end = int(row["char_start"] or 0), int(row["char_end"] or 0)
    if start < 0 or end <= start or end > len(text):
        return ""
    return text[start:end]


# ── check 1: every index id resolves ─────────────────────────────────────────


def check_index_resolution(
    conn: sqlite3.Connection, rows: dict[str, list[dict[str, Any]]]
) -> CheckResult:
    canonical = {str(r[0]) for r in conn.execute("select section_id from source_sections")}
    missing: dict[str, int] = {}
    for name, table_rows in rows.items():
        if name.startswith("__error__"):
            continue
        for row in table_rows:
            parent = str(row["chunk_id"]).split("#")[0]
            if parent not in canonical:
                missing[name] = missing.get(name, 0) + 1
    if missing:
        return CheckResult(
            "index_id_resolution",
            "fail",
            f"index chunk ids that do not resolve to a canonical section: {missing}",
            [{"unresolved_by_table": missing}],
        )
    return CheckResult("index_id_resolution", "pass", "every index chunk parent resolves", [])


# ── check 2: store↔index coverage with recorded exclusions ───────────────────


def _load_exclusion_table() -> list[dict[str, Any]]:
    if not EXCLUSION_TABLE_PATH.is_file():
        return []
    return json.loads(EXCLUSION_TABLE_PATH.read_text(encoding="utf-8")).get("classes", [])


def _class_matches(
    entry_class: dict[str, Any], jurisdiction: str, logical_id: str, unit_kind: str
) -> bool:
    applies = entry_class.get("applies") or {}
    if applies.get("jurisdiction") and applies["jurisdiction"] != jurisdiction:
        return False
    pattern = applies.get("logical_id_regex")
    if pattern and not re.search(pattern, logical_id):
        return False
    kinds = applies.get("unit_kind")
    return not (kinds and unit_kind not in kinds)


def _classify_unindexed(
    row: sqlite3.Row, classes: list[dict[str, Any]]
) -> tuple[str, str | None, str | None]:
    """(outcome, class_id) for one unindexed section.

    outcome is ``explained`` (a decided exclusion class owns it, or the section
    matches the built-in heading-only fragment rule), ``pending`` (an undecided
    class matches — still unexplained until D4 decides), ``deferred`` (an
    'indexed' class owns it: the projection brings it in, D4 owns the reason —
    neutral), or ``unexplained``.
    """
    # the built-in fragment rule (plan _plan_gate): the section's whole span is
    # its own title line, under the fragment floor. Verified from metadata —
    # the span hugs the title's length — because slicing store text here would
    # double the check's cost.
    title = str(row["title"] or "").strip()
    span = row["span"]
    if title and span is not None and 0 < int(span) < 120 and abs(int(span) - len(title)) <= 2:
        return "explained", "regulatory_heading_only_fragments", None
    matched_decided = None
    matched_pending = None
    matched_indexed = None
    for entry_class in classes:
        if _class_matches(
            entry_class,
            str(row["jurisdiction"]),
            str(row["logical_id"]),
            str(row["unit_kind"] or ""),
        ):
            decision = entry_class.get("decision")
            if decision == "excluded":
                matched_decided = entry_class
            elif decision == "indexed":
                matched_indexed = entry_class
            else:
                matched_pending = entry_class
    if matched_decided is not None:
        return "explained", str(matched_decided["id"]), None
    if matched_pending is not None:
        return "pending", str(matched_pending["id"]), None
    if matched_indexed is not None:
        return "deferred", str(matched_indexed["id"]), None
    return "unexplained", None, None


def check_coverage(conn: sqlite3.Connection, rows: dict[str, list[dict[str, Any]]]) -> CheckResult:
    indexed: set[str] = set()
    for name, table_rows in rows.items():
        if name.startswith("__error__"):
            continue
        for row in table_rows:
            indexed.add(str(row["chunk_id"]).split("#")[0])
    store_rows = conn.execute(
        """select s.section_id, s.unit_kind, s.title,
                  s.char_end - s.char_start as span,
                  d.jurisdiction, r.logical_id
           from source_sections s
           join document_revisions r on r.revision_id = s.revision_id
           join source_documents d on d.logical_id = r.logical_id"""
    ).fetchall()
    unindexed = [r for r in store_rows if str(r["section_id"]) not in indexed]
    classes = _load_exclusion_table()
    by_class: dict[str, int] = {}
    unexplained: list[sqlite3.Row] = []
    pending: dict[str, int] = {}
    for row in unindexed:
        outcome, class_id, _ = _classify_unindexed(row, classes)
        if outcome == "explained":
            by_class[class_id] = by_class.get(class_id, 0) + 1
        elif outcome == "pending":
            pending[class_id] = pending.get(class_id, 0) + 1
            unexplained.append(row)
        elif outcome == "unexplained":
            unexplained.append(row)
    findings = [
        {
            "unindexed_total": len(unindexed),
            "explained_by_class": by_class,
            "pending_classes": pending,
            "unexplained_by_jurisdiction": _count_by(unexplained, "jurisdiction"),
            "unexplained_examples": [
                {
                    "section_id": str(r["section_id"]),
                    "logical_id": str(r["logical_id"]),
                    "unit_kind": str(r["unit_kind"] or ""),
                }
                for r in unexplained[:5]
            ],
        }
    ]
    if unexplained:
        return CheckResult(
            "store_index_coverage",
            "fail",
            f"{len(unexplained)} unindexed section(s) without a decided exclusion class "
            f"({sum(pending.values())} in pending classes) — record the class and its reason "
            f"in {EXCLUSION_TABLE_PATH.name}",
            findings,
        )
    return CheckResult(
        "store_index_coverage",
        "pass",
        f"every one of {len(unindexed)} unindexed section(s) is covered by a decided exclusion class",
        findings,
    )


def _count_by(rows: list[sqlite3.Row], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row[key])
        out[value] = out.get(value, 0) + 1
    return out


# ── check 3: unit-shape census (report-only) ─────────────────────────────────


def check_unit_shapes(rows: dict[str, list[dict[str, Any]]]) -> CheckResult:
    census: dict[str, dict[str, int]] = {}
    for name, table_rows in rows.items():
        if name.startswith("__error__"):
            continue
        counts = {"chunks": 0, "fragment": 0, "furniture": 0, "toc": 0, "heading_only_empty": 0}
        examples: dict[str, str] = {}
        for row in table_rows:
            text = str(row["text"] or "")
            counts["chunks"] += 1
            if len(text) < FRAGMENT_CHARS:
                counts["fragment"] += 1
                examples.setdefault("fragment", text[:80])
            if FURNITURE_RE.search(text):
                counts["furniture"] += 1
                examples.setdefault("furniture", text[:80])
            if TOC_TITLE_RE.search(str(row["headings"] or "")):
                counts["toc"] += 1
                examples.setdefault("toc", text[:80])
            if not str(row["unit_kind"] or ""):
                counts["heading_only_empty"] += 1
        findings_entry = {**counts, "examples": examples}
        census[name] = findings_entry  # type: ignore[assignment]
    return CheckResult(
        "unit_shape_census",
        "pass",
        "census over indexed chunks (report-only; fragments and furniture are the re-cut's input)",
        [{"by_table": census}],
    )


# ── check 4: default-scope revision currency ─────────────────────────────────


def check_revision_currency(rows: dict[str, list[dict[str, Any]]], today: str) -> CheckResult:
    future: list[dict[str, Any]] = []
    inactive: list[dict[str, Any]] = []
    for name, table_rows in rows.items():
        if name.startswith("__error__"):
            continue
        seen: set[str] = set()
        for row in table_rows:
            chunk_key = str(row["chunk_id"])
            if chunk_key in seen:
                continue
            seen.add(chunk_key)
            if int(row["is_superseded"] or 0) != 0:
                continue
            effective = str(row["effective_from"] or "")
            effective_to = str(row["effective_to"] or "")
            if effective and effective > today:
                future.append(
                    {
                        "table": name,
                        "logical_id": str(row["logical_id"]),
                        "effective_from": effective,
                    }
                )
            if effective_to and effective_to <= today:
                inactive.append(
                    {
                        "table": name,
                        "logical_id": str(row["logical_id"]),
                        "effective_to": effective_to,
                    }
                )
    findings = [
        {
            "future_in_default_scope": future[:10],
            "future_count": len(future),
            "inactive_in_default_scope": inactive[:10],
            "inactive_count": len(inactive),
        }
    ]
    if future or inactive:
        return CheckResult(
            "revision_currency",
            "fail",
            f"default scope (is_superseded = 0) carries {len(future)} future-effective and "
            f"{len(inactive)} inactive chunk(s) — 'latest effective' must mean effective on the asked date",
            findings,
        )
    return CheckResult(
        "revision_currency", "pass", "default scope holds no future or inactive revision", findings
    )


# ── check 5: declared window = served window ─────────────────────────────────


def check_windows() -> CheckResult:
    import yaml

    portal_path = REPO_ROOT / "config" / "portal.yaml"
    raw = yaml.safe_load(portal_path.read_text(encoding="utf-8")) or {}
    workspaces = raw.get("workspaces") or {}
    backends_path = REPO_ROOT / "config" / "backends.yaml"
    backends_raw = yaml.safe_load(backends_path.read_text(encoding="utf-8")) or {}
    routing = backends_raw.get("workspace_routing") or {}

    from portal.modules.compliance.core.served_window import served_window_for_hint, tag_window

    findings: list[dict[str, Any]] = []
    failures: list[str] = []
    unknowns: list[str] = []
    for name, ws in sorted(workspaces.items()):
        if not isinstance(ws, dict):
            continue
        hint = str(ws.get("model_hint") or "")
        declared = ws.get("context_limit")
        if not hint or declared is None:
            continue
        declared_n = int(declared)
        tag_w = tag_window(hint)
        served = served_window_for_hint(hint, groups=routing.get(name))
        entry = {
            "workspace": name,
            "hint": hint,
            "declared": declared_n,
            "tag_window": tag_w,
            "served": served.applied_window,
            "resolved_model": served.resolved_model,
            "aliased": served.aliased,
        }
        findings.append(entry)
        # The tag window is recorded, never gated: a workspace may legitimately
        # declare less than its seat bakes, and tag names colloquially round
        # (``ctx98k`` bakes 98304). The task's failure class is declared ≠ served,
        # against EVERY route the workspace's groups can reach.
        for backend_id, window in served.route_windows:
            if window != declared_n:
                failures.append(
                    f"{name}: declared {declared_n} != served {window} ({backend_id}:{served.resolved_model})"
                )
        if served.applied_window is None:
            unknowns.append(name)
    if failures:
        return CheckResult(
            "window_declared_served",
            "fail",
            "; ".join(failures[:6]) + (" …" if len(failures) > 6 else ""),
            findings,
        )
    if unknowns:
        return CheckResult(
            "window_declared_served",
            "warn",
            f"served window unknown for {len(unknowns)} workspace(s) (backend unreachable) — "
            "static comparisons pass",
            findings,
        )
    return CheckResult(
        "window_declared_served",
        "pass",
        "declared window equals served window everywhere probed",
        findings,
    )


# ── check 6: edge census + TOC/furniture endpoints ───────────────────────────


def check_edges(conn: sqlite3.Connection, full: dict[str, str]) -> CheckResult:
    edges = conn.execute(
        "select assertion_id, relation_type, src_ref, dst_ref, derivation, review_state from relationship_assertions"
    ).fetchall()
    by_relation: dict[str, int] = {}
    by_derivation: dict[str, int] = {}
    by_state: dict[str, int] = {}
    bad_endpoints: list[dict[str, Any]] = []
    for edge in edges:
        by_relation[str(edge["relation_type"])] = by_relation.get(str(edge["relation_type"]), 0) + 1
        by_derivation[str(edge["derivation"] or "")] = (
            by_derivation.get(str(edge["derivation"] or ""), 0) + 1
        )
        by_state[str(edge["review_state"])] = by_state.get(str(edge["review_state"]), 0) + 1
        for side in ("src_ref", "dst_ref"):
            ref = str(edge[side])
            why = _ineligible_reason(conn, full, ref)
            if why:
                bad_endpoints.append(
                    {
                        "assertion_id": str(edge["assertion_id"]),
                        "side": side,
                        "ref": ref,
                        "relation": str(edge["relation_type"]),
                        "derivation": str(edge["derivation"] or ""),
                        "why": why,
                    }
                )
    findings = [
        {
            "by_relation": by_relation,
            "by_derivation": by_derivation,
            "by_review_state": by_state,
            "ineligible_endpoints": bad_endpoints[:10],
            "ineligible_count": len(bad_endpoints),
        }
    ]
    if bad_endpoints:
        return CheckResult(
            "edge_census",
            "fail",
            f"{len(bad_endpoints)} edge endpoint(s) resolve to TOC/furniture/fragment sections — "
            "never eligible as evidence or edge endpoints",
            findings,
        )
    return CheckResult(
        "edge_census",
        "pass",
        f"census over {len(edges)} edges; no TOC/furniture endpoints",
        findings,
    )


def _ineligible_reason(conn: sqlite3.Connection, full: dict[str, str], ref: str) -> str:
    base = ref.split("::")[0]
    if not re.match(r"^(isection|csection|section)-", base):
        return ""
    row = conn.execute(
        "select path, title, char_start, char_end, revision_id from source_sections where section_id=?",
        (base,),
    ).fetchone()
    if row is None:
        return ""
    text = ""
    rev = str(row["revision_id"])
    if rev in full:
        start, end = int(row["char_start"] or 0), int(row["char_end"] or 0)
        if 0 <= start < end <= len(full[rev]):
            text = full[rev][start:end]
    if TOC_PATH_RE.search(str(row["path"] or "")) or TOC_TITLE_RE.search(str(row["title"] or "")):
        return "toc"
    if FURNITURE_RE.search(text):
        return "furniture"
    if text and len(text) < FRAGMENT_CHARS and not text.strip():
        return "blank_fragment"
    return ""


# ── the report ───────────────────────────────────────────────────────────────


def data_integrity_report(*, probe_windows: bool = True) -> dict[str, Any]:
    """Every check, in task order. Never raises; an environmental failure is a finding."""
    from portal.modules.compliance.core.temporal import now_iso

    today = now_iso()[:10]
    results: list[CheckResult] = []
    try:
        conn = _connect()
    except Exception as exc:  # noqa: BLE001
        return {
            "date": today,
            "status": "fail",
            "results": [
                {"name": "store_open", "status": "fail", "detail": str(exc), "findings": []}
            ],
        }
    try:
        rows = _lance_rows()
        full = _full_texts(conn)
        results.append(check_index_resolution(conn, rows))
        results.append(check_coverage(conn, rows))
        results.append(check_unit_shapes(rows))
        results.append(check_revision_currency(rows, today))
        results.append(check_edges(conn, full))
    finally:
        conn.close()
    try:
        results.append(check_windows())
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult("window_declared_served", "fail", f"window check crashed: {exc}", [])
        )
    status = (
        "fail"
        if any(r.status == "fail" for r in results)
        else ("warn" if any(r.status == "warn" for r in results) else "pass")
    )
    return {
        "date": today,
        "status": status,
        "results": [r.as_dict() for r in results],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    report = data_integrity_report()
    if args.json:
        print(json.dumps(report, indent=1))
        return 0 if report["status"] == "pass" else 1
    print(f"DATA_TRUTH integrity: {report['status'].upper()} ({report['date']})")
    for result in report["results"]:
        marker = {"pass": "✓", "warn": "!", "fail": "✗"}[result["status"]]
        print(f"  {marker} {result['name']}: {result['status']} — {result['detail']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
