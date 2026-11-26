"""Offline tests: live discovery (config.py) and the scenario registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.qat import config as cq
from tests.qat import scenarios as sc
from tests.qat.config import Discovery, PersonaDef, Settings
from tests.qat.models import QATScenario

# ---------------------------------------------------------------- fixtures

PERSONAS = {
    "general": {"enabled": True},
    "security": {"enabled": True},
    "compliance": {"enabled": True},
    "media": {"enabled": True},
    "data": {"enabled": True},
    "security_redteam": {"enabled": False},
    "eval": {"enabled": False},
}


def _ws(
    module: str,
    hint: str,
    *,
    tools: list[str] | None = None,
    expose: bool = True,
    variants: dict | None = None,
) -> dict:
    return {
        "module": module,
        "name": hint,
        "model_hint": hint,
        "tools": tools or [],
        "expose_to_owui": expose,
        **({"variants": variants} if variants else {}),
    }


PORTAL = {
    "modules": PERSONAS,
    "workspaces": {
        "auto": _ws("general", "q:9b"),
        "auto-daily": _ws(
            "general",
            "d:8b",
            tools=["remember"],
            variants={
                "fast": {"expose_to_owui": True, "model_hint": "d:3b"},
                "hidden": {"expose_to_owui": False},
            },
        ),
        "auto-security": _ws(
            "security",
            "s:7b",
            variants={"blueteam": {"expose_to_owui": True}, "redteam": {"expose_to_owui": True}},
        ),
        "auto-compliance": _ws(
            "compliance",
            "c:8b",
            tools=["portal_documents"],
            variants={"reading": {"expose_to_owui": False}},
        ),
        "auto-audio": _ws(
            "media",
            "a:2b",
            tools=["portal_music"],
            variants={
                "image": {"expose_to_owui": True},
                "music": {"expose_to_owui": True},
                "video": {"expose_to_owui": True},
            },
        ),
        "auto-reasoning": _ws("general", "r:8b", variants={"math": {"expose_to_owui": True}}),
        "auto-vision": _ws("general", "v:11b"),
        "auto-research": _ws("general", "rs:8b", tools=["portal_research"]),
        "auto-council": _ws("general", "ct:8b"),
        "auto-coding": _ws(
            "general",
            "cd:30b",
            tools=["execute_python"],
            variants={"cad": {"expose_to_owui": True}, "bigfix": {"expose_to_owui": True}},
        ),
        "auto-documents": _ws("general", "dc:8b"),
        "auto-spl": _ws("general", "spl:8b"),
        "security-reviewer": _ws("security", "sr:8b"),
        "task-router": _ws("eval", "t:1b"),
        "tools-specialist": _ws("general", "g:7b", expose=False),
    },
    "mcp_fleet": [
        {"id": "data", "name": "portal-data", "port": 8939, "module": "data"},
        {"id": "proxmox", "name": "portal-proxmox", "port": 8927, "module": "security"},
        {"id": "pipeline", "name": "portal-pipeline", "port": 8928, "module": "platform"},
        {"id": "mitre", "name": "portal-mitre", "port": 8929, "module": "security"},
    ],
}


def _preset(pid: str, tools: list[str] | None = None) -> dict:
    return {
        "id": pid,
        "meta": {"name": pid, "toolIds": [f"server:mcp:{t}" for t in (tools or [])]},
        "params": {
            "model": pid,
            "system": f"You handle {pid}.",
            **({"function_calling": "native"} if pid == "auto" else {}),
        },
    }


PRESET_IDS = sorted(
    {
        "auto",
        "auto-daily",
        "auto-daily::fast",
        "auto-security",
        "auto-security::blueteam",
        "auto-security::redteam",
        "auto-compliance",
        "auto-audio",
        "auto-audio::image",
        "auto-audio::music",
        "auto-audio::video",
        "auto-reasoning",
        "auto-reasoning::math",
        "auto-vision",
        "auto-research",
        "auto-council",
        "auto-coding",
        "auto-coding::cad",
        "auto-coding::bigfix",
        "auto-documents",
        "auto-spl",
        "security-reviewer",
    }
)


def make_discovery(
    preset_ids: list[str] | None = None, personas: tuple[PersonaDef, ...] | None = None
) -> Discovery:
    ids = preset_ids if preset_ids is not None else PRESET_IDS
    d = cq.discover(
        portal=PORTAL,
        presets=[_preset(pid, tools=["remember"] if pid == "auto-daily" else None) for pid in ids],
    )
    d.personas = personas or (
        PersonaDef(
            slug="analyst",
            name="Analyst",
            workspace_model="auto-daily",
            category="data",
            model_pin="pin-model:8b",
        ),
        PersonaDef(
            slug="hunter",
            name="Hunter",
            workspace_model="auto-security",
            category="security",
            model_pin="",
        ),
        PersonaDef(
            slug="auditor",
            name="Auditor",
            workspace_model="auto-compliance",
            category="compliance",
            model_pin="",
        ),
    )
    d.gaps = cq.exposure_gaps(d)
    return d


def make_settings(tmp_path: Path, **overrides: str) -> Settings:
    env = {
        "OPENWEBUI_URL": "http://localhost:8080",
        "PIPELINE_URL": "http://localhost:9099",
        "PIPELINE_API_KEY": "test-key",
        "OPENWEBUI_ADMIN_EMAIL": "admin@portal.local",
        "OPENWEBUI_ADMIN_PASSWORD": "pw",
        "OWUI_API_KEY": "",
        "OLLAMA_URL": "http://localhost:11434",
        "OMLX_URL": "http://localhost:8085",
        "OMLX_API_KEY": "",
        "AI_OUTPUT_DIR": str(tmp_path / "AI_Output"),
        "PORTAL_ARM_APPROVAL_TTL_SECONDS": "300",
    }
    env.update(overrides)
    return Settings.load(env_file=tmp_path / "missing.env", environ=env)


# ---------------------------------------------------------------- config.py


class TestEnvParsing:
    def test_parse_env_file_named_keys_quotes_comments(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "# comment\n"
            "OPENWEBUI_ADMIN_PASSWORD=\"p@ss 'word'\"\n"
            "PIPELINE_API_KEY='quoted'\n"
            "EMPTY=\n"
            "not a kv line\n"
            "AI_OUTPUT_DIR=/tmp/ai\n",
            encoding="utf-8",
        )
        parsed = cq.parse_env_file(env)
        assert parsed["OPENWEBUI_ADMIN_PASSWORD"] == "p@ss 'word'"
        assert parsed["PIPELINE_API_KEY"] == "quoted"
        assert parsed["EMPTY"] == ""
        assert parsed["AI_OUTPUT_DIR"] == "/tmp/ai"
        assert "not a kv line" not in parsed

    def test_settings_env_file_beats_defaults_environ_beats_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("PIPELINE_API_KEY=from-file\n", encoding="utf-8")
        s = Settings.load(env_file=env_file, environ={"PIPELINE_API_KEY": "from-env"})
        assert s.pipeline_api_key == "from-env"
        s2 = Settings.load(env_file=env_file)
        assert s2.pipeline_api_key == "from-file"

    def test_settings_omlx_headers_only_with_key(self, tmp_path: Path) -> None:
        assert make_settings(tmp_path).omlx_headers() == {}
        assert make_settings(tmp_path, OMLX_API_KEY="k").omlx_headers() == {
            "Authorization": "Bearer k"
        }

    def test_host_urls_rewrite_docker_names_and_keep_localhost(self, tmp_path: Path) -> None:
        settings = Settings.load(
            env_file=tmp_path / "missing.env",
            environ={
                "OPENWEBUI_URL": "http://open-webui:8080/path",
                "PIPELINE_URL": "http://portal-pipeline:9099/health",
                "OLLAMA_URL": "http://host.docker.internal:11434/api",
                "OMLX_URL": "http://localhost:8085/v1",
            },
        )
        assert settings.owui_url == "http://127.0.0.1:8080/path"
        assert settings.pipeline_url == "http://127.0.0.1:9099/health"
        assert settings.ollama_url == "http://127.0.0.1:11434/api"
        assert settings.omlx_url == "http://localhost:8085/v1"
        assert cq._host_url("https://browser-mcp:3000/tool?q=1") == (
            "https://127.0.0.1:3000/tool?q=1"
        )
        assert cq._host_url("http://portal5-worker:123/path") == "http://127.0.0.1:123/path"

    def test_settings_reads_owui_api_key(self, tmp_path: Path) -> None:
        settings = make_settings(tmp_path, OWUI_API_KEY="provided-token")
        assert settings.owui_api_key == "provided-token"


class TestDiscovery:
    def test_modules_enabled_excludes_disabled(self) -> None:
        d = make_discovery()
        assert "general" in d.modules_enabled
        assert "security_redteam" not in d.modules_enabled
        assert "eval" not in d.modules_enabled

    def test_designed_exposed_ids_gates_eval_and_variants(self) -> None:
        d = make_discovery()
        designed = cq.designed_exposed_ids(d.workspaces, d.modules_enabled)
        assert "auto" in designed
        assert "auto-daily::fast" in designed
        assert "auto-daily::hidden" not in designed
        assert "auto-compliance::reading" not in designed
        assert "task-router" not in designed
        assert "tools-specialist" not in designed
        assert "auto-security::redteam" in designed

    def test_exposure_gaps_both_directions(self) -> None:
        d = make_discovery(preset_ids=["auto"])
        gaps = cq.exposure_gaps(d)
        assert any(g.startswith("designed-not-seeded: auto-daily") for g in gaps)
        d2 = cq.discover(portal=PORTAL, presets=[{"id": "ghost", "meta": {}, "params": {}}])
        assert "seeded-not-designed: ghost" in cq.exposure_gaps(d2)

    def test_perfect_roster_has_no_gaps(self) -> None:
        assert make_discovery().gaps == ()

    def test_load_presets_shape(self) -> None:
        preset = make_discovery().presets["auto"]
        assert preset.function_calling is True
        daily = make_discovery().presets["auto-daily"]
        assert daily.function_calling is False
        assert daily.tool_ids == ("server:mcp:remember",)

    def test_load_personas_reads_slug_and_pin(self, tmp_path: Path) -> None:
        pdir = tmp_path / "personas"
        pdir.mkdir()
        (pdir / "a.yaml").write_text(
            "name: Analyst\nslug: analyst\ncategory: data\nworkspace_model: auto-daily\n"
            "model_pin: pin-model:8b\n",
            encoding="utf-8",
        )
        (pdir / "b.yaml").write_text(
            "name: Hunter\nslug: hunter\ncategory: security\n", encoding="utf-8"
        )
        personas = cq.load_personas(pdir)
        assert [p.slug for p in personas] == ["analyst", "hunter"]
        assert personas[0].model_pin == "pin-model:8b"
        assert personas[1].model_pin == ""

    def test_bench_workspaces_loaded(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        bench = tmp_path / "bench.yaml"
        bench.write_text(
            "workspaces:\n  bench-x:\n    module: eval\n    max_concurrent: 1\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(cq, "BENCH_YAML", bench)
        assert "bench-x" in cq.discover(portal=PORTAL, presets=[]).bench_workspaces


# ---------------------------------------------------------------- scenarios.py


class TestRegistry:
    def test_registry_covers_all_phases(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        assert {s.phase for s in registry} == set(sc.ALL_PHASES)

    def test_cascade_order_tier_then_model_then_id(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        keys = [s.cascade_key() for s in registry]
        assert keys == sorted(keys)

    def test_no_retired_alias_in_any_scenario(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        retired = {
            "auto-coding-agentic",
            "auto-pentest",
            "auto-redteam",
            "auto-security-uncensored",
        }
        for s in registry:
            assert s.model_slug not in retired, s.scenario_id
            assert not retired & set(s.tags), s.scenario_id

    def test_compliance_annotated_in_service_false(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        compliance = [s for s in registry if s.phase == "compliance_smoke"]
        assert compliance
        for s in compliance:
            assert "in_service_false" in s.tags
            assert sc.COMPLIANCE_ANNOTATION in s.notes
            assert s.enabled is True  # runs smoke turns; never silently skipped

    def test_redteam_variants_annotated_disabled(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        red = [s for s in registry if s.scenario_id.endswith("auto-security-redteam")]
        assert len(red) == 1
        assert red[0].enabled is False
        assert "security_redteam_disabled" in red[0].tags
        assert sc.REDTEAM_ANNOTATION in red[0].notes
        blue = next(s for s in registry if s.scenario_id.endswith("auto-security-blueteam"))
        assert blue.enabled is True

    def test_unseeded_spec_preset_annotated_disabled(self) -> None:
        d = make_discovery(preset_ids=[p for p in PRESET_IDS if p != "auto-council"])
        registry = sc.build_registry(make_settings(Path("/tmp")), d)
        council = next(s for s in registry if s.scenario_id == "s2-p2-auto-council")
        assert council.enabled is False
        assert "not seeded" in council.notes
        seeded = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        assert next(s for s in seeded if s.scenario_id == "s2-p2-auto-council").enabled is True

    def test_persona_sweep_cap_counts_only_eligible(self) -> None:
        models = ["aaa-ghost", "bbb-ghost"] + sorted({pid for pid in PRESET_IDS if "::" not in pid})
        personas = tuple(
            PersonaDef(
                slug=f"p{i:02d}", name=f"P{i}", workspace_model=wm, category="x", model_pin=""
            )
            for i, wm in enumerate(models)
        )
        d = make_discovery(personas=personas)
        rows = [
            s
            for s in sc.build_registry(make_settings(Path("/tmp")), d)
            if s.phase == "personas_pin_sweep"
        ]
        assert len(rows) == sc.PERSONA_SWEEP_MAX
        assert all(r.model_slug in d.presets for r in rows)

    def test_media_artifact_kinds(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        kinds = {s.scenario_id: s.artifact_kind for s in registry if s.phase == "media_heavy"}
        assert kinds["s2-p6-auto-audio-stt"] == "docx"
        assert kinds["s2-p6-auto-audio-tts"] == "wav"
        assert kinds["s2-p6-auto-audio::image"] == "png"
        assert kinds["s2-p6-auto-audio::video"] == "mp4"
        assert kinds["s2-p6-auto-audio::music"] == "audio"
        video = next(s for s in registry if s.scenario_id == "s2-p6-auto-audio::video")
        assert video.artifact_min_duration_s == 3.0

    def test_rubric_between_one_and_five(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        for s in registry:
            assert len(s.rubric) <= 5, s.scenario_id
            if s.kind in {"chat", "adversarial", "browser"}:
                assert 1 <= len(s.rubric) <= 5, s.scenario_id

    def test_persona_sweep_deterministic_capped_and_pins(self) -> None:
        settings = make_settings(Path("/tmp"))
        first = [
            s
            for s in sc.build_registry(settings, make_discovery())
            if s.phase == "personas_pin_sweep"
        ]
        second = [
            s
            for s in sc.build_registry(settings, make_discovery())
            if s.phase == "personas_pin_sweep"
        ]
        assert first == second
        assert 0 < len(first) <= sc.PERSONA_SWEEP_MAX
        assert any("pin" in s.tags for s in first)
        assert all(s.expected == "pin-model:8b" for s in first if s.scenario_id == "s2-p5-analyst")

    def test_jarvis_policy_scenario_gated_on_ttl(self, tmp_path: Path) -> None:
        d = make_discovery()
        with_ttl = sc.build_registry(make_settings(tmp_path), d)
        assert any(
            s.scenario_id.endswith("risky-step-confirmation") and s.enabled for s in with_ttl
        )
        without = sc.build_registry(make_settings(tmp_path, PORTAL_ARM_APPROVAL_TTL_SECONDS="0"), d)
        policy = next(s for s in without if s.scenario_id.endswith("risky-step-confirmation"))
        assert policy.enabled is False

    def test_omlx_tool_calling_requires_omlx_backend(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        d = make_discovery()
        settings = make_settings(tmp_path)
        backends = tmp_path / "backends.yaml"
        backends.write_text(
            "backends:\n"
            "  - id: omlx-general\n    group: general\n    type: omlx\n"
            "    models:\n      - {id: mlx-4bit}\n"
            "  - id: ollama-general\n    group: general\n    type: ollama\n"
            "    models:\n      - {id: d:8b}\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(cq, "BACKENDS_YAML", backends)
        assert any(
            s.scenario_id == "s2-p4-omlx-tool-calling" for s in sc.build_registry(settings, d)
        )
        empty = tmp_path / "no_omlx.yaml"
        empty.write_text(
            "backends:\n  - id: o\n    group: general\n    type: ollama\n", encoding="utf-8"
        )
        monkeypatch.setattr(cq, "BACKENDS_YAML", empty)
        assert not any(
            s.scenario_id == "s2-p4-omlx-tool-calling" for s in sc.build_registry(settings, d)
        )

    def test_data_and_proxmox_infra_scenarios(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        infra = [s for s in registry if s.kind == "infra"]
        assert any(s.scenario_id.endswith("data-mcp") for s in infra)
        assert any(s.scenario_id.endswith("proxmox-readonly") for s in infra)
        assert any(s.scenario_id.endswith("pipeline-mcp") for s in infra)

    def test_adaptive_deep_dimensions_and_multi_turn(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        adaptive = [s for s in registry if s.stage == 4]
        by_id = {s.scenario_id: s for s in adaptive}
        assert "s4-auto-core" in by_id
        assert "s4-auto-daily-tools" in by_id
        assert len(by_id["s4-auto-daily-continuity"].prompts) == 2
        assert all(s.notes for s in adaptive)

    def test_hunt_scenarios_target_renamed_sourcetypes(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        hunt = [s for s in registry if s.scenario_id.startswith("s3-hunt-") and s.kind == "chat"]
        joined = " ".join(p for s in hunt for p in s.prompts)
        assert "windows:security" in joined
        assert "windows:sysmon" in joined
        assert "fgt_" in joined
        assert "earliest=-7d@d" in joined
        assert all(s.expected_tools == ("query_splunk",) for s in hunt)

    def test_injection_and_lab_gate_probes_present(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        adversarial = [s for s in registry if s.phase == "security_adversarial"]
        assert any("injection" in s.scenario_id for s in adversarial)
        lab = next(s for s in adversarial if s.scenario_id.endswith("lab-exec"))
        assert "p0-lab-ready" in lab.requires


class TestScenarioShape:
    def test_every_scenario_is_typed_and_routed(self) -> None:
        registry = sc.build_registry(make_settings(Path("/tmp")), make_discovery())
        for s in registry:
            assert isinstance(s, QATScenario)
            assert s.stage in {2, 3, 4}
            assert s.kind in {"chat", "browser", "infra", "adversarial", "pipeline", "tts"}
            if s.kind in {"chat", "adversarial", "pipeline"}:
                assert s.prompts, s.scenario_id

    def test_canonical_variants_from_live_catalog(self) -> None:
        """Variants come from the workspace catalog, not just OWUI presets."""
        d = make_discovery()
        d.presets.pop("auto-security::blueteam")
        d.presets.pop("auto-security::redteam")
        registry = sc.build_registry(make_settings(Path("/tmp")), d)
        blue = next(s for s in registry if s.scenario_id.endswith("auto-security-blueteam"))
        assert blue.kind == "pipeline"
        assert blue.model_slug == "auto-security::blueteam"
        red = next(s for s in registry if s.scenario_id.endswith("auto-security-redteam"))
        assert red.kind == "pipeline"
        assert red.enabled is False

    def test_live_repo_discovery_dry(self) -> None:
        """Against the real repo files: registry derives and stays consistent."""
        d = cq.discover()
        registry = sc.build_registry(Settings.load(env_file=Path("/nonexistent")), d)
        assert registry
        assert {s.stage for s in registry} == {2, 3, 4}
        preset_ids = set(d.presets)
        for s in registry:
            if s.kind in {"chat", "adversarial", "browser"} and s.enabled:
                assert s.model_slug in preset_ids, s.scenario_id
        # today's live roster exposes the uncensored lane, so the refusal probe runs
        refusal = [s for s in registry if s.scenario_id.endswith("refusal-preservation")]
        if "auto-general-uncensored" in preset_ids:
            assert len(refusal) == 1
