"""Part 4 production defects: P-3 (arguments in the tool name), N-22 (orphaned file on a
failed publish), N-23 (unconfined document reads), N-28 (unconfined kb_ingest), N-12 (the
harness evicting production's models) and N-7 (a version card matching a size)."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
import yaml

from portal.platform.inference.router.tools import split_embedded_call

OFFERED = {"compliance_read", "compliance_requirement", "kb_search"}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ('compliance_read{"ref": "OT-POL-007"}', ("compliance_read", {"ref": "OT-POL-007"})),
        ('compliance_read({"ref": "x"})', ("compliance_read", {"ref": "x"})),
        ('compliance_read(ref="CIP-007-6 R2")', ("compliance_read", {"ref": "CIP-007-6 R2"})),
        ("kb_search(query='relay', kb_id=a)", ("kb_search", {"query": "relay", "kb_id": "a"})),
    ],
)
def test_arguments_written_into_the_name_are_split_out(name, expected):
    tool, args = split_embedded_call(name, "{}", OFFERED)
    assert (tool, json.loads(args)) == expected


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("compliance_read", '{"ref": "x"}'),  # a proper call is untouched
        ("delete_everything", "{}"),  # not offered: left to the gate's refusal
        ("compliance_readx", "{}"),  # a different name, not an embedded form
        ('compliance_read{"ref": "x"}', '{"ref": "y"}'),  # separate arguments win
        ("compliance_read{not json", "{}"),
    ],
)
def test_anything_else_is_returned_unchanged(name, args):
    assert split_embedded_call(name, args, OFFERED) == (name, args)


@pytest.fixture
def docs(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    import importlib

    import portal.modules.documents.tools.document_mcp as dm

    dm = importlib.reload(dm)
    yield dm
    monkeypatch.undo()
    importlib.reload(dm)


def test_a_failed_publish_reports_the_file_it_created(docs, monkeypatch):
    f = docs.OUTPUT_DIR / "report.docx"
    f.write_bytes(b"x")
    monkeypatch.setattr(docs, "publish_file_sync", lambda p: {"error": "Open WebUI unreachable"})
    r = docs._published(f, "Document")
    assert r["success"] is True and r["published"] is False and "unreachable" in r["publish_error"]
    assert f.exists() and r["filename"] == f.name and "path" not in r


def test_document_reads_stay_inside_the_output_root(docs, tmp_path, monkeypatch):
    inside = docs.OUTPUT_DIR / "in.docx"
    inside.write_bytes(b"x")
    assert docs._resolve_input_path(str(inside)) == inside.resolve()
    assert docs._resolve_input_path("in.docx") == inside.resolve()
    outside = tmp_path / "secret.docx"
    outside.write_bytes(b"x")
    with pytest.raises(PermissionError):
        docs._resolve_input_path(str(outside))
    with pytest.raises(PermissionError):
        docs._resolve_input_path(str(docs.OUTPUT_DIR / ".." / "secret.docx"))
    monkeypatch.setenv("DOCUMENTS_READ_ROOTS", str(tmp_path))
    assert docs._resolve_input_path(str(outside)) == outside.resolve()


class _Req:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


def test_kb_ingest_refuses_a_source_outside_its_roots(tmp_path, monkeypatch):
    from portal.modules.research.tools import rag_multimodal as rm

    monkeypatch.setenv("PORTAL5_KB_INGEST_ROOTS", str(tmp_path / "kb"))
    (tmp_path / "kb" / "docs").mkdir(parents=True)
    r = asyncio.run(rm._ingest(_Req({"arguments": {"kb_id": "k", "source_dir": "/etc"}})))
    assert r.status_code == 403
    r = asyncio.run(
        rm._ingest(
            _Req({"arguments": {"kb_id": "k", "source_dir": str(tmp_path / "kb" / "missing")}})
        )
    )
    assert r.status_code == 404  # inside the roots, it gets as far as the existence check


def test_the_harness_never_evicts_a_production_seat_in_pipeline_mode(monkeypatch):
    from tests.wfe import campaign

    seats = campaign.production_seat_tags()
    assert "granite4.1:8b-ctx16k" in seats  # auto-documents' seat
    evicted = []
    monkeypatch.setattr(campaign, "loaded_models", lambda: ["granite4.1:8b-ctx16k", "leftover:tag"])
    monkeypatch.setattr(campaign, "drain_model", lambda tag, t: evicted.append(tag))
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    assert campaign.drain_others("") == ["leftover:tag"]
    evicted.clear()
    monkeypatch.setattr(campaign, "ENGINE", "ollama")  # direct mode: the bench rule stands
    assert sorted(campaign.drain_others("")) == ["granite4.1:8b-ctx16k", "leftover:tag"]


def test_a_version_card_never_matches_a_size():
    from tests.wfe.runner import card_entry

    assert (card_entry("hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k") or ("",))[0] == "qwen3.8"
    assert (card_entry("Qwen3.8-27B-oQ4e-mtp") or ("",))[0] == "qwen3.8"
    assert (card_entry("qwen3:8b") or ("",))[0] != "qwen3.8"
    assert (card_entry("hf.co/Qwen/Qwen3-8B-GGUF:Q4_K_M") or ("",))[0] != "qwen3.8"


def test_card_matching_changes_only_where_a_version_met_a_size():
    """Across every tag in the serving config, the new match differs from the old
    separator-blind one only where the old key's version digits were a size or variant."""
    from tests.wfe import runner

    repo = Path(runner.__file__).resolve().parents[2]
    b = yaml.safe_load((repo / "config" / "backends.yaml").read_text())
    tags = {
        m["id"] if isinstance(m, dict) else m
        for be in b["backends"]
        for m in be.get("models") or []
    }
    tags |= {
        str(w["model_hint"])
        for w in yaml.safe_load((repo / "config" / "portal.yaml").read_text())[
            "workspaces"
        ].values()
        if w.get("model_hint")
    }
    reg = runner._card_registry()

    def old(tag):
        best = None
        for key in reg:
            nk = runner._norm_key(key)
            if (
                nk
                and nk in runner._norm_key(tag)
                and (best is None or len(nk) > len(runner._norm_key(best)))
            ):
                best = key
        return best

    changed = {t: (old(t), (runner.card_entry(t) or (None,))[0]) for t in sorted(tags)}
    changed = {t: v for t, v in changed.items() if v[0] != v[1]}
    for tag, (was, now) in changed.items():
        assert re.search(r"\d\.\d", was or ""), (tag, was, now)  # only version-dot keys changed
        assert runner._VERSION_DOT.sub("", was) not in re.sub(r"[-_.\s]", "~", tag.lower()), (
            tag,
            was,
            now,
        )
