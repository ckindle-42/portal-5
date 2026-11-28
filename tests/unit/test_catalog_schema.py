"""Tests for persona catalog schema validation.

Verifies that:
- A persona referencing a non-existent workspace_model raises at strict-load.
- All 150 production personas have valid workspace_model references.
- No persona has a browser_policy field (retired in M3).
- resolve_preset_tools invariant: matches the M3 oracle snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from portal.platform.inference.config import (
    PersonaSpec,
    load_persona_map,
    load_portal_config,
    resolve_preset_tools,
    validate_persona_parents,
)
from portal.platform.inference.router.workspaces import (
    WORKSPACES,
)

REPO = Path(__file__).resolve().parent.parent.parent

SNAPSHOT = REPO / "tests" / "fixtures" / "preset_resolution_snapshot.json"


@pytest.fixture(autouse=True)
def _restore_config_cache():
    """Restore the real config cache after any test that swaps the yaml."""
    yield
    load_portal_config(_force_reload=True)


def test_persona_with_unknown_workspace_raises(tmp_path: Path) -> None:
    """validate_persona_parents raises when a persona's workspace_model is unknown."""
    p = tmp_path / "orphan.yaml"
    p.write_text(
        "name: Orphan\nslug: orphan\ncategory: test\nmodule: general\n"
        "workspace_model: does-not-exist\nsystem_prompt: test prompt\n"
    )
    personas = load_persona_map(personas_dir=tmp_path)
    with pytest.raises(ValueError, match="does-not-exist"):
        validate_persona_parents(personas)


def test_persona_missing_workspace_model_raises(tmp_path: Path) -> None:
    """PersonaSpec requires workspace_model — missing field raises pydantic ValidationError."""
    p = tmp_path / "bad.yaml"
    p.write_text("name: Bad\nslug: bad\ncategory: test\n")
    with pytest.raises(Exception, match="workspace_model"):
        PersonaSpec.model_validate(yaml.safe_load(p.read_text()))


def test_all_production_personas_have_valid_parents() -> None:
    """All production personas reference an existing workspace."""
    personas = load_persona_map()
    on_disk = len(
        list((Path(__file__).resolve().parents[2] / "config" / "personas").glob("*.yaml"))
    )
    assert len(personas) == on_disk, f"{len(personas)} loaded personas, {on_disk} persona files"
    validate_persona_parents(personas)  # raises if any parent is invalid


def test_no_persona_has_browser_policy() -> None:
    """After M3, no persona YAML may contain a browser_policy field."""
    personas_dir = REPO / "config" / "personas"
    with_policy = [
        f.name for f in sorted(personas_dir.glob("*.yaml")) if "browser_policy" in f.read_text()
    ]
    assert not with_policy, f"browser_policy found in retired persona YAMLs: {with_policy}"


def test_no_gdpr_in_persona_catalog() -> None:
    """GDPR is out of compliance scope; no persona YAML may reference it (gdprdpoadvisor removed)."""
    personas_dir = REPO / "config" / "personas"
    offenders = [
        f.name for f in sorted(personas_dir.glob("*.yaml")) if "gdpr" in f.read_text().lower()
    ]
    assert not offenders, f"GDPR references in persona YAMLs (out of scope): {offenders}"


def test_workspace_tools_match_snapshot() -> None:
    """WORKSPACES default tool lists must match the M3 oracle for all 90 workspaces."""
    snap = json.loads(SNAPSHOT.read_text())
    failures = []
    for ws_id, ws in WORKSPACES.items():
        tools = sorted(ws.get("tools", []))
        key = f"workspace::{ws_id}"
        if key in snap and snap[key]["effective_tools"] != tools:
            failures.append(f"{ws_id}: got {tools}, want {snap[key]['effective_tools']}")
    assert not failures, "Workspace tools drifted from snapshot:\n" + "\n".join(failures[:10])


