"""Regression net for the five live walkdown product bugs (no network, publishes mocked)."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

dm = importlib.import_module("portal.modules.documents.tools.document_mcp")
cad = importlib.import_module("portal.modules.cad.tools.cad_render_mcp")
vm = importlib.import_module("portal.modules.vulnintel.tools.vulnintel_mcp")

REPO = Path(__file__).resolve().parents[2]


def _needs(module: str):
    return pytest.mark.skipif(
        importlib.util.find_spec(module) is None,
        reason=f"{module} is absent (dev-only CI extras)",
    )


# ── 1. sandbox_status wired on auto-coding ───────────────────────────────────


def test_sandbox_status_wired_on_auto_coding():
    from portal.platform.inference.config import load_portal_config

    ws = load_portal_config().workspaces["auto-coding"]
    assert "sandbox_status" in ws.tools


def test_sandbox_status_in_code_sandbox_manifest():
    from portal.platform.data_loader import load_data

    manifest = load_data("config/inference", "tools_manifest_code_sandbox_mcp")
    assert "sandbox_status" in {t["name"] for t in manifest}


# ── 2. personalassistant prefers the ctx32k build ────────────────────────────


def test_personalassistant_prefers_ctx32k():
    from portal.platform.inference.config import load_persona_map

    p = load_persona_map()["personalassistant"]
    assert p.preferred_models[0] == "gemma4:26b-a4b-it-qat-ctx32k"


def test_ctx32k_tag_served_by_ollama_general():
    cfg = yaml.safe_load((REPO / "config" / "backends.yaml").read_text())
    general = next(g for g in cfg["backends"] if g.get("id") == "ollama-general")
    assert "gemma4:26b-a4b-it-qat-ctx32k" in {m["id"] for m in general["models"]}


# ── 3. convert_document: docx→pdf without LibreOffice, bare names, URLs ──────


@pytest.fixture
def doc_out(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(dm, "OUTPUT_DIR", out)
    monkeypatch.delenv("DOCUMENTS_READ_ROOTS", raising=False)
    monkeypatch.setattr(
        dm,
        "publish_file_sync",
        lambda p: {
            "id": "fid",
            "filename": Path(p).name,
            "url": f"/api/v1/files/fid/content/{Path(p).name}",
        },
    )
    return out


@pytest.fixture
def no_libreoffice(monkeypatch):
    def _absent(*args, **kwargs):
        raise FileNotFoundError("libreoffice")

    monkeypatch.setattr(subprocess, "run", _absent)


def _make_docx(path: Path) -> None:
    from docx import Document

    doc = Document()
    doc.add_heading("Walkdown Report", 0)
    doc.add_paragraph("WALKDOWN_MARKER paragraph text.")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "WALKDOWN_TABLE_CELL"
    table.cell(0, 1).text = "42"
    doc.save(str(path))


@_needs("docx")
@_needs("pymupdf")
def test_docx_to_pdf_without_libreoffice(doc_out, no_libreoffice):
    import pymupdf

    src = doc_out / "report_a1.docx"
    _make_docx(src)
    result = dm.convert_document(str(src), "pdf")
    assert result.get("success") is True, result
    assert result["method"] == "pymupdf"
    pdf = doc_out / result["filename"]
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF-")
    text = "".join(page.get_text() for page in pymupdf.open(stream=data, filetype="pdf"))
    assert "WALKDOWN_MARKER" in text
    assert "WALKDOWN_TABLE_CELL" in text


@_needs("docx")
@_needs("pymupdf")
@pytest.mark.parametrize(
    "ref",
    [
        "report_b2.docx",
        "/api/v1/files/fid/content/report_b2.docx",
        "http://localhost:8080/api/v1/files/fid/content/report_b2.docx",
    ],
)
def test_docx_to_pdf_resolves_bare_name_and_owui_urls(doc_out, no_libreoffice, ref):
    _make_docx(doc_out / "report_b2.docx")
    result = dm.convert_document(ref, "pdf")
    assert result.get("success") is True, result
    assert (doc_out / result["filename"]).read_bytes().startswith(b"%PDF-")


@_needs("docx")
@_needs("pymupdf")
def test_export_pdf_delegates_to_fallback(doc_out, no_libreoffice):
    _make_docx(doc_out / "report_c3.docx")
    result = dm.export_pdf("report_c3.docx")
    assert result.get("success") is True, result
    assert (doc_out / result["filename"]).read_bytes().startswith(b"%PDF-")


def test_convert_document_refuses_outside_and_traversal(doc_out, tmp_path):
    secret = tmp_path / "elsewhere" / "secret.docx"
    secret.parent.mkdir()
    secret.write_bytes(b"not a docx")
    for ref in (str(secret), "../secret.docx"):
        result = dm.convert_document(ref, "pdf")
        assert "error" in result, result
        assert not result.get("success")


# ── 4. convert_cad: bare filenames and OWUI URLs, traversal-safe ─────────────


@pytest.fixture
def cad_ws(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "generated" / "models3d").mkdir(parents=True)
    (ws / "uploads").mkdir()
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("AI_OUTPUT_DIR", str(ws))

    async def _fake_publish(p):
        return {
            "id": "fid",
            "filename": Path(p).name,
            "url": f"/api/v1/files/fid/content/{Path(p).name}",
        }

    monkeypatch.setattr(cad, "publish_file", _fake_publish)
    return ws


def _put_stl(path: Path) -> None:
    path.write_bytes(b"\0" * 80 + b"\0\0\0\0")


@pytest.mark.parametrize(
    "ref",
    [
        "part_ab12.stl",
        "/api/v1/files/fid/content/part_ab12.stl",
        "http://localhost:8080/api/v1/files/fid/content/part_ab12.stl",
    ],
)
def test_resolve_generated_bare_name_and_urls(cad_ws, ref):
    stl = cad_ws / "generated" / "models3d" / "part_ab12.stl"
    _put_stl(stl)
    assert cad._resolve_input(ref) == stl.resolve()


def test_resolve_uuid_prefixed_upload_by_original_name_and_url(cad_ws):
    upload_id = "ba61aacb-1111-2222-3333-444455556666"
    stored = cad_ws / "uploads" / f"{upload_id}_uploaded_part.stl"
    _put_stl(stored)
    refs = [
        "uploaded_part.stl",
        f"/api/v1/files/{upload_id}/content/uploaded_part.stl",
        f"/api/v1/files/{upload_id}/content",
    ]
    for ref in refs:
        assert cad._resolve_input(ref) == stored.resolve(), ref


@_needs("trimesh")
def test_convert_cad_bare_name_end_to_end(cad_ws):
    import trimesh

    stl = cad_ws / "generated" / "models3d" / "bracket_cd34.stl"
    trimesh.creation.box(extents=[60, 40, 30]).export(str(stl))
    result = asyncio.run(cad.convert_cad("bracket_cd34.stl", "obj"))
    assert "error" not in result, result
    out = Path(result["output_path"])
    assert out.suffix == ".obj" and out.is_file()
    assert b"v " in out.read_bytes()


@_needs("trimesh")
def test_convert_cad_download_url_end_to_end(cad_ws):
    import trimesh

    stl = cad_ws / "generated" / "models3d" / "bracket_ef56.stl"
    trimesh.creation.box(extents=[10, 10, 10]).export(str(stl))
    url = "http://localhost:8080/api/v1/files/fid/content/bracket_ef56.stl"
    result = asyncio.run(cad.convert_cad(url, "obj"))
    assert "error" not in result, result
    assert Path(result["output_path"]).is_file()


def test_convert_cad_missing_and_traversal_are_structured_errors(cad_ws, tmp_path):
    secret = tmp_path / "secret.stl"
    _put_stl(secret)
    for ref in ("no_such_file.stl", "../secret.stl", "/etc/passwd"):
        result = asyncio.run(cad.convert_cad(ref, "obj"))
        assert "error" in result, (ref, result)
        assert not result.get("output_path")
    assert not list((cad_ws / "generated" / "models3d").glob("*.obj"))


# ── 5. triage_cve carries the description; auto-security must quote it ───────


@pytest.fixture
def no_audit(monkeypatch):
    monkeypatch.setattr(vm, "_audit", lambda *args, **kwargs: None)


def test_triage_cve_includes_nvd_description(no_audit, monkeypatch):
    description = (
        "Apache Log4j2 2.0-beta9 through 2.15.0 JNDI features used in configuration, "
        "log messages, and parameters do not protect against attacker controlled LDAP "
        "and other JNDI related endpoints."
    )
    monkeypatch.setattr(
        vm,
        "lookup_cve",
        lambda cid: {
            "cve_id": cid,
            "found": True,
            "description": description,
            "cvss": {"baseScore": 10.0},
        },
    )
    monkeypatch.setattr(
        vm, "get_epss", lambda cid: {"cve_id": cid, "epss": 0.94, "percentile": 0.99}
    )
    monkeypatch.setattr(vm, "check_kev", lambda cid: {"cve_id": cid, "in_kev": True})
    out = vm.triage_cve("CVE-2021-44228")
    assert out["description"].startswith("Apache Log4j2")
    assert "Modbus" not in out["description"]
    assert out["label"] == "CRITICAL"


def test_triage_cve_flags_missing_description(no_audit, monkeypatch):
    monkeypatch.setattr(vm, "lookup_cve", lambda cid: {"cve_id": cid, "found": False})
    monkeypatch.setattr(vm, "get_epss", lambda cid: {"cve_id": cid, "epss": None})
    monkeypatch.setattr(vm, "check_kev", lambda cid: {"cve_id": cid, "in_kev": False})
    out = vm.triage_cve("CVE-2021-44228")
    assert out["description"] == ""
    assert "do not guess" in out["description_note"]


def test_auto_security_prompt_requires_verbatim_cve_description():
    from portal.platform.inference.config import load_portal_config

    ws = load_portal_config().workspaces["auto-security"]
    append = ws.system_prompt_append or ""
    assert "verbatim" in append
    assert "never invent" in append
