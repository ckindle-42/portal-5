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


class _Fake:
    """Answers the probe's four query shapes from a small table."""

    def __init__(self, joint: str = "1") -> None:
        self.days = 3
        self.joint = joint

    def iter_post(self, search: str, start: float, end: float) -> Iterator[Mapping[str, Any]]:
        if "TERM(" in search:
            yield {"sourcetype": "winhostmon", "count": "7"}
        elif "by _time span=1d" in search:
            yield from ({"_time": str(d * 86400), "count": "10"} for d in range(self.days))
        elif "by source" in search:
            if '"stream:http"' in search:
                yield {"source": "stream:http", "count": "50"}
            elif '"xmlwineventlog:sysmon"' in search:
                yield {"source": "portal5:corpus:cousin:x", "count": "4"}
        elif "stats count as count by day" in search:
            if '"10.0.0.5"' in search:
                yield from ({"day": str(d * 86400), "count": "2"} for d in range(self.days))
            elif '"web.example"' in search:
                yield {"day": "86400", "count": "1"}
        elif search.endswith("| stats count as count"):
            yield {"count": self.joint}


def _entry(entities: tuple[str, ...], sourcetype: str, technique: str = "T1") -> AnswerKeyEntry:
    return AnswerKeyEntry(
        dataset="botsv1",
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
