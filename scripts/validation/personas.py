"""Persona-family checks: module tags on workspaces/MCP/personas, prompt
uniqueness, the retired-alias ratchet, and served-model integrity gates."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ._shared import REPO_ROOT
from .registry import register


@register("workspace_module_tag", "AP. workspace module tag", order=40)
def check_workspace_module_tag() -> tuple[str, str, list[dict]]:
    """AP. Every workspace in config/portal.yaml carries a module: tag (hard-fail)."""
    import yaml

    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    workspaces = cfg.get("workspaces", {}) or {}
    untagged = sorted(k for k, v in workspaces.items() if not v.get("module"))
    tagged = len(workspaces) - len(untagged)
    detail = f"{tagged}/{len(workspaces)} workspaces tagged"
    if untagged:
        return (
            "FAIL",
            f"{detail} — untagged: {untagged[:5]}{'...' if len(untagged) > 5 else ''}",
            [],
        )
    return ("PASS", detail, [])


@register("mcp_module_tag", "AQ. mcp module tag", order=41)
def check_mcp_module_tag() -> tuple[str, str, list[dict]]:
    """AQ. Every mcp_fleet entry in config/portal.yaml carries a module: tag (hard-fail)."""
    import yaml

    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    mcp_fleet = cfg.get("mcp_fleet", []) or []
    untagged = sorted(m["id"] for m in mcp_fleet if not m.get("module"))
    tagged = len(mcp_fleet) - len(untagged)
    detail = f"{tagged}/{len(mcp_fleet)} mcp_fleet entries tagged"
    if untagged:
        return ("FAIL", f"{detail} — untagged: {untagged}", [])
    return ("PASS", detail, [])


@register("persona_module_tag", "AR. persona module tag", order=42)
def check_persona_module_tag() -> tuple[str, str, list[dict]]:
    """AR. Every persona YAML carries a module: tag (hard-fail)."""
    import glob

    import yaml

    persona_dir = REPO_ROOT / "config" / "personas"
    files = sorted(glob.glob(str(persona_dir / "*.yaml")))
    untagged = []
    for f in files:
        d = yaml.safe_load(open(f)) or {}  # noqa: SIM115
        if not d.get("module"):
            untagged.append(Path(f).name)
    tagged = len(files) - len(untagged)
    detail = f"{tagged}/{len(files)} personas tagged"
    if untagged:
        return (
            "FAIL",
            f"{detail} — untagged: {untagged[:5]}{'...' if len(untagged) > 5 else ''}",
            [],
        )
    return ("PASS", detail, [])


@register("persona_prompt_uniqueness", "AS. persona prompt uniqueness", order=43)
def check_persona_prompt_uniqueness() -> tuple[str, str, list[dict]]:
    """AS. No two personas share a byte-identical system_prompt.

    Personas using `prompt_template:` are excluded from the hash comparison —
    a shared template referenced by many personas is the fix, not a new
    collision.
    """
    import glob
    import hashlib
    from collections import defaultdict

    import yaml

    persona_dir = REPO_ROOT / "config" / "personas"
    by_hash: dict[str, list[str]] = defaultdict(list)
    for f in sorted(glob.glob(str(persona_dir / "*.yaml"))):
        d = yaml.safe_load(open(f)) or {}  # noqa: SIM115
        if d.get("prompt_template"):
            continue
        sp = (d.get("system_prompt") or "").strip()
        if not sp:
            continue
        h = hashlib.md5(sp.encode()).hexdigest()  # noqa: S324
        by_hash[h].append(d.get("slug", Path(f).name))
    dups = {h: slugs for h, slugs in by_hash.items() if len(slugs) > 1}
    if dups:
        sample = next(iter(dups.values()))
        return (
            "FAIL",
            f"{len(dups)} duplicate-prompt group(s), e.g. {sample[:3]}{'...' if len(sample) > 3 else ''}",
            [],
        )
    return ("PASS", "no duplicate persona prompts", [])


@register("alias_ratchet", "AT. alias ratchet", order=44)
def check_alias_ratchet() -> tuple[str, str, list[dict]]:
    """AT. Zero live-code references to a retired pre-collapse workspace alias.

    Hard assertion: zero non-comment occurrences of any of the 23 retired
    alias ids (`scripts/alias_census.py`'s `_RETIRED_ALIAS_IDS`) in live
    Python serving-path code (shim/integration/personas categories — where a
    bare alias id would be a real regression: a default argument, a dict
    value sent as `model=`, etc.).

    Deliberately *not* a zero-occurrence-anywhere-in-the-repo assertion:
    `docs/`, `tests/`, `config/`'s narrative JSON/YAML legitimately reference
    retired ids by name when explaining collapse/retirement history (the
    "explanatory comment" content the closeout's own exemption design
    anticipated, ~700 refs across the doc/test corpus). `scripts/alias_census.py`'s
    comment/docstring-aware classifier is what makes the code-vs-narrative
    distinction precise instead of guessing.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from alias_census import run_census

    result = run_census()
    code_hits = result["code_hits_by_file"]

    if code_hits:
        return (
            "FAIL",
            f"{result['code_risk_total']} live alias reference(s) in "
            f"serving-path code: {code_hits}",
            [],
        )
    return (
        "PASS",
        f"0 live-code alias references ({result['total']} total refs across "
        f"docs/tests/config narrative, {result['frozen_total']} in frozen artifacts)",
        [],
    )


@register("routing_regression", "AU. routing regression (served model)", order=45)
def check_routing_regression() -> tuple[str, str, list[dict]]:
    """AU. Routing decisions match the versioned baseline (served model, not just id).

    Runs the committed corpus (tests/routing/corpus.json) through the current
    keyword-layer router and asserts the full (base, variant, served_model)
    tuple per prompt against tests/routing/baseline.json — a workspace-id-only
    check is insufficient (right workspace, wrong served model). Hard fail on
    any drift. Intended routing changes must be re-blessed explicitly
    (`scripts/routing_regression.py --rebless`) with the diff recorded in the
    commit — never silently accepted here.
    """
    # Earlier checks in this same process may import portal.platform.inference
    # and set PROMETHEUS_MULTIPROC_DIR (see metrics.py's own docstring) to a
    # directory that only exists once the pipeline's own startup has created it.
    # This subprocess doesn't need multiprocess metrics — routing_regression.py
    # only imports routing.py for its pure keyword-scoring function — so drop
    # the inherited var rather than risk a FileNotFoundError from a stale/
    # nonexistent multiprocess dir polluting an unrelated check.
    child_env = {k: v for k, v in os.environ.items() if k != "PROMETHEUS_MULTIPROC_DIR"}
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "routing_regression.py"), "--assert-baseline"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=child_env,
    )
    if result.returncode != 0:
        return (
            "FAIL",
            (result.stdout.strip() + "\n" + result.stderr.strip()).strip()[-800:],
            [],
        )
    return ("PASS", result.stdout.strip(), [])


