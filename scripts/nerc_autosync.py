#!/usr/bin/env python3
"""NERC auto-sync with a linked-impact change report (BILATERAL_CORPUS_V1 P8).

Currency is a trigger, not an operator action. This runs on a timer, fetches
NERC's own One-Stop-Shop workbook, diffs the lifecycle facts against the store,
and for every standard that moved does the whole chain:

    acquire → byte-hash → UNCHANGED or new revision → capture (P1)
    → materialize (P3) → re-project (P4) → rebuild links (P7)
    → re-run the standing questions whose material moved (P6)
    → emit a change report

**The change report is this phase's product.** Per changed requirement: what
changed, the internal sections linked to it, those documents' own
``last_reviewed_date``, and the re-run answers to the standing questions. Nobody
has to ask.

A network failure preserves the last verified snapshot and returns a dated
currency warning. It never deletes, and it never marks stale material current.

    uv run python scripts/nerc_autosync.py --emit-change-report
    uv run python scripts/nerc_autosync.py --family CIP-007 --no-read
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import nerc_source_sync as sync  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

REPORT_ROOT = REPO_ROOT / "reports" / "compliance" / "autosync"
STATE_PATH = REPO_ROOT / "data" / "private" / "nerc_autosync_state.json"

#: every currently effective CIP family, plus the future CIP-007 revision.
#: Discovered from the workbook at run time; this is only the default scope.
DEFAULT_FAMILIES = (
    "CIP-002",
    "CIP-003",
    "CIP-004",
    "CIP-005",
    "CIP-006",
    "CIP-007",
    "CIP-008",
    "CIP-009",
    "CIP-010",
    "CIP-011",
    "CIP-012",
    "CIP-013",
    "CIP-014",
    "CIP-015",
)

#: lifecycle fields whose movement means the standard changed for our purposes.
WATCHED_FIELDS = (
    "status",
    "effective",
    "inactive",
    "implementation_plan_url",
    "technical_rationale_url",
)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return dict(json.loads(STATE_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return {}
    return {}


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_PATH)


def stored_lifecycle(repo: Repository) -> dict[str, dict[str, str]]:
    """What the STORE currently believes about each standard's lifecycle."""
    rows = repo._conn.execute(
        """SELECT d.logical_id, r.effective_date, r.inactive_date, r.lifecycle_status,
                  r.revision_id
           FROM source_documents d JOIN document_revisions r ON r.logical_id = d.logical_id
           WHERE d.source_kind = 'regulatory_standard' AND d.jurisdiction = 'US'"""
    ).fetchall()
    return {
        str(row[0]).split("/", 1)[-1]: {
            "effective": str(row[1] or ""),
            "inactive": str(row[2] or ""),
            "status": str(row[3] or ""),
            "revision_id": str(row[4] or ""),
        }
        for row in rows
    }


