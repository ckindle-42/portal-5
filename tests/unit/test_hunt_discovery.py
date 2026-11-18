"""Investigation and job behavior, seeded from observation episodes."""

from __future__ import annotations

from typing import Any

from portal.modules.security.core.hunt.engine import HOUR, host_hour_novelty
from portal.modules.security.core.hunt.ranking import query_progress_kind, query_progress_shape

DAY = 86400

T0 = 100 * DAY + 3 * HOUR

LEAD = T0 + 5 * HOUR


def _reduced(rows: list[dict[str, Any]], span: int) -> list[dict[str, Any]]:
    first: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: float(item["_time"])):
        key = (row["host"], row["source"], row["punct"])
        if key not in first:
            bucket = dict(row)
            bucket["_time"] = float(int(float(row["_time"])) // span * span)
            first[key] = bucket
    return list(first.values())


def _novelty_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(4):
        rows.append(
            {
                "_time": float(T0 + index * HOUR),
                "host": "h",
                "source": "s",
                "punct": f"p{index}",
                "count": 1,
            }
        )
    return rows


def test_first_occurrence_reduction_preserves_novelty_exactly() -> None:
    rows = _novelty_rows()
    for span in (60, 600, HOUR, DAY):
        full = host_hour_novelty(rows, span=span)
        reduced = host_hour_novelty(_reduced(rows, span), span=span)
        assert set(full) == set(reduced)
        for key in full:
            assert full[key][0] == reduced[key][0]


def test_narrow_window_reports_standalone_shape() -> None:
    """A single-bucket term scan is flagged standalone; a multi-bucket variant is not."""
    narrow = '| tstats count where index=idx TERM("spk0") by _time span=3600s'
    wide = '| tstats count where index=idx TERM("spk0") by _time span=600s'
    assert query_progress_shape(narrow, float(LEAD), float(LEAD + HOUR)) == "standalone"
    assert query_progress_shape(wide, float(LEAD), float(LEAD + 4 * HOUR)) == "other"


def test_plain_quoted_tstats_terms_keep_their_progress_kinds() -> None:
    narrow = '| tstats count where index="idx" "uid=0" by _time span=3600s'
    cells = '| tstats count where index="idx" "uid=0" by host source'

    assert query_progress_shape(narrow, float(LEAD), float(LEAD + HOUR)) == "standalone"
    assert query_progress_kind(narrow, float(LEAD), float(LEAD + HOUR)) == "hour_screen"
    assert query_progress_kind(cells, float(LEAD), float(LEAD + HOUR)) == "term_tstats"


def test_packed_parent_reports_packed_shape() -> None:
    """A query carrying ``eval _ht=`` is flagged packed, regardless of window width."""
    packed_narrow = (
        '| tstats count where index="idx" '
        'TERM("spk0") by _time span=3600s '
        '| eval _hc=printf("%d:%d",_time,count) | eval _ht="0"'
    )
    packed_wide = (
        '| tstats count where index="idx" '
        'TERM("spk0") by _time span=600s '
        '| eval _hc=printf("%d:%d",_time,count) | eval _ht="0"'
    )
    assert query_progress_shape(packed_narrow, float(LEAD), float(LEAD + HOUR)) == "packed"
    assert query_progress_shape(packed_wide, float(LEAD), float(LEAD + 4 * HOUR)) == "packed"