@register("persona_intent", "AV. persona intent (identity vs served model)", order=46)
def check_persona_intent() -> tuple[str, str, list[dict]]:
    """AV. A persona's system_prompt identity claim matches its served model.

    Catches the bug class "right workspace, wrong served model" — a persona
    named/prompted for a specific model lineage (e.g. "powered by Magistral")
    but actually served a different model via its workspace's pool primary or
    a stale model_pin. Also checks module/workspace discipline agreement and
    that every model_pin is a real backends.yaml catalog id.
    """
    # Same PROMETHEUS_MULTIPROC_DIR pollution as check_routing_regression
    # (see its comment) — this subprocess transitively imports preinject.py
    # -> metrics.py and doesn't need multiprocess metrics either.
    child_env = {k: v for k, v in os.environ.items() if k != "PROMETHEUS_MULTIPROC_DIR"}
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "persona_intent_audit.py"), "--verbose"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=child_env,
    )
    if result.returncode != 0:
        return ("FAIL", (result.stdout.strip() + "\n" + result.stderr.strip()).strip()[-800:], [])
    return ("PASS", result.stdout.strip() or "0 hard failures", [])


# Pre-existing eval/bench-* workspaces that predate this check (landed before
# TASK-BENCH-FOLLOWUP-001 Part 3) and carry a baked -ctxNk tag with no
# recorded working-ctx probe. Grandfathered so this check doesn't retroactively
# fail unrelated workspaces; new/edited eval workspaces get no such pass —
# they must carry ctx_validated: true. Shrink this set as each is verified.
_CTX_HYGIENE_GRANDFATHERED = {
    "bench-granite41-8b",
    "bench-granite41-30b",
}


