"""A5 pull-based reading: the conversation's material is a requirement brief.

The brief carries the standard's own text for the requirement and an INDEX of
the sections in scope — no operator section text. The packet-era forcing
("complete", "do not search", "answer only from this material") leaves the
tool output, and the window guard prices against the serving engine's own
window, not a stale seat tag (the Q1b M8 finding).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import reading_material
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.conversation_window import fit_material
from portal.modules.compliance.core.models import RelationshipAssertion, SourceDocument
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.temporal import now_iso

PART_ROWS = [
    ("B. Requirements and Measures", "2.1 | High Impact | Identify a source for patches. | M."),
    ("B. Requirements and Measures", "2.2 | High Impact | Evaluate every 35 calendar days. | M."),
]
OPERATOR_ROWS = [
    ("3 Patching", "The OT team evaluates patches once every 30 calendar days."),
]

#: the packet-era text A5 removes — none of it may serve again
FORBIDDEN = (
    "complete material",
    "Nothing here needs a search",
    "Answer only from this material",
    "Do not search",
    "nothing is missing from it",
)


def _capture(path: Path, rows: list[tuple[str, str]]) -> CapturedDocument:
    units, buf, cursor = [], [], 0
    for ordinal, (heading, body) in enumerate(rows):
        piece = body + "\n"
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind="table_row" if " | " in body else "prose",
                heading_path=heading,
                title=heading,
                page_start=1,
                page_end=1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path,
        page_count=1,
        full_text="".join(buf),
        units=units,
        reader_strings=tuple(body for _h, body in rows),
    )


def _document(repo: Repository, logical_id: str, jurisdiction: str, kind: str, rows: list) -> str:
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=logical_id,
            issuer="x",
            source_kind=kind,
            jurisdiction=jurisdiction,
        )
    )
    revision = repo.add_document_revision(logical_id, f"/docs/{logical_id}", logical_id.encode())
    store_capture(repo, revision.revision_id, _capture(Path(f"/docs/{logical_id}"), rows))
    return revision.revision_id


def _sections(repo: Repository, revision_id: str) -> list[str]:
    return [
        str(row[0])
        for row in repo._conn.execute(
            "SELECT section_id FROM source_sections WHERE revision_id = ? ORDER BY ordinal",
            (revision_id,),
        )
    ]


@pytest.fixture
def store(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "store.db")
    regulatory = _document(repo, "NERC/CIP-007-6", "US", "regulatory_standard", PART_ROWS)
    operator = _document(repo, "ACME/patching", "internal", "procedure", OPERATOR_ROWS)
    with repo._lock, repo._conn:
        repo._conn.execute(
            "INSERT OR IGNORE INTO standard_revisions(revision_id, logical_id, family, version,"
            " org_id) VALUES ('CIP-007-6','CIP-007','CIP-007','6','default')"
        )
        for part in ("2.1", "2.2"):
            repo._conn.execute(
                "INSERT OR IGNORE INTO requirement_nodes(node_id, standard_revision_id,"
                " requirement, part, logical_lineage_id, org_id) VALUES (?,?,?,?,'','default')",
                (f"CIP-007-6 R2 Part {part}", "CIP-007-6", "R2", part),
            )
    from portal.modules.compliance.core import requirement_anchor as ra

    rows = _sections(repo, regulatory)
    for index, part in enumerate(("2.1", "2.2")):
        repo.record_anchors(
            [
                ra.Anchor(
                    requirement_id=f"CIP-007-6 R2 Part {part}",
                    revision_id=regulatory,
                    relation="governing",
                    anchored=True,
                    char_start=0,
                    char_end=1,
                    section_ids=[rows[index]],
                    occurrences=1,
                )
            ]
        )
    operator_sections = _sections(repo, operator)
    repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="rel-2.2",
            relation_type="IMPLEMENTS",
            src_ref="CIP-007-6 R2 Part 2.2",
            src_revision_id=None,
            dst_ref=f"ACME/patching::{operator_sections[0]}",
            dst_revision_id=None,
            scope="",
            citations=[],
            status="proposed",
            review_state="proposed",
            valid_from=now_iso()[:10],
        )
    )
    return repo


def test_brief_carries_the_standard_and_an_index_not_operator_text(store: Repository):
    payload = reading_material.render_brief(store, "CIP-007-6 R2 Part 2.2")
    assert "error" not in payload
    text = payload["text"]
    # the standard's own text for the requirement travels in full
    assert "Evaluate every 35 calendar days" in text
    # the operator section's text does NOT travel — its index row does
    operator_id = _sections(store, _revision_of(store, "ACME/patching"))[0]
    assert "once every 30 calendar days" not in text
    assert operator_id in text
    assert "ACME/patching" in text
    assert "proposed edge" in text
    assert payload["by_side"].get("operator") == 1


def _revision_of(repo: Repository, logical_id: str) -> str:
    row = repo._conn.execute(
        "SELECT revision_id FROM document_revisions WHERE logical_id = ?"
        " ORDER BY rowid DESC LIMIT 1",
        (logical_id,),
    ).fetchone()
    return str(row[0])


def test_brief_never_carries_the_packet_forcing(store: Repository):
    text = reading_material.render_brief(store, "CIP-007-6 R2 Part 2.2")["text"]
    for phrase in FORBIDDEN:
        assert phrase not in text


def test_a_non_address_is_refused(store: Repository):
    assert "error" in reading_material.render_brief(store, "not a ref at all")


@pytest.mark.parametrize(
    ("served", "seat", "text_bytes", "fits"),
    [
        (262_144, "gemma4:26b-a4b-it-q4_K_M-ctx32k", 120_000, True),
        (0, "gemma4:26b-a4b-it-q4_K_M-ctx32k", 120_000, False),
        (0, "gemma4:26b-a4b-it-q4_K_M", 10_000, False),
    ],
    ids=["engine-window-fits", "tag-fallback-refuses", "no-window-refuses-blind"],
)
def test_the_guard_prices_against_the_engine_window_then_the_tag(
    monkeypatch, served, seat, text_bytes, fits
):
    from portal.modules.compliance.core.conversation_window import seat_window

    monkeypatch.setattr(
        "portal.modules.compliance.core.conversation_window.served_window",
        lambda _seat: (served, "test engine" if served else ""),
    )
    fitted = fit_material({"text": "x" * text_bytes}, seat)
    assert fitted["fits"] is fits
    assert fitted["served_window"] == (served or None)
    assert fitted["seat_tag_window"] == (seat_window(seat) or None)
    if not served and not seat_window(seat):
        assert "refusing to price blind" in fitted["why"]