def test_hunt_reasoning_is_an_internal_batching_seat() -> None:
    """The hunt's reasoning seat: internal, tool-free, deterministic, admits 8."""
    spec = load_portal_config().workspaces["hunt-reasoning"]
    assert spec.router is False, "the hunt seat must never be an auto-routing destination"
    assert spec.expose_to_owui is False, "it is called by the hunt, not by a person"
    assert spec.tools == [] and spec.temperature == 0.0
    assert spec.max_concurrent == 8, "one batching (oMLX) backend admits 8 concurrent"


def test_hunt_reasoning_has_a_batching_seat_and_a_gguf_fallback() -> None:
    """The hint resolves on an oMLX checkpoint and on its own Ollama GGUF tag."""
    from portal.platform.inference.cluster_backends import BackendRegistry

    hint = load_portal_config().workspaces["hunt-reasoning"].model_hint
    # The hint is a seat decision (A/B-switchable); this test asserts resolvability only.
    assert hint, "the hunt seat must declare a model_hint"
    registry = BackendRegistry(str(REPO / "config" / "backends.yaml"))
    serving = {b.type for b in registry.list_backends() if b.resolve_model(hint or "")}
    assert {"omlx", "ollama"} <= serving
    modelfile = (REPO / "config/modelfiles/gemma4-26b-a4b-it-qat-ctx8k-hunt.Modelfile").read_text()
    assert "FROM gemma4:26b-a4b-it-qat-ctx8k" in modelfile
    assert "PARAMETER temperature 0" in modelfile


def test_compliance_reading_seat_serves_qwen36_with_an_ollama_fallback() -> None:
    """The reading seat serves Qwen3.6-35B-A3B at its 128k window (2026-11-28
    seat swap): the hint is the GGUF tag, so an oMLX outage falls back to
    Ollama on the same weights, and the machine-seat twin carries the same hint
    so machine calls that address the reading tag land in the bare
    compliance-mapping lane."""
    from portal.platform.inference import model_addressing
    from portal.platform.inference.cluster_backends import BackendRegistry

    workspaces = model_addressing.workspaces()
    reading = workspaces["auto-compliance::reading"]
    hint = reading["model_hint"]
    assert hint == "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx128k"
    # The Qwen3.6 instruct card row, above the compliance lane's 0.3 ceiling and
    # recorded as the card's own value (settings_audit sampling_card_over_lane).
    assert float(reading["temperature"]) == 0.7
    # The machine-seat twin must carry the same hint so machine calls that
    # address the reading tag land in the bare compliance-mapping lane.
    assert workspaces["compliance-mapping"]["model_hint"] == hint
    registry = BackendRegistry(str(REPO / "config/backends.yaml"))
    serving = {b.type for b in registry.list_backends() if b.resolve_model(hint or "")}
    assert {"omlx", "ollama"} <= serving
    modelfile = (
        REPO / "config/modelfiles/qwen3.6-35b-a3b-ud-q4_k_xl-ctx128k.Modelfile"
    ).read_text()
    assert "FROM hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k" in modelfile
    assert "PARAMETER num_ctx 131072" in modelfile
    # The retired arm's variant is gone; the seat is the only reading variant.
    assert "reading-qwen36" not in workspaces["auto-compliance"]["variants"]


def test_resolve_preset_tools_typed_path() -> None:
    """resolve_preset_tools with PersonaSpec gives same result as dict path."""
    persona_spec = PersonaSpec(
        name="Test",
        slug="test",
        category="general",
        module="general",
        workspace_model="auto",
        tools_allow=["memory", "rag"],
    )
    result = resolve_preset_tools(persona_spec, ["memory", "rag", "research"])
    assert result == ["memory", "rag"]


def test_resolve_preset_tools_deny() -> None:
    """tools_deny removes entries from the effective set."""
    persona_spec = PersonaSpec(
        name="Test",
        slug="test",
        category="general",
        module="general",
        workspace_model="auto",
        tools_deny=["research"],
    )
    result = resolve_preset_tools(persona_spec, ["memory", "rag", "research"])
    assert "research" not in result
    assert "memory" in result


