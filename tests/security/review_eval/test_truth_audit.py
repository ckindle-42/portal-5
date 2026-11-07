"""scripts/review_truth_audit.py flags answer-key entries that cannot be found where they claim."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from portal.modules.security.core.bully.corpus_bed import AnswerKeyEntry

REPO = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "review_truth_audit", REPO / "scripts" / "review_truth_audit.py"
)
assert _SPEC is not None and _SPEC.loader is not None
audit_mod: Any = importlib.util.module_from_spec(_SPEC)
sys.modules["review_truth_audit"] = audit_mod
_SPEC.loader.exec_module(audit_mod)

# Presence tables, from the live shapes the task quotes: tstats TERM("bstoll") by sourcetype
# reports wineventlog:security=23812, and TERM("kutekitten") lives only in osquery, never in the
# declared stream:smtp. Multi-token entities whose full term the index does not hold (BGIST-L)
# resolve through their ANDed alphanumeric tokens.
FULL_PRESENCE: dict[str, tuple[str, int]] = {
    "10.0.0.5": ("stream:http", 100),
    "web.example": ("stream:http", 50),
    "host-a": ("winhostmon", 7),
    "user-a": ("winhostmon", 7),
    "bstoll": ("wineventlog:security", 23812),
    "kutekitten": ("osquery:results", 6087),
}
TOKEN_PRESENCE: dict[str, tuple[str, int]] = {"bgist": ("wineventlog:security", 3105)}
ENTITY_DAYS: dict[str, list[tuple[int, str]]] = {
    "10.0.0.5": [(d * 86400, "10") for d in range(3)],
    "web.example": [(86400, "1")],
    "bgist": [(d * 86400, "5") for d in range(3)],
}
# sourcetype-in-search -> (returned source, count)
SOURCE_COUNTS: dict[str, tuple[str, int]] = {
    "stream:http": ("stream:http", 50),
    "xmlwineventlog:sysmon": ("portal5:corpus:cousin:x", 4),
    "stream:smtp": ("stream:smtp", 670760),
    "wineventlog:security": ("wineventlog:security", 46469),
}


class _Fake:
    """Answers the probe's tstats query shapes from the tables above."""

    def __init__(self, joint: str = "1") -> None:
        self.days = 3
        self.joint = joint

    def iter_post(self, search: str, start: float, end: float) -> Iterator[Mapping[str, Any]]:
        lowered = search.lower()
        if "NOT source=" in search:  # joint: tstats AND of every entity's resolved form
            yield {"count": self.joint}
        elif "TERM(" in search and "by _time span=1d" in search:  # per-entity day buckets
            yield from self._entity_day_rows(lowered)
        elif "TERM(" in search:  # presence resolution: full term, then ANDed tokens
            table = TOKEN_PRESENCE if search.count("TERM(") > 1 else FULL_PRESENCE
            yield from self._matching(table, lowered)
        elif "by _time span=1d" in search:  # sensor days for a declared sourcetype
            yield from ({"_time": str(d * 86400), "count": "10"} for d in range(self.days))
        elif "by source" in search:
            yield from self._matching(SOURCE_COUNTS, lowered)

    def _entity_day_rows(self, lowered: str) -> Iterator[Mapping[str, Any]]:
        for entity, rows in ENTITY_DAYS.items():
            if f'term("{entity}")' in lowered:
                yield from ({"_time": str(day), "count": count} for day, count in rows)

    def _matching(
        self, table: dict[str, tuple[str, int]], lowered: str
    ) -> Iterator[Mapping[str, Any]]:
        for key, (st, count) in table.items():
            if f'"{key}"' in lowered:
                yield (
                    {"sourcetype": st, "count": str(count)}
                    if "term(" in lowered
                    else {
                        "source": st,
                        "count": str(count),
                    }
                )


def _entry(
    entities: tuple[str, ...],
    sourcetype: str,
    technique: str = "T1",
    dataset: str = "botsv1",
) -> AnswerKeyEntry:
    return AnswerKeyEntry(
        dataset=dataset,
        technique=technique,
        behavioural_spine=("auth",),
        entities=entities,
        sourcetypes=(sourcetype,),
    )


