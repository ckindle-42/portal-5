"""Portal 5 UAT — slug->workspace mapping, routed-model validation.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase C). WORKSPACES/_PERSONA_MAP/expected_models are imported function-
locally by the original bodies (kept as-is, A5).
"""

from __future__ import annotations


def _map_slug_to_workspace(slug: str) -> str:
    """Resolve a persona slug to its workspace id, or return the slug
    if it's already a workspace id."""
    from expected_models import _PERSONA_MAP, WORKSPACES

    if slug in WORKSPACES:
        return slug
    p = _PERSONA_MAP.get(slug)
    if p is None:
        ws = ""
    elif isinstance(p, dict):
        ws = p.get("workspace_model") or p.get("workspace") or ""
    else:
        ws = getattr(p, "workspace_model", "") or getattr(p, "workspace", "") or ""
    return ws if ws in WORKSPACES else ""


def _get_backend_from_pipeline_logs(slug: str) -> str:
    """Query pipeline Docker logs for the most recent backend that actually
    served a request for the given workspace/persona slug.

    Uses the "Backend X succeeded" log line (only emitted on actual success)
    rather than the "Routing workspace=X → backend=Y" line (emitted for the
    first candidate ATTEMPTED, which may 503 and fall to a different backend).

    Log line patterns (pipeline emits both; we prefer the succeeded line):
      Backend ollama-general succeeded for workspace=auto-documents model=phi4:14b-q8_0
      Backend ollama-coding succeeded for workspace=auto-agentic model=qwen3-coder:30b
    """
    import re
    import subprocess

    # Resolve persona slug to its workspace for log matching
    ws = _map_slug_to_workspace(slug)

    try:
        result = subprocess.run(
            ["docker", "logs", "portal5-pipeline", "--tail", "300"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        combined = result.stdout + result.stderr  # docker logs may use either stream

        # PRIMARY: match "Backend X succeeded for workspace=Y model=Z"
        # This line is only emitted when a backend actually returns a response,
        # so it correctly reflects backend-group fallbacks that the
        # "Routing workspace" attempt line would hide.
        for search_term in (ws, slug):
            if not search_term:
                continue
            succeeded_pattern = re.compile(
                r"Backend\s+([^\s]+)\s+succeeded\s+for\s+workspace="
                + re.escape(search_term)
                + r"\s+model=([^\s]+)"
            )
            matches = succeeded_pattern.findall(combined)
            if matches:
                backend, model = matches[-1]  # most recent
                return f"{backend}|{model}"

        # FALLBACK: if no "succeeded" line found (e.g. non-stream path that
        # doesn't emit it), fall back to the attempt log line as before.
        for search_term in (ws, slug):
            if not search_term:
                continue
            pattern = re.compile(
                r"Routing workspace="
                + re.escape(search_term)
                + r".*?backend=([^\s]+)\s+model=([^\s]+)"
            )
            matches = pattern.findall(combined)
            if matches:
                backend, model = matches[-1]
                return f"{backend}|{model}"
    except Exception:
        pass
    return ""


def _check_routed_model(test: dict, routed_model: str) -> tuple[bool, str] | None:
    """Validate routed_model against test expectation.

    Two-source approach:
      1. OWUI chat metadata via owui_get_routed_model (may store the
         workspace/persona name, not the backend model)
      2. Pipeline Docker logs — extracts the actual backend=xxx model=yyy

    Returns:
        None             - no expectation defined for this test, skip the check
        (True,  detail)  - actual model matches expectation
        (False, detail)  - mismatch (caller should downgrade PASS to WARN)

    Resolution order:
        1. test['assert_routed_via']: list[str] of substrings
        2. test['model_slug'] in WORKSPACES
        3. test['model_slug'] in _PERSONA_MAP
        4. None — no expectation, skip
    """
    if test.get("via_dispatcher") or test.get("is_manual"):
        return None
    if not routed_model:
        return None

    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

    from expected_models import model_matches_expected, resolve_expected

    explicit = test.get("assert_routed_via")
    slug = test.get("model_slug", "")

    keys, src = resolve_expected(
        workspace_id=slug,
        persona_slug=slug,
    )
    if not keys:
        return None

    # 1st check: OWUI-stored model (may be the workspace/persona name)
    ok_owui = model_matches_expected(routed_model, keys)

    # 2nd check: pipeline logs (actual backend model)
    backend_model = _get_backend_from_pipeline_logs(slug)

    ok_pipeline = False
    pipeline_detail = ""
    if backend_model:
        ok_pipeline = model_matches_expected(backend_model, keys)
        pipeline_detail = f" (pipeline: {backend_model})"

    if explicit:
        ok = ok_owui or ok_pipeline
        return (
            ok,
            f"explicit expectation: {explicit}{pipeline_detail}"
            if ok
            else f"explicit expectation NOT matched: {explicit}{pipeline_detail}",
        )

    if ok_owui or ok_pipeline:
        detail = f"matches {src}"
        if backend_model:
            detail += f" — pipeline confirms: {backend_model}"
        return (True, detail)

    return (False, f"expected {src} (OWUI={routed_model}{pipeline_detail})")
