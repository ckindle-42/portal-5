"""Tests for the module enable/disable toggle layer — M7 of
BUILD_PROGRAM_MODULARIZATION_ALL_V1.

Covers the resolver (portal.platform.wiki.adapters.modules) and the writeback
adapter (portal.platform.wiki.adapters.writeback_module) in isolated tmp
wiki dirs, same pattern as test_growth_writeback.py.
"""

from __future__ import annotations

from pathlib import Path

from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import reset_canonical_dir, set_canonical_dir


def _patch_modules(monkeypatch, states: dict[str, bool]) -> None:
    import portal.platform.inference.config as cfg
    from portal.platform.inference.config import ModuleToggle, load_portal_config

    real = load_portal_config()
    modules = {name: ModuleToggle(enabled=on) for name, on in states.items()}
    patched = real.model_copy(update={"modules": modules})
    monkeypatch.setattr(cfg, "load_portal_config", lambda *a, **k: patched)


def _seed_module_unit(name: str, enabled: bool) -> None:
    from portal.platform.wiki.store import save_unit

    unit = KnowledgeUnit(
        id=f"unit-module-{name}",
        kind="mixed",
        title=f"Module: {name}",
        sources=[SourceRef(type="code", path=f"portal/modules/{name}/")],
        body=f"Test module unit.\n\n```yaml\nenabled: {str(enabled).lower()}\n```\n",
        tags=["module", name],
    )
    save_unit(unit)


class TestModulesResolver:
    def test_enabled_modules_falls_back_to_defaults_when_config_omits_them(self, monkeypatch):
        from portal.platform.wiki.adapters.modules import DEFAULT_ENABLED_MODULES, enabled_modules

        monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
        _patch_modules(monkeypatch, {})
        assert set(enabled_modules()) == set(DEFAULT_ENABLED_MODULES)

    def test_enabled_modules_reads_config(self, monkeypatch):
        from portal.platform.wiki.adapters.modules import ALL_MODULES, enabled_modules

        monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
        _patch_modules(monkeypatch, {mod: mod != "coding" for mod in ALL_MODULES})
        result = set(enabled_modules())
        assert "coding" not in result
        assert result == set(ALL_MODULES) - {"coding"}

    def test_launched_mcp_ids_always_includes_unmapped_platform_ids(self, monkeypatch):
        """memory/mlx_transcribe/pipeline/wiki have no module mapping — they
        must never be dropped just because every discipline module is off."""
        from portal.platform.wiki.adapters.modules import ALL_MODULES, launched_mcp_ids

        _patch_modules(monkeypatch, dict.fromkeys(ALL_MODULES, False))
        ids = launched_mcp_ids()
        for platform_id in ("memory", "mlx_transcribe", "pipeline", "wiki"):
            assert platform_id in ids, f"{platform_id} was dropped with all modules disabled"
        for base_id in ("filesystem", "fetch", "git", "docker"):
            assert base_id in ids
        assert "proxmox" not in ids

    def test_is_workspace_disabled(self, monkeypatch):
        from portal.platform.wiki.adapters.modules import ALL_MODULES, is_workspace_disabled

        _patch_modules(monkeypatch, {mod: mod != "coding" for mod in ALL_MODULES})
        assert is_workspace_disabled("auto-coding") is True
        assert is_workspace_disabled("auto-research") is False
        assert is_workspace_disabled("auto-security") is False

    def test_owui_workspaces_returns_none_when_nothing_disabled(self, monkeypatch):
        from portal.platform.wiki.adapters.modules import ALL_MODULES, owui_workspaces

        _patch_modules(monkeypatch, dict.fromkeys(ALL_MODULES, True))
        assert owui_workspaces() is None

    def test_wiki_fence_does_not_override_config(self, tmp_path, monkeypatch):
        from portal.platform.wiki.adapters.modules import ALL_MODULES, enabled_modules

        monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
        set_canonical_dir(tmp_path / "canonical")
        try:
            for mod in ALL_MODULES:
                _seed_module_unit(mod, enabled=False)
            assert "general" in enabled_modules()
            assert "media" in enabled_modules()
            assert "music" not in enabled_modules()
            assert "image" not in enabled_modules()
            assert "video" not in enabled_modules()
        finally:
            reset_canonical_dir()

    def test_toggle_changes_one_config_line_and_no_wiki_file(self, tmp_path):
        from portal.platform.inference.cli.module import write_module_enabled

        repo = Path(__file__).resolve().parents[2]
        src = (repo / "config" / "portal.yaml").read_text(encoding="utf-8")
        dest = tmp_path / "portal.yaml"
        dest.write_text(src, encoding="utf-8")
        wiki = repo / "portal_wiki"
        before = sorted(
            (p.relative_to(wiki), p.read_bytes()) for p in wiki.rglob("*") if p.is_file()
        )
        write_module_enabled("documents", False, path=dest)
        lines_before = src.splitlines()
        lines_after = dest.read_text(encoding="utf-8").splitlines()
        diff_at = [
            i for i, (a, b) in enumerate(zip(lines_before, lines_after, strict=True)) if a != b
        ]
        assert len(diff_at) == 1
        assert lines_before[diff_at[0] - 1].strip() == "documents:"
        assert lines_after[diff_at[0]] == "    enabled: false"
        after = sorted(
            (p.relative_to(wiki), p.read_bytes()) for p in wiki.rglob("*") if p.is_file()
        )
        assert before == after


class TestModuleWriteback:
    def test_module_state_change_flips_enabled_field(self, tmp_path):
        from portal.platform.wiki.adapters.writeback_module import module_state_change
        from portal.platform.wiki.store import load_unit
        from portal.platform.wiki.writeback import reset_proposed_dir, set_proposed_dir

        set_canonical_dir(tmp_path / "canonical")
        set_proposed_dir(tmp_path / "proposed")
        try:
            _seed_module_unit("testmod", enabled=True)
            result = module_state_change(
                "testmod", from_state=True, to_state=False, actor="test", auto_confirm=True
            )
            assert result is not None
            unit = load_unit("unit-module-testmod")
            assert unit is not None
            assert "enabled: false" in unit.body
        finally:
            reset_proposed_dir()
            reset_canonical_dir()

    def test_module_state_change_returns_none_for_missing_unit(self, tmp_path):
        from portal.platform.wiki.adapters.writeback_module import module_state_change
        from portal.platform.wiki.writeback import reset_proposed_dir, set_proposed_dir

        set_canonical_dir(tmp_path / "canonical")
        set_proposed_dir(tmp_path / "proposed")
        try:
            result = module_state_change(
                "doesnotexist", from_state=True, to_state=False, actor="test", auto_confirm=True
            )
            assert result is None
        finally:
            reset_proposed_dir()
            reset_canonical_dir()