def test_resolve_preset_tools_no_persona() -> None:
    """None persona returns workspace tools unchanged."""
    result = resolve_preset_tools(None, ["memory", "rag"])
    assert result == ["memory", "rag"]


def test_security_inkling_seats_preserve_card_and_fallback_contract() -> None:
    """The approved Inkling seats resolve on their intended engines and card."""
    from portal.platform.inference.cluster_backends import BackendRegistry

    backend_data = yaml.safe_load((REPO / "config" / "backends.yaml").read_text())
    backends = {backend["id"]: backend for backend in backend_data["backends"]}
    models = {
        backend_id: {
            model["id"]: model for model in backend.get("models", []) if isinstance(model, dict)
        }
        for backend_id, backend in backends.items()
    }
    assert models["omlx-security"]["Inkling-2-Mini-oQ4e-mtp"]["supports_tools"] is True
    assert models["omlx-security"]["Inkling-2-Mini-oQ4e-mtp"]["keep_reason"]
    abliterated_hint = "Inkling-2-Mini-abliterated-oQ4e-mtp"
    gguf_fallback = "portal5/orcarouter-inkling-2-mini-abliterated:mix16g-ctx32k"
    for group in ("omlx-security", "omlx-general"):
        assert models[group][abliterated_hint]["supports_tools"] is True
        assert models[group][abliterated_hint]["keep_reason"]
    assert (
        models["ollama-security"]["portal5/orcarouter-inkling-2-mini-abliterated:mix16g-ctx32k"][
            "supports_tools"
        ]
        is True
    )
    assert (
        models["ollama-general"]["portal5/orcarouter-inkling-2-mini-abliterated:mix16g-ctx32k"][
            "supports_tools"
        ]
        is True
    )
    assert models["ollama-security"]["inkling-2-mini:ctx256k"]["supports_tools"] is True
    registry = BackendRegistry(str(REPO / "config" / "backends.yaml"))
    registry_backends = {backend.id: backend for backend in registry.list_backends()}
    base_hint = "Inkling-2-Mini-oQ4e-mtp"
    assert registry_backends["omlx-security"].resolve_model(base_hint) == base_hint
    assert registry_backends["ollama-security"].resolve_model(base_hint) == "inkling-2-mini:ctx256k"
    for group in ("ollama-security", "ollama-general"):
        assert registry_backends[group].resolve_model(abliterated_hint) == gguf_fallback
    assert "inkling-2-mini:ctx256k" not in backends["omlx-general"].get("aliases", {})

    portal = yaml.safe_load((REPO / "config" / "portal.yaml").read_text())
    workspace = portal["workspaces"]["auto-security"]
    assert workspace["model_hint"] == base_hint
    assert "context_limit" not in workspace
    assert workspace["predict_limit"] == 32768
    assert (workspace["temperature"], workspace["top_p"]) == (1.0, 0.95)
    assert workspace["emits_reasoning"] is True
    assert "think" not in workspace
    assert not {
        "top_k",
        "min_p",
        "repeat_penalty",
        "stop",
        "sampling_override",
    }.intersection(workspace)


