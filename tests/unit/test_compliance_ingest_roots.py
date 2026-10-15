"""N-33: compliance_ingest reads only inside the public compliance data dir and the operator
profile's corpus_dirs. The route is offered to the model, so its source_dir must be confined."""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest

cr = importlib.import_module("portal.modules.compliance.tools.compliance_retrieval")
op = importlib.import_module("portal.modules.compliance.core.operator_profile")
ingest_mod = importlib.import_module("portal.modules.compliance.core.ingest")


class _Req:
    def __init__(self, a: dict) -> None:
        self._a = {"arguments": a}

    async def json(self) -> dict:
        return self._a


def _post(source_dir: str) -> tuple[int, dict]:
    resp = asyncio.run(cr._ingest(_Req({"kb_id": "operator_corpus", "source_dir": source_dir})))
    return resp.status_code, json.loads(resp.body)


@pytest.fixture
def ingested(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record what the route hands to the ingest function instead of ingesting."""
    seen: list[str] = []

    async def _fake(source_dir: str, kb_id: str, rebuild: bool) -> dict:
        seen.append(source_dir)
        return {"ok": True}

    monkeypatch.setattr(ingest_mod, "ingest_folder", _fake)
    return seen


def _profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corpus: dict[str, str]) -> None:
    path = tmp_path / "operator_profile.json"
    path.write_text(json.dumps({"corpus_dirs": corpus}), encoding="utf-8")
    monkeypatch.setattr(op, "PROFILE_PATH", path)
    op.profile.cache_clear()


def test_outside_every_root_is_refused_and_not_ingested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ingested: list[str]
) -> None:
    _profile(tmp_path, monkeypatch, {"source_root": str(tmp_path / "corpus")})
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    status, body = _post(str(outside))

    assert status == 403
    assert "outside the compliance ingest roots" in body["error"]
    assert str(tmp_path / "corpus") in body["error"]
    assert ingested == []


def test_profile_corpus_dir_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ingested: list[str]
) -> None:
    corpus = tmp_path / "corpus"
    (corpus / "CIP-007").mkdir(parents=True)
    _profile(tmp_path, monkeypatch, {"source_root": str(corpus)})

    status, body = _post(str(corpus / "CIP-007"))

    assert status == 200
    assert body == {"ok": True}
    assert ingested == [str((corpus / "CIP-007").resolve())]


def test_relative_profile_dir_resolves_against_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ingested: list[str]
) -> None:
    repo = Path(cr.__file__).resolve().parents[4]
    _profile(tmp_path, monkeypatch, {"internal_v9": "coding_task/v9_compliance/CORPUS-A"})

    status, _ = _post(str(repo / "coding_task" / "v9_compliance" / "CORPUS-A"))

    assert status == 200
    assert len(ingested) == 1


def test_no_profile_allows_only_the_public_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ingested: list[str]
) -> None:
    monkeypatch.setattr(op, "PROFILE_PATH", tmp_path / "absent.json")
    op.profile.cache_clear()
    public = Path(cr.__file__).resolve().parents[1] / "data" / "cip_pdfs"

    status, _ = _post(str(public))
    assert status == 200

    status, body = _post(str(tmp_path))
    assert status == 403
    assert "outside the compliance ingest roots" in body["error"]
    assert len(ingested) == 1


def test_no_profile_never_crashes_the_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ingested: list[str]
) -> None:
    monkeypatch.setattr(op, "PROFILE_PATH", tmp_path / "absent.json")
    op.profile.cache_clear()

    assert cr._compliance_ingest_roots() == [Path(cr.__file__).resolve().parents[1] / "data"]