def diff_lifecycle(
    workbook: dict[str, Any], store: dict[str, dict[str, str]], families: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Standards whose watched lifecycle facts moved, or that the store lacks."""
    moved: list[dict[str, Any]] = []
    for standard, facts in sorted(workbook.items()):
        if not any(standard.startswith(f + "-") for f in families):
            continue
        known = store.get(standard)
        entry = {k: str(getattr(facts, k, "") or "") for k in WATCHED_FIELDS}
        if known is None:
            moved.append({"standard": standard, "change": "not in the store", "now": entry})
            continue
        deltas = {
            field: {"was": known.get(field, ""), "now": entry[field]}
            for field in ("status", "effective", "inactive")
            if known.get(field, "") != entry[field]
        }
        if deltas:
            moved.append({"standard": standard, "change": "lifecycle moved", "deltas": deltas})
    return moved


def _linked_impact(repo: Repository, standard: str) -> list[dict[str, Any]]:
    """Per requirement of one standard: its linked internal sections, and those
    documents' own last review dates — the half of a change report that says
    what the operator has to go and look at."""
    from portal.modules.compliance.core.section_index import resolve_sections

    rows = repo._conn.execute(
        """SELECT src_ref, dst_ref, status, derivation, confidence
           FROM relationship_assertions
           WHERE src_ref LIKE ? AND status IN ('approved','proposed')
           ORDER BY src_ref, confidence DESC""",
        (f"{standard}%",),
    ).fetchall()
    resolved = resolve_sections(repo, [str(r[1]) for r in rows])
    out: dict[str, dict[str, Any]] = {}
    for src, dst, status, derivation, confidence in rows:
        entry = resolved.get(str(dst))
        if entry is None:
            continue
        bucket = out.setdefault(str(src), {"requirement": str(src), "linked": []})
        bucket["linked"].append(
            {
                "section_id": str(dst),
                "document": entry.get("document_title") or entry.get("logical_id"),
                "heading": entry.get("headings"),
                "link_status": status,
                "derivation": derivation,
                "confidence": confidence,
                "document_last_reviewed": entry.get("last_reviewed_date"),
            }
        )
    return list(out.values())


def _semantic_delta(repo: Repository, standard: str) -> dict[str, Any]:
    from portal.modules.compliance.core.revision_compare import semantic_diff

    family = "-".join(standard.split("-")[:2])
    versions = sorted(
        {
            str(r[0]).rsplit("-", 1)[-1]
            for r in repo._conn.execute(
                """SELECT logical_id FROM source_documents
                   WHERE source_kind = 'regulatory_standard' AND logical_id LIKE ?""",
                (f"NERC/{family}-%",),
            ).fetchall()
        }
    )
    if len(versions) < 2:
        return {"detail": f"{family} has one revision in the store — no delta to compute"}
    try:
        return semantic_diff(
            repo, family=family, version_before=versions[0], version_after=versions[-1]
        )
    except Exception as exc:  # noqa: BLE001 - a delta is context, never the gate
        return {"error": str(exc)}


def run(
    *,
    families: tuple[str, ...] = DEFAULT_FAMILIES,
    read_answers: bool = True,
    reproject: bool = True,
    model: str = "",
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "ran_at": _now(),
        "families": list(families),
        "warnings": [],
        "changed": [],
        "acquired": {},
        "projection": {},
        "links": {},
        "standing_answers": [],
    }
    state = read_state()

    # 1. the registry, and the diff against what the store believes
    registry = sync._acquire(
        "one-stop-shop.xlsx", sync.ONE_STOP_SHOP_URL, role="registry", directory=sync.OFFICIAL_DIR
    )
    if registry.status == "FAILED":
        report["warnings"].append(
            f"{_now()}: lifecycle registry unavailable ({registry.warning}); "
            "the last verified snapshot is retained and must not be treated as current"
        )
        report["currency"] = "STALE — registry unreachable, nothing changed"
        write_state({**state, "last_attempt": report["ran_at"], "last_error": registry.warning})
        return report
    if registry.warning:
        report["warnings"].append(
            f"{_now()}: registry not refreshed ({registry.warning}); lifecycle facts come "
            "from the last verified snapshot and must not be treated as current"
        )

    workbook = sync.parse_lifecycle(
        Path(registry.path).read_bytes(), registry_sha256=registry.sha256
    )
    repo = Repository()
    try:
        report["changed"] = diff_lifecycle(workbook, stored_lifecycle(repo), families)
        if not report["changed"]:
            report["currency"] = "CURRENT — the registry agrees with the store"
            write_state(
                {**state, "last_success": report["ran_at"], "registry_sha256": registry.sha256}
            )
            return report

        # 2. acquire every moved standard's bundle
        for entry in report["changed"]:
            standard = str(entry["standard"])
            family, version = standard.rsplit("-", 1)
            bundle = sync.sync_official_bundle(family=family, versions=(version,))
            report["acquired"][standard] = {
                a.name: {"status": a.status, "sha256": a.sha256[:16], "role": a.role}
                for a in bundle.artifacts
            }
            report["warnings"].extend(bundle.warnings)
    finally:
        repo.close()

    # 3. materialize (capture lands here), re-project, rebuild links
    from scripts.materialize_regulatory_corpus import materialize

    report["materialization"] = _summarise_materialization(materialize(backup=True))

    if reproject:
        from scripts.project_compliance_sections import project

        report["projection"] = project(["US", "internal"])

    repo = Repository()
    try:
        from portal.modules.compliance.core import candidate_links, section_index

        plan = section_index.build_plan(repo, jurisdiction="internal")
        receipt = section_index.boundary_receipt(repo, plan)
        for entry in report["changed"]:
            standard = str(entry["standard"])
            links = candidate_links.build_links(repo, standard)
            report["links"][standard] = candidate_links.record_links(
                repo, links, boundary_receipt=receipt
            )
            entry["semantic_delta"] = _semantic_delta(repo, standard)
            entry["linked_impact"] = _linked_impact(repo, standard)

        # 4. re-run the standing questions whose material moved
        if read_answers:
            from portal.modules.compliance.core.reader import run_standing_questions

            seat = model or _reading_seat()
            for entry in report["changed"]:
                for row in entry.get("linked_impact", []):
                    report["standing_answers"].extend(
                        run_standing_questions(
                            repo,
                            str(row["requirement"]),
                            model=seat,
                            thread_id=f"autosync:{report['ran_at']}",
                        )
                    )
    finally:
        repo.close()

    report["currency"] = "REFRESHED"
    write_state(
        {
            **state,
            "last_success": report["ran_at"],
            "registry_sha256": registry.sha256,
            "changed": [c["standard"] for c in report["changed"]],
        }
    )
    return report


def _reading_seat() -> str:
    import os

    from portal.modules.compliance.core.runtime_config import _read_council_config

    configured = _read_council_config().get("reading_seat")
    if isinstance(configured, dict) and configured.get("model"):
        return str(configured["model"])
    return os.environ.get("COMPLIANCE_READING_MODEL", "granite4.1:30b-ctx64k")


def _summarise_materialization(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "hash_verified": len(report.get("hash_verified", [])),
        "documents": [
            {
                "logical_id": d["logical_id"],
                "effective_date": d.get("effective_date"),
                "inactive_date": d.get("inactive_date"),
                "sections": (d.get("capture") or {}).get("sections")
                if isinstance(d.get("capture"), dict)
                else d.get("sections"),
            }
            for d in report.get("documents", [])
        ],
        "identity_repairs": report.get("identity_repairs", []),
        "jurisdictions": report.get("census", {}).get("jurisdictions", []),
    }


def render(report: dict[str, Any]) -> str:
    """The change report, for a human who did not ask for it."""
    lines = [
        f"# NERC auto-sync — {report['ran_at']}",
        "",
        f"currency: **{report.get('currency', 'unknown')}**",
    ]
    for warning in report.get("warnings", []):
        lines.append(f"- WARNING: {warning}")
    if not report.get("changed"):
        lines.append("\nNothing moved. The registry and the store agree.")
        return "\n".join(lines) + "\n"
    for entry in report["changed"]:
        lines.append(f"\n## {entry['standard']} — {entry['change']}")
        for field, delta in (entry.get("deltas") or {}).items():
            lines.append(f"- `{field}`: `{delta['was'] or '—'}` → `{delta['now'] or '—'}`")
        delta = entry.get("semantic_delta") or {}
        if delta.get("changed"):
            lines.append(f"- semantic delta: {len(delta['changed'])} duties changed")
        for row in entry.get("linked_impact", []):
            lines.append(f"\n### {row['requirement']}")
            for link in row["linked"]:
                lines.append(
                    f"- `{link['section_id']}` {link['document']} — {link['heading']} "
                    f"({link['link_status']}/{link['derivation']}, "
                    f"last reviewed {link['document_last_reviewed'] or 'unrecorded'})"
                )
    if report.get("standing_answers"):
        lines.append("\n## standing questions, re-run")
        for answer in report["standing_answers"]:
            lines.append(f"\n### {answer.get('question')} — {answer.get('ref')}")
            lines.append(str(answer.get("answer", ""))[:1500])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", action="append", default=None)
    parser.add_argument("--emit-change-report", action="store_true")
    parser.add_argument("--no-read", action="store_true", help="skip the standing-question re-run")
    parser.add_argument("--no-reproject", action="store_true")
    parser.add_argument("--model", default="")
    args = parser.parse_args(argv)

    report = run(
        families=tuple(args.family) if args.family else DEFAULT_FAMILIES,
        read_answers=not args.no_read,
        reproject=not args.no_reproject,
        model=args.model,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / f"{stamp}.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    markdown = render(report)
    (REPORT_ROOT / f"{stamp}.md").write_text(markdown, encoding="utf-8")
    if args.emit_change_report:
        print(markdown)
    else:
        print(f"{report.get('currency')} — {len(report.get('changed', []))} standard(s) moved")
        print(f"report: {REPORT_ROOT / f'{stamp}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
