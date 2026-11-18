from __future__ import annotations

from dataclasses import replace
from typing import Any

import duckdb

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.behaviours import (
    MisfitShape,
    collect_behaviours,
    create_events,
    line_shape,
    load_misfits,
)
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.misfit import (
    MISFIT_GENERATOR,
    generate_misfit,
    source_coverage,
)
from portal.modules.security.core.hunt.notables.receipt import write_json
from portal.modules.security.core.hunt.notables.run import (
    DEFAULT_GENERATORS,
    GENERATORS,
    notables_stage,
)
from portal.modules.security.core.hunt.notables.sample import SourceFacts


def _card(
    roles: dict[str, tuple[str, ...]] | None = None,
    fmt: str = "json",
    coverage: float = 0.95,
    sourcetype: str = "st",
    **kwargs: Any,
) -> SourceCard:
    return SourceCard(
        index="ix",
        sourcetype=sourcetype,
        kind="activity",
        roles=roles or {"actor": ("user",), "action": ("image",)},
        understood=True,
        reason=None,
        fmt=fmt,
        coverage=coverage,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="key",
        **kwargs,
    )


def _facts() -> SourceFacts:
    # a real range containing the row times, so each sub-window reads its own rows once
    return SourceFacts("ix", "st", 5, 0.0, 100.0, ("h1",), 1, ("/s1",), 1)


class _RowsExecutor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def read(
        self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
    ) -> Read:
        del query, kind, row_cap
        rows = [dict(row) for row in self.rows if start <= float(row["_time"]) < end]
        return Read(rows, False, None)


def test_line_shape_normalises_values_and_keeps_punctuation() -> None:
    assert line_shape("pid 1234 started") == "aaa 9999 aaaaaaa"
    assert line_shape("bash: 196: Bad file descriptor") == line_shape(
        "bash: 207: Bad file descriptor"
    )
    assert line_shape("bash: 196: Bad file descriptor") != line_shape("bash: 196: Bad gateway")
    assert line_shape("  ") == ""


def test_out_of_structure_lines_are_counted_sampled_and_stored(tmp_path) -> None:
    card = _card()
    rows = [
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 1.0, "host": "h1"},
        {"_raw": '{"user": "amy", "image": "cmd.exe"}', "_time": 2.0, "host": "h1"},
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 3.0, "host": "h2"},
        {"_raw": "bash: 196: Bad file descriptor", "_time": 4.0, "host": "h1"},
        {"_raw": "   ", "_time": 5.0, "host": "h1"},
    ]
    store = tmp_path / "b.duckdb"
    _behaviours, receipt = collect_behaviours(
        _RowsExecutor(rows),  # type: ignore[arg-type]
        [card],
        {"ix:st": _facts()},
        store,
    )
    entry = receipt["receipts"][0]
    assert entry["events_out_of_structure"] == 2
    assert entry["unparsed_share"] == round(2 / 5, 6)
    assert receipt["misfit_lines"] == 1
    assert receipt["misfit_sources"] == 1
    misfits, stats, notes = load_misfits(store)
    assert notes == []
    assert stats["ix:st"]["lines_read"] == 5
    assert stats["ix:st"]["misfit_lines"] == 1
    assert stats["ix:st"]["shapes_kept"] == 1
    assert len(misfits) == 1
    shape = misfits[0]
    assert shape.source_id == "ix:st"
    assert shape.events == 1
    assert shape.hosts == 1
    assert shape.examples[0]["raw"] == "bash: 196: Bad file descriptor"
    assert shape.examples[0]["host"] == "h1"


def test_a_line_claimed_by_any_card_of_its_source_is_not_a_misfit(tmp_path) -> None:
    activity = replace(
        _card({"actor": ("src",), "action": ("proto",)}),
        part_field="event_type",
        part_value="flow",
    )
    alert = replace(
        activity,
        kind="alert",
        roles={"actor": ("src",), "action": ("sig",)},
        part_value="alert",
    )
    rows = [
        {"_raw": '{"event_type":"flow","src":"a","proto":"TCP"}', "_time": 1.0, "host": "h1"},
        {"_raw": '{"event_type":"alert","src":"a","sig":"scan"}', "_time": 2.0, "host": "h1"},
        {"_raw": "plain junk", "_time": 3.0, "host": "h1"},
    ]
    _behaviours, receipt = collect_behaviours(
        _RowsExecutor(rows),  # type: ignore[arg-type]
        [activity, alert],
        {"ix:st": _facts()},
        tmp_path / "mixed.duckdb",
    )
    assert receipt["misfit_lines"] == 1
    misfits, _stats, _notes = load_misfits(tmp_path / "mixed.duckdb")
    assert [shape.examples[0]["raw"] for shape in misfits] == ["plain junk"]


def test_load_misfits_declares_a_store_without_the_table(tmp_path) -> None:
    path = tmp_path / "old.duckdb"
    con = duckdb.connect(str(path))
    try:
        create_events(con)
    finally:
        con.close()
    misfits, stats, notes = load_misfits(path)
    assert misfits == []
    assert stats == {}
    assert notes == ["no_misfit_table"]


def _shape(shape: str, events: int, raw: str = "bash: 196: Bad file descriptor") -> MisfitShape:
    return MisfitShape(
        "ix:st",
        shape,
        events,
        1,
        10.0,
        20.0,
        ({"time": 10.0, "host": "h1", "raw": raw, "earliest": 0.0, "latest": 3600.0},),
    )


