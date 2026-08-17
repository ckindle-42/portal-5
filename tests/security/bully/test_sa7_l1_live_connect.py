from __future__ import annotations

import pytest

from portal.modules.security.core.bully.connectors import MissingCredentialsError, QueryIntent
from portal.modules.security.core.bully.data_plane import DataPlane
from portal.modules.security.core.bully.live_connect import (
    connect_lab_splunk,
    lab_splunk_connector,
    register_staged_corpora,
)


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


def test_staged_roots_use_lazy_ingest_and_common_read_surface(tmp_path):
    attack = tmp_path / "attack"
    attack.mkdir()
    (attack / "events.jsonl").write_text('{"user":"alice"}\n{"user":"bob"}\n')
    corpora = tmp_path / "corpora"
    flaws = corpora / "flaws_cloud_cloudtrail" / "records" / "flaws_cloudtrail_logs"
    flaws.mkdir(parents=True)
    (flaws / "records.json").write_text('{"Records":[{"eventName":"ConsoleLogin"}]}')
    invictus = corpora / "invictus_ir_aws_dataset" / "repo" / "CloudTrail"
    invictus.mkdir(parents=True)
    (invictus / "records.json").write_text('[{"eventName":"CreateUser"}]')

    plane = DataPlane()
    profiles = register_staged_corpora(
        plane,
        corpora_root=corpora,
        attack_data_root=attack,
        sample_limit=1,
        counts={"attack_data": 2, "flaws_cloud_cloudtrail": 1, "invictus_ir_aws_dataset": 1},
    )
    assert {profile.source_id for profile in profiles} == {
        "attack_data",
        "flaws_cloud_cloudtrail",
        "invictus_ir_aws_dataset",
    }
    result = plane.connectors["flaws_cloud_cloudtrail"].read(
        QueryIntent("read staged records", limit=1)
    )
    assert result.mode == "ingest"
    assert result.records[0]["eventName"] == "ConsoleLogin"
    assert result.metadata["record_count"] == 1
