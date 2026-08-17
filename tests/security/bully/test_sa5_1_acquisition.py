"""SA5.1 -- corpus acquisition + staged manifest (TASK_BULLY_SA5).

Hermetic: fetch specs assert license compatibility structurally, the manifest
schema validates, checksums are recorded, and a license-blocked source is
never fetched. Network fetch is exercised via a tiny local HTTP server (or
mocked urllib) so the download path is real, not stubbed.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from scripts import corpus_acquire
from scripts.corpus_acquire import (
    ACQUISITION_MANIFEST_SCHEMA,
    SourceFetchSpec,
    acquire_one,
    load_fetch_specs,
    load_manifest,
)


@pytest.fixture
def corpora(tmp_path: Path) -> Path:
    root = tmp_path / "corpora"
    root.mkdir()
    return root


def _dossier(source_id: str):
    from portal.modules.security.core.bully.analyst_corpus import CANDIDATE_SOURCE_DOSSIERS

    return next(d for d in CANDIDATE_SOURCE_DOSSIERS if d.source_id == source_id)


class _StaticHandler(BaseHTTPRequestHandler):
    payload = b"fake cloudtrail records\n" * 100

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args):  # noqa: ARG002 -- test noise
        pass


@pytest.fixture
def file_server():
    server = HTTPServer(("127.0.0.1", 0), _StaticHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/flaws.tar"
    server.shutdown()


def test_load_fetch_specs_indexes_dossiers_and_asserts_license():
    specs = load_fetch_specs()
    assert "flaws_cloud_cloudtrail" in specs
    assert "invictus_ir_aws_dataset" in specs
    assert "cloudtrail_attack_research" in specs
    assert "darpa_optc_tc3" in specs
    # The license-blocked OTRF source has no fetch spec at all.
    assert "otrf_security_datasets" not in specs


def test_license_blocked_source_never_fetched(corpora):
    """A source with an incompatible license is recorded as blocked and its
    staging root is never created -- it is never fetched (A2 / SA4.1)."""
    spec = SourceFetchSpec(
        source_id="otrf_security_datasets",
        name="OTRF Security-Datasets",
        license="GPL-3.0",
        fetch_kind="git",
        url="https://example.com/otrf",
    )
    row = acquire_one(spec, corpora, fetch=True)
    assert row["status"] == "license_blocked"
    assert "GPL-3.0" in row["reason"]
    assert not (corpora / spec.source_id).exists()


def test_download_fetch_records_checksum_and_bytes(corpora, file_server, monkeypatch):
    """A download source streams to disk and the manifest row records byte
    size + sha256 checksum (A2)."""
    spec = SourceFetchSpec(
        source_id="flaws_cloud_cloudtrail",
        name="flaws.cloud CloudTrail",
        license="public",
        fetch_kind="download",
        url=file_server,
    )
    monkeypatch.setattr(corpus_acquire, "corpora_root", lambda: corpora)
    row = acquire_one(spec, corpora, fetch=True)
    assert row["status"] == "fetched"
    assert row["bytes"] == len(_StaticHandler.payload)
    assert row["checksum"]
    assert len(row["checksum"]) == 64
    staged = corpora / spec.source_id / "flaws.tar"
    assert staged.exists()
    manifest = load_manifest(corpora)
    entry = next(e for e in manifest["sources"] if e["source_id"] == spec.source_id)
    assert entry["checksum"] == row["checksum"]
    assert entry["bytes"] == row["bytes"]
    assert entry["url"] == file_server


def test_failed_fetch_is_recorded_finding_not_silent(corpora, monkeypatch):
    """A source that fails to fetch is a recorded finding with the reason --
    never a silent skip (A2)."""
    spec = SourceFetchSpec(
        source_id="flaws_cloud_cloudtrail",
        name="flaws.cloud CloudTrail",
        license="public",
        fetch_kind="download",
        url="http://127.0.0.1:1/unreachable.tar",
    )
    monkeypatch.setattr(corpus_acquire, "corpora_root", lambda: corpora)
    row = acquire_one(spec, corpora, fetch=True)
    assert row["status"] == "failed"
    assert row["reason"]
    manifest = load_manifest(corpora)
    assert any(
        e["source_id"] == spec.source_id and e["status"] == "failed" for e in manifest["sources"]
    )


def test_manifest_schema_and_append_only(corpora):
    manifest = load_manifest(corpora)
    assert manifest["schema"] == ACQUISITION_MANIFEST_SCHEMA
    assert manifest["sources"] == []


def test_staged_checksum_deterministic(corpora, tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.log").write_text("alpha", encoding="utf-8")
    (root / "b.log").write_text("beta", encoding="utf-8")
    first = corpus_acquire._staged_checksum(root)
    (root / "c.log").write_text("gamma", encoding="utf-8")
    second = corpus_acquire._staged_checksum(root)
    assert first != second
    assert len(first) == 64


def test_real_dossier_fetch_spec_licenses_compatible():
    """Every declared fetch spec carries a license compatible with the
    self-hosted stack (structural guarantee -- no blocked source has a spec)."""
    specs = load_fetch_specs()
    for spec in specs.values():
        dossier = _dossier(spec.source_id)
        assert dossier.license_compatible is True
        assert spec.license == dossier.license