def test_generate_misfit_ranks_the_rarest_shape_first() -> None:
    cards = [_card()]
    facts = {"ix:st": _facts()}
    stats = {"ix:st": {"lines_read": 10_000, "misfit_lines": 6}}
    misfits = [_shape("aaa 9", 5, raw="aaa 9 raw"), _shape("a: 999:", 1)]
    notables, receipt = generate_misfit(cards, facts, misfits, stats)
    assert [item.measure_value for item in notables] == [0.0001, 0.0005]
    top = notables[0]
    assert top.generator == MISFIT_GENERATOR
    assert top.basis == "out_of_structure"
    assert top.entities == (("shape", "a: 999:"),)
    assert top.counts["events"] == 1
    assert top.counts["lines_read"] == 10_000
    query = str(top.evidence[0]["query"])
    assert 'index="ix"' in query
    assert '"descriptor"' in query
    assert receipt["existed"] == 2
    assert receipt["kept"] == 2


def test_generate_misfit_only_ranks_sources_that_are_well_understood() -> None:
    facts = {"ix:st": _facts()}
    stats = {"ix:st": {"lines_read": 10_000, "misfit_lines": 1}}
    misfits = [_shape("a", 1)]
    notables, receipt = generate_misfit([_card(coverage=0.5)], facts, misfits, stats)
    assert notables == []
    assert receipt["skipped"]["low_coverage"] == 1
    assert source_coverage([_card(coverage=0.5), _card(coverage=0.95)]) == {"ix:st": 0.95}


def test_generate_misfit_skips_sources_whose_misfit_share_is_not_rare() -> None:
    facts = {"ix:st": _facts()}
    stats = {"ix:st": {"lines_read": 10_000, "misfit_lines": 200}}
    notables, receipt = generate_misfit([_card()], facts, [_shape("a", 200)], stats)
    assert notables == []
    assert receipt["skipped"]["poorly_understood_source"] == 1
    _no_stats, receipt2 = generate_misfit([_card()], {}, [_shape("a", 1)], {})
    assert receipt2["skipped"]["no_read_stats"] == 1


def test_generate_misfit_interleaves_sources_so_one_cannot_monopolise() -> None:
    cards = [_card(), _card(sourcetype="big")]
    facts = {"ix:st": _facts(), "ix:big": _facts()}
    stats = {
        "ix:st": {"lines_read": 10_000, "misfit_lines": 2},
        "ix:big": {"lines_read": 100_000, "misfit_lines": 2},
    }
    misfits = [
        MisfitShape("ix:st", "a", 1, 1, 10.0, 20.0, ()),
        MisfitShape("ix:st", "b", 1, 1, 10.0, 20.0, ()),
        MisfitShape("ix:big", "c", 1, 1, 10.0, 20.0, ()),
        MisfitShape("ix:big", "d", 1, 1, 10.0, 20.0, ()),
    ]
    notables, receipt = generate_misfit(cards, facts, misfits, stats)
    assert [item.source_id for item in notables] == ["ix:big", "ix:st", "ix:big", "ix:st"]
    assert receipt["sources_ranked"] == 2


def test_misfit_is_a_default_generator_and_runs_in_the_notables_stage(tmp_path) -> None:
    assert MISFIT_GENERATOR in GENERATORS
    assert MISFIT_GENERATOR in DEFAULT_GENERATORS
    card = _card()
    rows: list[dict[str, object]] = [
        {"_raw": '{"user": "bob", "image": "cmd.exe"}', "_time": 1.0, "host": "h1"}
    ] * 200
    rows.append({"_raw": "bash: 196: Bad file descriptor", "_time": 2.0, "host": "h1"})
    _behaviours, _receipt = collect_behaviours(
        _RowsExecutor(rows),  # type: ignore[arg-type]
        [card],
        {"ix:st": SourceFacts("ix", "st", 201, 0.0, 100.0, ("h1",), 1, ("/s1",), 1)},
        tmp_path / "behaviours.duckdb",
    )
    write_json(tmp_path / "sources.json", {"cards": [card.as_dict()]})
    found, receipt = notables_stage(
        index="ix",
        out=tmp_path,
        start=0.0,
        end=7200.0,
        search=_RowsExecutor([]),  # type: ignore[arg-type]
        enabled=[MISFIT_GENERATOR],
    )
    assert [row["generator"] for row in found] == [MISFIT_GENERATOR]
    assert receipt[MISFIT_GENERATOR]["kept"] == 1
    stored = (tmp_path / "notables.jsonl").read_text()
    assert "out_of_structure" in stored


def test_a_store_without_misfits_degrades_to_a_declared_note(tmp_path) -> None:
    card = _card()
    store = tmp_path / "behaviours.duckdb"
    con = duckdb.connect(str(store))
    try:
        create_events(con)
        con.execute("CREATE TABLE behaviours AS SELECT * FROM events LIMIT 0")
        con.execute(
            "CREATE TABLE source_stats AS SELECT 'ix:st' AS source_id,"
            " 0 AS hosts_possible, 0 AS actors_possible"
        )
    finally:
        con.close()
    write_json(tmp_path / "sources.json", {"cards": [card.as_dict()]})
    found, receipt = notables_stage(
        index="ix",
        out=tmp_path,
        start=0.0,
        end=7200.0,
        search=_RowsExecutor([]),  # type: ignore[arg-type]
        enabled=[MISFIT_GENERATOR],
    )
    assert found == []
    assert receipt[MISFIT_GENERATOR]["notes"] == ["no_misfit_table"]
