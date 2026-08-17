from __future__ import annotations

import pytest

from portal.modules.security.core.bully.connectors import MissingCredentialsError, QueryIntent
from portal.modules.security.core.bully.data_plane import DataPlane
from portal.modules.security.core.bully.live_connect import connect_lab_splunk, lab_splunk_connector


class _FakeSplunk:
    index = "portal5_lab"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def _run_search(self, search: str, earliest: str, latest: str) -> list[dict]:
        self.calls.append((search, earliest, latest))
        return [
            {
                "_time": 1_700_000_000.0,
                "host": "corpus-flaws-cloud",
                "raw": '{"eventName":"ConsoleLogin"}',
                "fields": {"eventName": "ConsoleLogin", "userIdentity": "alice"},
            }
        ]


def test_live_splunk_registration_uses_native_query_and_audit(monkeypatch):
    monkeypatch.setenv("LAB_SPLUNK_PASSWORD", "test-secret")
    backend = _FakeSplunk()
    plane = DataPlane()
    profile, probe = connect_lab_splunk(plane, backend=backend, sample_limit=1, count_records=False)

    assert profile.mode == "query_in_place"
    assert profile.capabilities.queryable_in_place is True
    assert probe["records"] == 1
    assert probe["native_query"]["search"].startswith("search index=portal5_lab")
    assert backend.calls
    assert len(plane.audit.entries()) == 1
    assert plane.audit.entries()[0].mode == "query_in_place"
    assert "test-secret" not in str(plane.audit.replay_plan())


def test_live_splunk_connector_fails_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("LAB_SPLUNK_PASSWORD", raising=False)
    connector = lab_splunk_connector(backend=_FakeSplunk())
    with pytest.raises(MissingCredentialsError):
        connector.read(QueryIntent("probe", limit=1))
