from __future__ import annotations

import threading
import time
from typing import Any

from portal.modules.security.core.hunt.engine import _literal_term_segments
from portal.modules.security.core.hunt.executor import DEFAULT_BUDGETS, HuntBudget, HuntExecutor
from portal.modules.security.core.hunt.notables.knowledge import KnowledgeItem
from portal.modules.security.core.hunt.notables.manifest import (
    _provenance_query,
    audit_items,
)


def test_knowledge_audit_reads_items_concurrently_and_keeps_report_order() -> None:
    class _AuditSearch:
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.active = 0
            self.peak = 0

        def iter_post_bounded(self, query: str, *_args: Any, **_kwargs: Any) -> Any:
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.02)
            with self.lock:
                self.active -= 1
            yield {"query": query}

    search = _AuditSearch()
    executor = HuntExecutor(search, HuntBudget(dict(DEFAULT_BUDGETS)))
    items = [
        KnowledgeItem(
            statement=f"statement {index}",
            label=f"label {index:02}",
            label_kind="known_bad",
            label_basis="technique",
            family="family",
            split="build",
            index="idx",
            source_kind="activity",
            query=f"search index=idx id={index}",
        )
        for index in range(24)
    ]

    report = audit_items(executor, items, 0.0, 1.0)

    assert report["items"] == len(items)
    assert report["rows"] == len(items)
    assert search.peak == 8
    assert [row["label"] for row in report["counts"]] == [f"label {i:02}" for i in range(24)]


def test_provenance_query_uses_quoted_plain_terms_for_key_value_embedded_values() -> None:
    """Whole phrases stay quoted while too-short numeric fragments are omitted."""
    query = _provenance_query(
        "hb_kyoushi_s1", "intranet_server", "/audit/audit.log", ["type=CRED_ACQ uid=0"]
    )
    assert " TERM(" not in query
    assert '"type=CRED_ACQ"' in query
    assert '"uid=0"' in query
    assert query.startswith(
        'search index="hb_kyoushi_s1" host="intranet_server" source="/audit/audit.log"'
    )


def test_provenance_query_escapes_embedded_quotes() -> None:
    """Quoted boundaries split clean terms without emitting syntax fragments."""
    query = _provenance_query("foo", "h1", "/s", ['he said "yes"'])
    assert '"said"' in query
    assert '"yes"' not in query
    assert " TERM(" not in query


def test_provenance_query_numeric_value_is_quoted() -> None:
    """Numeric values under four characters do not become query terms."""
    query = _provenance_query("idx", "host", "/src", ["42", "admin"])
    assert '"admin"' in query
    assert '"42"' not in query
    assert " TERM(" not in query


def test_provenance_query_drops_star_adjacent_pieces() -> None:
    query = _provenance_query("idx", "host", "/src", ["alpha*medium*verylongsegment"])

    assert query == 'search index="idx" host="host" source="/src" | head 5'


def test_default_segments_keep_dns_customer_domain_and_drop_star_neighbors() -> None:
    line = (
        "dnsmasq[14919]: reply 3x6-.1-.*SadBEXbCFTw*kitMRtD8ch5XbwBwIbmEHDcmi*"
        "/37v9m99Ips9CCbziwJcl-.customers_2020.xlsx.kiirjekuimkpcrcioastvkeodpnimx.biz "
        "is 10.195.165.2"
    )

    terms = _literal_term_segments(line)
    query = _provenance_query("santos", "hostA", "/dnsmasq.log", [line])

    assert len(terms) <= 2
    assert any(
        term == "customers_2020.xlsx.kiirjekuimkpcrcioastvkeodpnimx.biz"
        or term in {"customers", "2020", "xlsx", "kiirjekuimkpcrcioastvkeodpnimx", "biz"}
        for term in terms
    )
    assert all("*" not in term for term in terms)
    assert "SadBEXbCFTw" not in terms
    assert "kitMRtD8ch5XbwBwIbmEHDcmi" not in terms
    assert any(f'"{term}"' in query for term in terms)
    assert "kitMRtD8ch5XbwBwIbmEHDcmi" not in query


def test_default_segments_keep_key_value_phrases_and_drop_unclean_values() -> None:
    terms = _literal_term_segments("type=CRED_ACQ uid=0")

    assert terms == ("type=CRED_ACQ", "uid=0")
    assert all(len(term) >= 4 for term in terms)
    assert _literal_term_segments("foo^bar") == ()
    assert _literal_term_segments("alpha?beta") == ()


def test_provenance_query_drops_wildcard_value_without_long_segments() -> None:
    query = _provenance_query("idx", "host", "/src", ["***"])

    assert query == 'search index="idx" host="host" source="/src" | head 5'


def test_provenance_query_drops_values_shorter_than_four_characters() -> None:
    query = _provenance_query("idx", "host", "/src", ["bob"])

    assert query == 'search index="idx" host="host" source="/src" | head 5'