@register("eval_workspace_config_hygiene", "BW. eval-workspace config hygiene", order=72)
def check_eval_workspace_config_hygiene() -> tuple[str, str, list[dict]]:
    """BW. eval/bench-* workspaces don't repeat the Deepwen CAD config churn.

    Two footguns cost three benching passes (TASK-BENCH-FOLLOWUP-001):
      1. P5-OLLAMA-OPTIONS-001 — context_limit: is silently dropped by Ollama's
         /v1 endpoint; ctx must be baked into the model tag (-ctxNk).
      2. tool_choice: required inherited from a cloned workspace without being
         re-verified for the new model's architecture (auto-cad -> Deepwen).

    Does NOT enforce a uniform ctx across a lane — a baked -ctxNk tag is only
    accepted if the workspace also carries `ctx_validated: true`, proving a
    working-ctx preflight was actually run for *this* model rather than
    copied from whatever workspace it was cloned from. Same pattern for
    `tool_choice: required`, gated on `tool_choice_verified: true`.
    """
    import re

    import yaml

    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    workspaces = cfg.get("workspaces", {}) or {}
    ctx_suffix_re = re.compile(r"-ctx\d+k?$", re.IGNORECASE)

    dropped_context_limit: list[str] = []
    unvalidated_ctx: list[str] = []
    unverified_tool_choice: list[str] = []
    checked = 0

    for ws_id, ws in workspaces.items():
        if not isinstance(ws, dict):
            continue
        is_eval_lane = ws.get("module") == "eval" or ws_id.startswith("bench-")
        if not is_eval_lane:
            continue
        checked += 1
        model_hint = ws.get("model_hint", "") or ""
        has_baked_ctx = bool(ctx_suffix_re.search(model_hint))

        if "context_limit" in ws and not has_baked_ctx:
            dropped_context_limit.append(ws_id)

        if has_baked_ctx and not ws.get("ctx_validated"):
            if ws_id not in _CTX_HYGIENE_GRANDFATHERED:
                unvalidated_ctx.append(ws_id)

        if ws.get("tool_choice") == "required" and not ws.get("tool_choice_verified"):
            unverified_tool_choice.append(ws_id)

    detail = f"{checked} eval/bench-* workspaces checked"
    problems = []
    if dropped_context_limit:
        problems.append(
            f"context_limit set without baked -ctxNk tag (silently dropped, "
            f"P5-OLLAMA-OPTIONS-001): {sorted(dropped_context_limit)}"
        )
    if unvalidated_ctx:
        problems.append(
            f"baked ctx tag missing ctx_validated:true (working-ctx preflight not "
            f"recorded, may be copied from a cloned workspace): {sorted(unvalidated_ctx)}"
        )
    if unverified_tool_choice:
        problems.append(
            f"tool_choice: required missing tool_choice_verified:true (may be "
            f"inherited from a cloned workspace, doesn't transfer across model "
            f"architectures): {sorted(unverified_tool_choice)}"
        )
    if problems:
        return ("FAIL", f"{detail} — " + "; ".join(problems), [])
    return ("PASS", detail, [])
