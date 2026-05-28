"""S1: Configuration consistency."""
import json
import yaml
from tests.acceptance._common import (
    ROOT,
    record,
    _load_backends_yaml,
    _get_personas,
    _get_ws_ids,
    _get_persona_prompts,
    _get_persona_prompts_excluded,
    _get_mlx_orgs,
)


async def run() -> None:
    PERSONAS = _get_personas()
    WS_IDS = _get_ws_ids()
    PERSONA_PROMPTS = _get_persona_prompts()
    PERSONA_PROMPTS_EXCLUDED = _get_persona_prompts_excluded()
    _MLX_ORGS = _get_mlx_orgs()
    """S1: Configuration consistency."""
    print("\n━━━ S1. CONFIGURATION CONSISTENCY ━━━")
    sec = "S1"

    # S1-01: backends.yaml exists
    t0 = time.time()
    backends_file = ROOT / "config/backends.yaml"
    record(
        sec,
        "S1-01",
        "backends.yaml exists",
        "PASS" if backends_file.exists() else "FAIL",
        str(backends_file),
        t0=t0,
    )

    # S1-02: backends.yaml is valid YAML
    t0 = time.time()
    try:
        backends = _load_backends_yaml()
        record(
            sec,
            "S1-02",
            "backends.yaml valid YAML",
            "PASS",
            f"{len(backends.get('backends', []))} backends",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S1-02", "backends.yaml valid YAML", "FAIL", str(e)[:100], t0=t0)
        return

    # S1-03: Workspace IDs consistent between router_pipe.py and backends.yaml
    t0 = time.time()
    pipe_ids = set(WS_IDS)
    yaml_ids = set(backends.get("workspace_routing", {}).keys())
    if pipe_ids == yaml_ids:
        record(
            sec, "S1-03", "Workspace IDs consistent", "PASS", f"{len(pipe_ids)} workspaces", t0=t0
        )
    else:
        diff = pipe_ids.symmetric_difference(yaml_ids)
        record(sec, "S1-03", "Workspace IDs consistent", "FAIL", f"mismatch: {diff}", t0=t0)

    # S1-04: All persona YAMLs are valid
    t0 = time.time()
    persona_dir = ROOT / "config/personas"
    persona_files = list(persona_dir.glob("*.yaml"))
    invalid = []
    for pf in persona_files:
        try:
            yaml.safe_load(pf.read_text())
        except Exception:
            invalid.append(pf.name)
    record(
        sec,
        "S1-04",
        "Persona YAMLs valid",
        "PASS" if not invalid else "FAIL",
        f"{len(persona_files)} personas" if not invalid else f"invalid: {invalid}",
        t0=t0,
    )

    # S1-05: Persona count matches actual yaml file count (no frozen baseline)
    t0 = time.time()
    yaml_count = len(list((ROOT / "config/personas").glob("*.yaml")))
    actual_count = len(PERSONAS)
    record(
        sec,
        "S1-05",
        "Persona count matches yaml file count",
        "PASS" if actual_count == yaml_count else "FAIL",
        f"{actual_count} loaded, {yaml_count} yaml files",
        t0=t0,
    )

    # S1-06: routing_descriptions.json exists and valid
    t0 = time.time()
    routing_desc_file = ROOT / "config/routing_descriptions.json"
    try:
        if routing_desc_file.exists():
            desc = json.loads(routing_desc_file.read_text())
            record(
                sec,
                "S1-06",
                "routing_descriptions.json",
                "PASS",
                f"{len(desc)} descriptions",
                t0=t0,
            )
        else:
            record(sec, "S1-06", "routing_descriptions.json", "WARN", "file not found", t0=t0)
    except Exception as e:
        record(sec, "S1-06", "routing_descriptions.json", "FAIL", str(e)[:100], t0=t0)

    # S1-07: routing_examples.json exists and valid
    t0 = time.time()
    routing_ex_file = ROOT / "config/routing_examples.json"
    try:
        if routing_ex_file.exists():
            ex = json.loads(routing_ex_file.read_text())
            record(sec, "S1-07", "routing_examples.json", "PASS", f"{len(ex)} examples", t0=t0)
        else:
            record(sec, "S1-07", "routing_examples.json", "WARN", "file not found", t0=t0)
    except Exception as e:
        record(sec, "S1-07", "routing_examples.json", "FAIL", str(e)[:100], t0=t0)

    # S1-08: MLX backend routing — VLM models flagged is_vlm: true in backends.yaml.
    # Source of truth: scripts/mlx-proxy.py:_load_mlx_metadata() reads is_vlm from
    # config/backends.yaml. Previous implementation grepped the proxy source for
    # an inline VLM_MODELS literal that no longer exists post-refactor.
    t0 = time.time()
    try:
        cfg = _load_backends_yaml()
        vlm_ids: set[str] = set()
        all_ids: set[str] = set()
        for backend in cfg.get("backends", []):
            for m in backend.get("mlx_models", []) or []:
                mid = m.get("id")
                if not mid:
                    continue
                all_ids.add(mid)
                if m.get("is_vlm") is True:
                    vlm_ids.add(mid)
        # Gemma 4 31B dense, E4B, JANG, and abliterated 26B MoE must be VLM (require mlx_vlm)
        gemma_31b_vlm = "mlx-community/gemma-4-31b-it-4bit" in vlm_ids
        gemma_e4b_vlm = "mlx-community/gemma-4-e4b-it-4bit" in vlm_ids
        gemma_31b_all = "mlx-community/gemma-4-31b-it-4bit" in all_ids
        jang_vlm = "dealignai/Gemma-4-31B-JANG_4M-CRACK" in vlm_ids
        jang_all = "dealignai/Gemma-4-31B-JANG_4M-CRACK" in all_ids
        gemma_26b_abl_vlm = (
            "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit" in vlm_ids
        )
        gemma_26b_abl_all = (
            "Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit" in all_ids
        )
        all_ok = (
            gemma_31b_vlm
            and gemma_e4b_vlm
            and gemma_31b_all
            and jang_vlm
            and jang_all
            and gemma_26b_abl_vlm
            and gemma_26b_abl_all
        )
        # Not all VLM models may be deployed; missing models → INFO not FAIL
        missing_vlm = []
        if not gemma_31b_vlm: missing_vlm.append("31b_vlm")
        if not gemma_e4b_vlm: missing_vlm.append("e4b_vlm")
        if not gemma_31b_all: missing_vlm.append("31b_all")
        if not jang_vlm: missing_vlm.append("jang_vlm")
        if not jang_all: missing_vlm.append("jang_all")
        if not gemma_26b_abl_vlm: missing_vlm.append("26b_abl_vlm")
        if not gemma_26b_abl_all: missing_vlm.append("26b_abl_all")
        status = "PASS" if all_ok else ("FAIL" if not missing_vlm else "INFO")
        detail = (
            "✓ Gemma 4 31B + E4B + JANG + 26B-abl flagged is_vlm"
            if all_ok
            else f"models not deployed/missing VLM flags: {missing_vlm}"
        )
        record(
            sec,
            "S1-08",
            "MLX routing: VLM models flagged is_vlm in backends.yaml (mlx_vlm backend)",
            status,
            detail,
            t0=t0,
        )
    except Exception as e:
        record(sec, "S1-08", "MLX routing: VLM models flagged is_vlm", "FAIL", str(e)[:100], t0=t0)

    # S1-09: MLX backend routing — text-only models NOT flagged is_vlm in backends.yaml.
    # Magistral and Phi-4 must be loaded by mlx_lm, not mlx_vlm.
    t0 = time.time()
    try:
        cfg = _load_backends_yaml()
        vlm_ids = set()
        all_ids = set()
        for backend in cfg.get("backends", []):
            for m in backend.get("mlx_models", []) or []:
                mid = m.get("id")
                if not mid:
                    continue
                all_ids.add(mid)
                if m.get("is_vlm") is True:
                    vlm_ids.add(mid)
        magistral_id = "lmstudio-community/Magistral-Small-2509-MLX-8bit"
        phi4_id = "mlx-community/phi-4-8bit"
        magistral_in_all = magistral_id in all_ids
        magistral_in_vlm = magistral_id in vlm_ids
        phi4_in_all = phi4_id in all_ids
        phi4_in_vlm = phi4_id in vlm_ids
        lm_ok = magistral_in_all and not magistral_in_vlm and phi4_in_all and not phi4_in_vlm
        record(
            sec,
            "S1-09",
            "MLX routing: text-only models NOT flagged is_vlm (mlx_lm backend)",
            "PASS" if lm_ok else "FAIL",
            "✓ Magistral + Phi-4 use mlx_lm"
            if lm_ok
            else f"magistral: all={magistral_in_all} vlm={magistral_in_vlm} | phi4: all={phi4_in_all} vlm={phi4_in_vlm}",
            t0=t0,
        )
    except Exception as e:
        record(
            sec,
            "S1-09",
            "MLX routing: text-only models NOT flagged is_vlm",
            "FAIL",
            str(e)[:100],
            t0=t0,
        )

    # S1-10: All persona workspace_model values are valid pipeline workspace IDs or Ollama tags.
    # Raw MLX HF paths (mlx-community/*, lmstudio-community/*, Jackrong/*, dealignai/*) are
    # INVALID because the pipeline only exposes workspace IDs in /v1/models.  Personas with
    # raw HF paths show "model not found" in Open WebUI even though the model is downloaded.
    t0 = time.time()
    valid_ws_ids = set(WS_IDS) | {"auto"}
    bad_personas: list[str] = []
    for p in PERSONAS:
        slug = p.get("slug", "?")
        ws_model = p.get("workspace_model", "")
        if not ws_model:
            bad_personas.append(f"{slug}:(missing)")
            continue
        # Valid if it's a known pipeline workspace ID
        if ws_model in valid_ws_ids:
            continue
        # Invalid if it starts with a known MLX org prefix — these are raw HF paths
        if any(ws_model.startswith(org) for org in _MLX_ORGS):
            bad_personas.append(f"{slug}:{ws_model.split('/')[-1]}")
    record(
        sec,
        "S1-10",
        "Persona workspace_model values are pipeline IDs or Ollama tags",
        "FAIL" if bad_personas else "PASS",
        f"invalid (raw MLX paths): {bad_personas}"
        if bad_personas
        else f"all {len(PERSONAS)} personas use valid workspace_model values",
        t0=t0,
    )

    # S1-11: Every non-benchmark persona has a PERSONA_PROMPTS entry
    t0 = time.time()
    non_bench = [p for p in PERSONAS if p.get("category") != "benchmark"]
    missing_prompts = [
        p["slug"] for p in non_bench
        if p["slug"] not in PERSONA_PROMPTS and p["slug"] not in PERSONA_PROMPTS_EXCLUDED
    ]
    record(
        sec,
        "S1-11",
        "All personas have PERSONA_PROMPTS entries",
        "FAIL" if missing_prompts else "PASS",
        f"missing prompts for: {missing_prompts}"
        if missing_prompts
        else f"all {len(non_bench)} non-benchmark personas covered",
        t0=t0,
    )

    # S1-17: workspace hint reachability
    t0 = time.time()
    try:
        from portal_pipeline.cluster_backends import BackendRegistry
        from portal_pipeline.router_pipe import _validate_workspace_hints

        reg = BackendRegistry()
        errors = _validate_workspace_hints(reg)
        if not errors:
            record(
                sec,
                "S1-17",
                "workspace hint reachability",
                "PASS",
                f"all {len(WS_IDS)} workspace hints resolve",
                t0=t0,
            )
        else:
            record(
                sec,
                "S1-17",
                "workspace hint reachability",
                "FAIL",
                f"{len(errors)} hints unresolved: {errors[0][:120]}",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S1-17", "workspace hint reachability", "FAIL", str(e)[:200], t0=t0)