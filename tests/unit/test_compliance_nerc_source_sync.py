"""Official NERC source synchronization tests (END_TO_END Phase 2 / foundation
P2). Hermetic: all network fetches are stubbed; the lifecycle fixture is a
saved public workbook derived from NERC's own One-Stop Shop rows.

Covers: lifecycle parsing against the real registry values, fingerprint-aware
idempotence (UNCHANGED on identical bytes), failure preservation of the last
verified snapshot, immutable-revision registration in the canonical store, and
manifest retention.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from portal.modules.compliance.core.nerc_source_sync import (
    ONE_STOP_SHOP_URL,
    Artifact,
    parse_lifecycle,
    sync_official_bundle,
)

FIXTURE = (
    Path(__file__).resolve().parents[1] / "data" / "compliance_nerc" / "one_stop_shop_fixture.xlsx"
)
FIXTURE_BYTES = FIXTURE.read_bytes()
FIXTURE_SHA = hashlib.sha256(FIXTURE_BYTES).hexdigest()

PDF_BYTES = b"%PDF-1.6 fake standard bytes for hermetic sync\n"
PLAN_BYTES = b"%PDF-1.6 fake implementation plan bytes\n"

URL_MAP = {
    ONE_STOP_SHOP_URL: FIXTURE_BYTES,
    "https://www.nerc.com/globalassets/standards/reliability-standards/cip/cip-007-6.pdf": PDF_BYTES,
    "https://www.nerc.com/globalassets/standards/reliability-standards/cip/cip-007-7.1.pdf": b"%PDF-1.6 other pdf v7.1\n",
    "https://www.nerc.com/globalassets/standards/reliability-standards/cip/CIP_Implementation_Plan_CLEAN_BOARD.pdf": PLAN_BYTES,
    "https://www.nerc.com/globalassets/standards/reliability-standards/cip/2016-02-Virtualization-Implementation-Plan_clean_04032024.pdf": PLAN_BYTES,
    "https://www.nerc.com/globalassets/standards/projects/2016-02/2016-02_cip-007-7_technical_rationale_04032024.pdf": PLAN_BYTES,
}


class RecordingFetch:
    """Stub transport: serves URL_MAP, counts calls, can fail selectively."""

    def __init__(self, fail_urls: set[str] | None = None):
        self.calls: list[str] = []
        self.fail_urls = fail_urls or set()

    def __call__(self, url: str, **_: object) -> bytes:
        self.calls.append(url)
        if url in self.fail_urls:
            raise ConnectionError(f"stubbed failure for {url}")
        return URL_MAP[url]


# ── lifecycle parsing (against saved public registry values) ────────────────


def test_lifecycle_facts_match_the_official_registry():
    facts = parse_lifecycle(FIXTURE_BYTES, registry_sha256=FIXTURE_SHA)
    six = facts["CIP-007-6"]
    assert six.status == "Mandatory Subject to Enforcement"
    assert six.effective == "2016-07-01"
    assert six.inactive == "2028-06-30"  # the retirement boundary
    assert six.phased_implementation is True
    assert six.implementation_plan_url.endswith("CIP_Implementation_Plan_CLEAN_BOARD.pdf")
    assert six.docket.startswith("Filing/Order Docket")

    seven_one = facts["CIP-007-7.1"]
    assert seven_one.status == "Subject to Future Enforcement"
    assert seven_one.effective == "2028-07-01"
    assert seven_one.inactive == ""
    assert seven_one.technical_rationale_url  # linked for the future revision

    seven = facts["CIP-007-7"]
    assert seven.status == "Inactive"  # replaced by 7.1 via errata, never effective


def test_registry_provenance_is_carried_on_the_facts():
    facts = parse_lifecycle(FIXTURE_BYTES, registry_sha256=FIXTURE_SHA)
    assert all(f.registry_sha256 == FIXTURE_SHA for f in facts.values())


# ── synchronization (hermetic) ──────────────────────────────────────────────


def test_sync_acquires_verifies_and_records(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "portal.modules.compliance.core.nerc_source_sync._register_in_store",
        lambda *a, **k: hashlib.sha256(k["payload"]).hexdigest(),  # bytes → revision id
    )
    fetch = RecordingFetch()
    report = sync_official_bundle(directory=tmp_path, fetch=fetch, register_store=True)
    by_name = {a.name: a for a in report.artifacts}
    assert by_name["one-stop-shop.xlsx"].status == "ACQUIRED"
    assert by_name["cip-007-6.pdf"].sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert by_name["cip-007-7.1.pdf"].status == "ACQUIRED"
    assert by_name["cip-007-6-implementation-plan.pdf"].role == "implementation_plan"
    assert by_name["cip-007-7.1-technical-rationale.pdf"].role == "technical_rationale"
    assert set(report.lifecycle) == {"CIP-007-6", "CIP-007-7.1"}
    assert not report.warnings

    manifest = json.loads((tmp_path / "acquisition_manifest.json").read_text())
    assert manifest["lifecycle"]["CIP-007-6"]["inactive"] == "2028-06-30"
    assert manifest["store_revisions"]["cip-007-6.pdf"]
    # bytes written once, immutably
    assert (tmp_path / "cip-007-6.pdf").read_bytes() == PDF_BYTES


def test_sync_is_fingerprint_aware_unchanged_bytes_never_rewrite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "portal.modules.compliance.core.nerc_source_sync._register_in_store",
        lambda *a, **k: "r",
    )
    fetch = RecordingFetch()
    sync_official_bundle(directory=tmp_path, fetch=fetch)
    first_mtime = (tmp_path / "cip-007-6.pdf").stat().st_mtime_ns
    n_first = len(fetch.calls)

    report2 = sync_official_bundle(directory=tmp_path, fetch=fetch)
    assert (tmp_path / "cip-007-6.pdf").stat().st_mtime_ns == first_mtime  # not rewritten
    assert by(report2.artifacts, "cip-007-6.pdf").status == "UNCHANGED"
    assert by(report2.artifacts, "one-stop-shop.xlsx").status == "UNCHANGED"
    n_second = len(fetch.calls) - n_first
    assert n_second == n_first  # one fetch per artifact, zero rewrites
    assert not report2.warnings


def test_failed_refresh_preserves_last_verified_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "portal.modules.compliance.core.nerc_source_sync._register_in_store",
        lambda *a, **k: "r",
    )
    sync_official_bundle(directory=tmp_path, fetch=RecordingFetch())
    before = (tmp_path / "cip-007-6.pdf").read_bytes()

    failing = RecordingFetch(fail_urls={ONE_STOP_SHOP_URL})
    report = sync_official_bundle(directory=tmp_path, fetch=failing)
    assert (tmp_path / "cip-007-6.pdf").read_bytes() == before  # retained
    registry = by(report.artifacts, "one-stop-shop.xlsx")
    assert registry.status == "UNCHANGED"
    assert "refresh failed" in registry.warning
    # the dated currency warning is present and says the facts are not current
    assert any("not refreshed" in w and "not be treated as current" in w for w in report.warnings)
    # lifecycle facts come from the RETAINED snapshot, with its own provenance
    assert set(report.lifecycle) == {"CIP-007-6", "CIP-007-7.1"}
    manifest = json.loads((tmp_path / "acquisition_manifest.json").read_text())
    assert manifest["artifacts"][0]["warning"]


def test_acquisition_failure_with_no_prior_snapshot_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "portal.modules.compliance.core.nerc_source_sync._register_in_store",
        lambda *a, **k: "r",
    )
    fetch = RecordingFetch(fail_urls={u for u in URL_MAP if u != ONE_STOP_SHOP_URL})
    report = sync_official_bundle(directory=tmp_path, fetch=fetch)
    failed = [a for a in report.artifacts if a.status == "FAILED"]
    assert failed, "a total PDF outage must surface as FAILED artifacts"
    assert all(not a.sha256 for a in failed)  # nothing fingerprinted, nothing claimed
    assert report.lifecycle  # facts still parsed from the good registry fetch


def test_store_registration_creates_immutable_revisions(tmp_path):
    repo_calls: list[tuple[str, bytes]] = []

    def fake_register(*args: object, **kwargs: object) -> str:
        logical_id = str(kwargs.get("logical_id") or (args[0] if args else ""))
        payload = bytes(kwargs.get("payload") or b"")  # type: ignore[arg-type]
        repo_calls.append((logical_id, payload))
        return hashlib.sha256(payload).hexdigest()

    import portal.modules.compliance.core.nerc_source_sync as mod

    original = mod._register_in_store
    mod._register_in_store = fake_register
    try:
        report = sync_official_bundle(
            directory=tmp_path, fetch=RecordingFetch(), register_store=True
        )
    finally:
        mod._register_in_store = original
    assert {logical for logical, _ in repo_calls} >= {
        "NERC/cip-007-6.pdf",
        "NERC/cip-007-7.1.pdf",
        "NERC/one-stop-shop.xlsx",
    }
    assert report.store_revisions["cip-007-6.pdf"] == hashlib.sha256(PDF_BYTES).hexdigest()


def test_absent_standard_is_a_warning_not_silent_success(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "portal.modules.compliance.core.nerc_source_sync._register_in_store",
        lambda *a, **k: "r",
    )
    report = sync_official_bundle(versions=("6", "9.9"), directory=tmp_path, fetch=RecordingFetch())
    assert any("CIP-007-9.9" in w and "absent" in w for w in report.warnings)
    assert "CIP-007-9.9" not in report.lifecycle


def by(artifacts: list[Artifact], name: str) -> Artifact:
    return next(a for a in artifacts if a.name == name)


def test_artifact_fingerprint_binds_url_bytes_and_time():
    a = Artifact(name="x", url="u", sha256="h", retrieved_at="t")
    b = Artifact(name="x", url="u", sha256="h", retrieved_at="t2")
    assert a.fingerprint() != b.fingerprint()