def test_audit_flags_background_entities_and_portal_only_sourcetypes() -> None:
    doc = audit_mod.audit(
        [
            _entry(("web.example", "10.0.0.5"), "stream:http"),
            _entry(("HOST-A", "user-a"), "xmlwineventlog:sysmon", "T2"),
            _entry(("10.0.0.5", "WEB.example"), "stream:http", "T3"),
        ],
        audit_mod.Probe(_Fake()),
    )
    first, second, third = doc["entries"]
    assert "entity_on_every_sensor_day:10.0.0.5" in first["problems"]
    assert first["entities"]["web.example"]["days_in_declared"] == 1
    assert "same_entity_set_as:botsv1:T3" in first["problems"]
    assert "sourcetype_only_portal_written:xmlwineventlog:sysmon" in second["problems"]
    assert "entity_absent_in_declared_sourcetypes:HOST-A" in second["problems"]
    assert second["entities"]["HOST-A"]["elsewhere"] == {"winhostmon": 7}
    assert doc["usable_entry_count"] == 0
    assert "0 of 3 entries" in audit_mod.render(doc)


def test_a_clean_entry_is_usable() -> None:
    doc = audit_mod.audit([_entry(("web.example",), "stream:http")], audit_mod.Probe(_Fake()))
    assert doc["entries"][0]["problems"] == []
    assert doc["usable_entry_count"] == 1


def test_audit_rejects_entities_that_never_share_an_event() -> None:
    entry = _entry(("web.example", "10.0.0.5"), "stream:http")
    together = audit_mod.audit([entry], audit_mod.Probe(_Fake(joint="1")))["entries"][0]
    apart = audit_mod.audit([entry], audit_mod.Probe(_Fake(joint="0")))["entries"][0]
    assert together["joint_events"] == 1
    assert "entities_never_share_an_event" not in together["problems"]
    assert "entities_never_share_an_event" in apart["problems"]


def test_a_multi_token_entity_falls_back_to_anded_token_terms() -> None:
    doc = audit_mod.audit(
        [_entry(("BGIST-L",), "wineventlog:security", dataset="botsv3")], audit_mod.Probe(_Fake())
    )
    row = doc["entries"][0]
    assert "entity_absent_in_declared_sourcetypes:BGIST-L" not in row["problems"]
    assert row["entities"]["BGIST-L"]["days_in_declared"] == 3


def test_an_entity_present_only_elsewhere_stays_a_true_absence() -> None:
    doc = audit_mod.audit(
        [_entry(("kutekitten",), "stream:smtp", dataset="botsv2")], audit_mod.Probe(_Fake())
    )
    row = doc["entries"][0]
    assert "entity_absent_in_declared_sourcetypes:kutekitten" in row["problems"]
    assert row["entities"]["kutekitten"]["elsewhere"] == {"osquery:results": 6087}
    assert row["usable"] is False


def test_absence_contradicting_the_elsewhere_map_is_its_own_finding() -> None:
    # The split-brain the defect produced: the elsewhere map names the declared sourcetype
    # while the day lookup found none of it. The audit must never call that a plain absence.
    doc = audit_mod.audit(
        [_entry(("bstoll",), "wineventlog:security", dataset="botsv3")], audit_mod.Probe(_Fake())
    )
    row = doc["entries"][0]
    assert "entity_metadata_contradiction:bstoll:wineventlog:security" in row["problems"]
    assert "entity_absent_in_declared_sourcetypes:bstoll" not in row["problems"]
    assert row["entities"]["bstoll"]["elsewhere"] == {"wineventlog:security": 23812}
    assert row["usable"] is False


def test_every_probe_query_resolves_indexed_metadata_never_a_search_time_field() -> None:
    seen: list[str] = []
    search_list = seen

    class _Recording:
        def iter_post(self, search: str, start: float, end: float) -> Iterator[Mapping[str, Any]]:
            search_list.append(search)
            if "NOT source=" in search or ("TERM(" in search and "by _time" in search):
                yield {"_time": "0", "count": "1"}
            elif "TERM(" in search:
                yield {"sourcetype": "stream:http", "count": "1"}
            elif "by _time span=1d" in search:
                yield {"_time": "0", "count": "1"}
            else:
                yield {"source": "stream:http", "count": "1"}

    entry = _entry(("web.example", "10.0.0.5"), "stream:http")
    audit_mod.audit([entry], audit_mod.Probe(_Recording()))
    assert seen, "the audit issued no queries"
    assert all(query.startswith("| tstats") for query in seen)
    assert any('NOT source="portal5:*"' in query for query in seen)
