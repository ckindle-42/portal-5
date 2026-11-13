"""REMOVED_CLOSED identities named by live seating config fail the audit."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "model_cleanup_audit",
    Path(__file__).resolve().parents[2] / "scripts" / "model_cleanup_audit.py",
)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def _write_fixture(root: Path, *, hint: str, backend_id: str) -> None:
    config = root / "config"
    config.mkdir()
    (config / "backends.yaml").write_text(
        f"backends:\n- id: ollama-general\n  models:\n  - id: {backend_id}\n",
        encoding="utf-8",
    )
    (config / "portal.yaml").write_text(
        "workspaces:\n"
        "  tools-specialist:\n"
        "    variants:\n"
        "      fast:\n"
        f"        model_hint: {hint}\n",
        encoding="utf-8",
    )
    (config / "bench_workspaces.yaml").write_text("workspaces: {}\n", encoding="utf-8")


def test_removed_closed_live_hint_is_a_config_ref(tmp_path: Path) -> None:
    _write_fixture(tmp_path, hint="gone:tag", backend_id="gone:tag")
    live = audit.live_config_model_ids(tmp_path)
    refs = audit.removed_closed_live_refs(
        {"gone:tag": "REMOVED_CLOSED", "kept:tag": "INTEGRATED"},
        live,
    )
    assert [ident for ident, _sources in refs] == ["gone:tag"]
    sources = refs[0][1]
    assert "config/portal.yaml [tools-specialist::fast].model_hint" in sources
    assert "config/backends.yaml [ollama-general].models.id" in sources


def test_removed_closed_absent_from_config_is_not_a_ref() -> None:
    disp = {"hf.co/bartowski/nex-agi_Nex-N2.5-mini-GGUF:Q4_K_M": "REMOVED_CLOSED"}
    assert audit.removed_closed_live_refs(disp, {}) == []


def test_integrated_live_id_is_not_a_removed_ref(tmp_path: Path) -> None:
    _write_fixture(tmp_path, hint="kept:tag", backend_id="kept:tag")
    live = audit.live_config_model_ids(tmp_path)
    assert audit.removed_closed_live_refs({"kept:tag": "INTEGRATED"}, live) == []


def test_report_names_removed_closed_live_refs() -> None:
    report = audit.render_disposition_report(
        {"gone:tag": "REMOVED_CLOSED"},
        [],
        [("gone:tag", ["config/portal.yaml [tools-specialist::fast].model_hint"])],
    )
    assert "REMOVED_CLOSED referenced by live config (1)" in report
    assert "`gone:tag`" in report
    assert "tools-specialist::fast" in report