def test_abliterated_inkling_security_variants_follow_default_reasoning_contract() -> None:
    """The abliterated seats use Inkling's default reasoning contract."""
    from portal.platform.inference.model_cards import card_entry

    portal = yaml.safe_load((REPO / "config" / "portal.yaml").read_text())
    variants = portal["workspaces"]["auto-security"]["variants"]
    abliterated_hint = "Inkling-2-Mini-abliterated-oQ4e-mtp"
    gguf_fallback = "portal5/orcarouter-inkling-2-mini-abliterated:mix16g-ctx32k"
    inherited_base_variants = {"blueteam-orchestrated", "blueteam-council"}
    inkling_reasoning_variants = {"uncensored", "purpleteam-deep"}
    assert all(
        variant.get("think") is (name == "pentest")
        for name, variant in variants.items()
        if name not in inherited_base_variants | inkling_reasoning_variants
    )
    assert all(
        variant.get("emits_reasoning") is False
        for name, variant in variants.items()
        if name not in ({"pentest"} | inherited_base_variants | inkling_reasoning_variants)
    )
    uncensored = variants["uncensored"]
    assert uncensored["model_hint"] == abliterated_hint
    assert uncensored["context_limit"] == 262144
    assert uncensored["predict_limit"] == 32768
    assert "think" not in uncensored
    assert uncensored["emits_reasoning"] is True
    assert abliterated_hint in uncensored["description"]
    assert gguf_fallback in uncensored["description"]
    deep = variants["purpleteam-deep"]
    assert deep["model_hint"] == abliterated_hint
    assert deep["context_limit"] == 262144
    assert deep["predict_limit"] == 32768
    assert "think" not in deep
    assert deep["emits_reasoning"] is True
    assert abliterated_hint in deep["description"]
    assert gguf_fallback in deep["description"]
    assert [hop["model"] for hop in deep["chain"]] == [
        "granite4.1:8b-ctx8k",
        "qwen3-coder:30b-a3b-q4_K_M",
        "qwen3.6:27b-q4_K_M",
    ]
    assert card_entry(uncensored["model_hint"])[0] == "inkling-2-mini"
    assert f"### `{uncensored['model_hint']}`" in (REPO / "config" / "MODEL_CATALOG.md").read_text()


def test_general_uncensored_seats_inkling_abliterated_with_general_failover() -> None:
    """The base uncensored general seat is the oMLX abliterated checkpoint.

    Variants keep their own hints. Failover is the existing general-group alias.
    """
    from portal.platform.inference.cluster_backends import BackendRegistry
    from portal.platform.inference.model_cards import card_entry

    hint = "Inkling-2-Mini-abliterated-oQ4e-mtp"
    gguf = "portal5/orcarouter-inkling-2-mini-abliterated:mix16g-ctx32k"
    huihui = "hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:q4_K_M-ctx32k"
    portal = yaml.safe_load((REPO / "config" / "portal.yaml").read_text())
    seat = portal["workspaces"]["auto-general-uncensored"]
    assert seat["model_hint"] == hint
    assert seat["reasoning_effort"] == "low"
    assert seat["context_limit"] == 262144
    assert seat["predict_limit"] == 32768
    assert (seat["temperature"], seat["top_p"]) == (1.0, 0.95)
    assert seat["emits_reasoning"] is True
    assert "think" not in seat
    assert not {
        "top_k",
        "min_p",
        "presence_penalty",
        "repeat_penalty",
        "think_profiles",
    }.intersection(seat)
    assert seat["tools"] == [
        "execute_bash",
        "execute_python",
        "read_word_document",
        "read_pdf",
        "remember",
        "recall",
    ]
    assert "CBRN" in seat["system_prompt_append"]
    assert hint in seat["description"] and gguf in seat["description"]
    assert card_entry(hint)[0] == "inkling-2-mini"
    variants = {
        "throwaway": "portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k",
        "throwaway-gemma4-heretic": "portal5/gemma4-26b-heretic:q4_K_M-ctx256k",
        "throwaway-ornith15": "portal5/ornith15-35b:q4_K_M-ctx256k",
        "creative": "fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx24k",
    }
    assert {name: cfg["model_hint"] for name, cfg in seat["variants"].items()} == variants
    assert all(cfg.get("emits_reasoning") is False for cfg in seat["variants"].values())
    assert all(cfg.get("think") is False for cfg in seat["variants"].values())
    backends = yaml.safe_load((REPO / "config" / "backends.yaml").read_text())
    by_id = {backend["id"]: backend for backend in backends["backends"]}
    assert huihui in {model["id"] for model in by_id["ollama-general"]["models"]}
    assert by_id["ollama-general"]["aliases"][hint] == gguf
    assert backends["workspace_routing"]["auto-general-uncensored"] == ["general"]
    registry = BackendRegistry(str(REPO / "config" / "backends.yaml"))
    resolved = {backend.id: backend for backend in registry.list_backends()}
    assert resolved["omlx-general"].resolve_model(hint) == hint
    assert resolved["ollama-general"].resolve_model(hint) == gguf
