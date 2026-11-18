from __future__ import annotations

from portal.modules.security.core.hunt.notables import scoreboard as board
from portal.modules.security.core.hunt.notables.scoreboard import (
    event_time,
)

FIRST = 1616529600.0  # 2021-03-23T20:00:00Z


def test_relate_rows_never_displace_stage1_ranks() -> None:
    first = {"notable_id": "stage1-0"}
    second = {"notable_id": "stage1-1"}
    relation = {"notable_id": "relate-0", "anchor_rank": 0, "relation_score": 1.0}

    ordered = board._with_related([first, second], [relation])

    assert ordered[:2] == [first, second]
    assert ordered[2:] == [relation]


def test_claim_reads_plain_quoted_terms_and_skips_field_values() -> None:
    row = {
        "source_id": "idx:auth.log",
        "generator": "similar_to_known",
        "evidence": [
            {
                "query": (
                    'search index="idx" (source="/auth.log") "systemd-logind" "root" | head 5'
                ),
            }
        ],
    }
    claim = board._claim(row)
    assert claim.terms == ("systemd-logind", "root")
    assert claim.sources == frozenset({"/auth.log"})


def test_event_time_reads_the_shapes_the_ingest_writes() -> None:
    assert event_time('[23/Mar/2021:20:32:09 +0000] "GET / HTTP/1.1"', 1970) == FIRST + 1929.0
    assert event_time('{"timestamp":"2021-03-23T13:59:50.462715+0000"}', 1970) == 1616507990.0
    assert event_time("Mar 23 20:00:00 dnsmasq[1]: query[A] x", 2021) == FIRST
    assert event_time("msg=audit(1616529600.795:103): pid=1", 1970) == 1616529600.795
    assert event_time("[Tue Mar 23 20:32:09.254196 2021] [php7:error] boom", 1970) == FIRST + 1929.0
    assert event_time("no timestamp here", 1970) is None
