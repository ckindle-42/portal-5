"""S1: Configuration consistency."""

import json
import time

import yaml

from tests.acceptance._common import (
    ROOT,
    _get_persona_prompts,
    _get_persona_prompts_excluded,
    _get_personas,
    _get_ws_ids,
    _load_backends_yaml,
    record,
)


async def run() -> None:
    PERSONAS = _get_personas()
    WS_IDS = _get_ws_ids()
    PERSONA_PROMPTS = _get_persona_prompts()
    PERSONA_PROMPTS_EXCLUDED = _get_persona_prompts_excluded()
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

    # S1-08: MLX VLM routing — retired (MLX proxy deleted in 3a0c58e)
    t0 = time.time()
    record(
        sec,
        "S1-08",
        "MLX routing: VLM models (retired)",
        "INFO",
        "MLX proxy retired in 3a0c58e",
        t0=t0,
    )

    # S1-09: MLX text-only routing — retired (MLX proxy deleted in 3a0c58e)
    record(
        sec,
        "S1-09",
        "MLX routing: text-only models (retired)",
        "INFO",
        "MLX proxy retired in 3a0c58e",
        t0=t0,
    )

    # S1-10: All persona workspace_model values are valid pipeline workspace IDs or Ollama tags.
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
        bad_personas.append(f"{slug}:{ws_model.split('/')[-1]}")
    record(
        sec,
        "S1-10",
        "Persona workspace_model values are pipeline IDs or Ollama tags",
        "FAIL" if bad_personas else "PASS",
        f"invalid: {bad_personas}"
        if bad_personas
        else f"all {len(PERSONAS)} personas use valid workspace_model values",
        t0=t0,
    )

    # S1-11: Every non-benchmark persona has a PERSONA_PROMPTS entry
    t0 = time.time()
    non_bench = [p for p in PERSONAS if p.get("category") != "benchmark"]
    missing_prompts = [
        p["slug"]
        for p in non_bench
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
        import os, tempfile as _tf  # noqa: E401
        _prom = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "")
        if not _prom or not os.path.isdir(_prom):
            _mp = _tf.mkdtemp(prefix="portal5_acceptance_metrics_")
            os.environ["PROMETHEUS_MULTIPROC_DIR"] = _mp
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
