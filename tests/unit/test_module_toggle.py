"""Tests for the module enable/disable toggle layer — M7 of
BUILD_PROGRAM_MODULARIZATION_ALL_V1.

Covers the resolver (portal.platform.wiki.adapters.modules) and the writeback
adapter (portal.platform.wiki.adapters.writeback_module) in isolated tmp
wiki dirs, same pattern as test_growth_writeback.py.
"""

from __future__ import annotations

from portal.platform.wiki.schema import KnowledgeUnit, SourceRef
from portal.platform.wiki.store import reset_canonical_dir, set_canonical_dir


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
    def test_enabled_modules_falls_back_to_defaults_when_no_wiki_units(self, tmp_path, monkeypatch):
        from portal.platform.wiki.adapters.modules import DEFAULT_ENABLED_MODULES, enabled_modules

        # Isolate from PORTAL_ENABLE_EVAL leaking in from another test in the
        # same session (eval's env-var opt-in is intentionally independent of
        # the wiki toggle this test exercises — see _eval_env_opt_in).
        monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
        set_canonical_dir(tmp_path / "canonical")
        try:
            assert set(enabled_modules()) == set(DEFAULT_ENABLED_MODULES)
        finally:
            reset_canonical_dir()

    def test_enabled_modules_reads_wiki_state_when_present(self, tmp_path):
        from portal.platform.wiki.adapters.modules import ALL_MODULES, enabled_modules

        set_canonical_dir(tmp_path / "canonical")
        try:
            for mod in ALL_MODULES:
                _seed_module_unit(mod, enabled=(mod != "coding"))
            result = set(enabled_modules())
            assert "coding" not in result
            assert result == set(ALL_MODULES) - {"coding"}
        finally:
            reset_canonical_dir()

    def test_launched_mcp_ids_always_includes_unmapped_platform_ids(self, tmp_path):
        """memory/mlx_transcribe/pipeline/wiki have no module mapping — they
        must never be dropped just because every discipline module is off."""
        from portal.platform.wiki.adapters.modules import ALL_MODULES, launched_mcp_ids

        set_canonical_dir(tmp_path / "canonical")
        try:
            for mod in ALL_MODULES:
                _seed_module_unit(mod, enabled=False)
            ids = launched_mcp_ids()
            for platform_id in ("memory", "mlx_transcribe", "pipeline", "wiki"):
                assert platform_id in ids, f"{platform_id} was dropped with all modules disabled"
            # general's base tools stay on too, per spec
            for base_id in ("filesystem", "fetch", "git", "docker"):
                assert base_id in ids
            # but a module-owned id (e.g. security's tools) must be gone
            assert "proxmox" not in ids
        finally:
            reset_canonical_dir()

    def test_is_workspace_disabled(self, tmp_path):
        from portal.platform.wiki.adapters.modules import ALL_MODULES, is_workspace_disabled

        set_canonical_dir(tmp_path / "canonical")
        try:
            for mod in ALL_MODULES:
                _seed_module_unit(mod, enabled=(mod != "coding"))
            assert is_workspace_disabled("auto-coding") is True
            assert is_workspace_disabled("auto-research") is False
            # unmapped workspace (e.g. security's) is never considered disabled
            assert is_workspace_disabled("auto-security") is False
        finally:
            reset_canonical_dir()

    def test_owui_workspaces_returns_none_when_nothing_disabled(self, tmp_path):
        from portal.platform.wiki.adapters.modules import ALL_MODULES, owui_workspaces

        set_canonical_dir(tmp_path / "canonical")
        try:
            for mod in ALL_MODULES:
                _seed_module_unit(mod, enabled=True)
            assert owui_workspaces() is None
        finally:
            reset_canonical_dir()


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
