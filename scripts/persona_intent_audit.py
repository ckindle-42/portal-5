#!/usr/bin/env python3
"""Persona intent audit — DESIGN_PERSONA_INTENT_REMEDIATION_V1.md §7.

Catches the class of bug found in that design doc: a persona's
system_prompt claims a specific model lineage as its identity, but the
model actually served (workspace pool primary, or model_pin override)
doesn't match — the "right workspace, wrong served model" failure that a
workspace-id-only check can't see. That design's own 5 known cases
(magistralstrategist, devstral_coder, glm_coder/glm-coder, glm_thinker/
glm-thinking, phi4stemanalyst) are what this script would have caught at
collapse time, had it existed then.

Checks:
1. (hard) discipline(persona.module) == discipline(workspace_model's module)
2. (hard) system_prompt lineage claims match the actually-served model
   (model_pin if set, else workspace_model's model_hint)
3. (hard) model_pin, if set, is a real config/backends.yaml catalog id
4. (warn) preferred_models[0], if set alongside model_pin, doesn't name a
   contradicting lineage (preferred_models is dead metadata — §6 — so this
   is advisory, not authoritative; a mismatch means the dead field is lying
   about intent, not that anything is mis-served)
5. (hard) model_pin, if set, is reachable by the workspace's
   workspace_routing backend groups — catalog membership (check 3) is
   necessary but not sufficient; a pin can be a valid catalog id yet sit in
   a backend group the workspace never routes to, so the request silently
   falls back to the pool default instead of serving the pin
   (FINDINGS_MODEL_REACHABILITY.md — the phi4stemanalyst class of bug;
   catalog-membership-only checking is what let it through originally)

Usage:
    python3 scripts/persona_intent_audit.py
    python3 scripts/persona_intent_audit.py --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Lineage keyword -> canonical family name. Order matters: longer/more
# specific keys first so "magistral" (a Mistral sub-brand) is checked before
# the generic "mistral" would otherwise also match its own text.
_LINEAGE_KEYWORDS: list[tuple[str, str]] = [
    ("magistral", "mistral"),
    ("devstral", "mistral"),
    ("mistral", "mistral"),
    ("deepseek", "deepseek"),
    ("glm-z1", "glm"),
    ("glm", "glm"),
    ("phi-4", "phi4"),
    ("phi4", "phi4"),
    ("qwen", "qwen"),
    ("gemma", "gemma"),
    ("granite", "granite"),
    ("llama", "llama"),
    ("gpt-oss", "gpt-oss"),
    ("baronllm", "baronllm"),
    ("vulnllm", "vulnllm"),
    ("lfm", "lfm"),
    ("laguna", "laguna"),
]


def _lineage_of(text: str) -> str | None:
    """First lineage keyword found in (lowercased) text, or None."""
    low = text.lower()
    for kw, family in _LINEAGE_KEYWORDS:
        if kw in low:
            return family
    return None


def _claimed_lineage(system_prompt: str) -> str | None:
    """Scan system_prompt for an explicit "powered by X" / "using X model" /
    "X-lineage" identity claim — NOT a passing/contrast mention (e.g. "unlike
    Qwen or DeepSeek" does not count; only sentences asserting identity do).
    """
    low = system_prompt.lower()
    identity_patterns = [
        r"powered by ([a-z0-9.\- ]+)",
        r"using (?:the )?([a-z0-9.\- ]+?) model",
        r"you are (?:a|an) .*?powered by ([a-z0-9.\- ]+)",
    ]
    for pat in identity_patterns:
        m = re.search(pat, low)
        if m:
            lineage = _lineage_of(m.group(1))
            if lineage:
                return lineage
    return None


def _discipline_of_module(module: str) -> str:
    """Coarse discipline bucket a module belongs to — coding/reasoning/
    security/general modules already ARE the discipline; this exists so
    future module additions don't need a parallel mapping table."""
    return module


def _group_models() -> dict[str, set[str]]:
    """group name (e.g. "reasoning") -> set of model ids it declares."""
    import yaml

    from portal.platform.inference.cluster_backends import DEFAULT_CONFIG_PATH

    with open(DEFAULT_CONFIG_PATH) as fh:
        cfg = yaml.safe_load(fh.read())
    groups: dict[str, set[str]] = {}
    for be in cfg.get("backends", []):
        name = be.get("group") or (be.get("id") or be.get("name") or "").replace("ollama-", "")
        groups[name] = {m.get("id") if isinstance(m, dict) else m for m in be.get("models", [])}
    return groups


def _workspace_routing() -> dict[str, list[str]]:
    import yaml

    from portal.platform.inference.cluster_backends import DEFAULT_CONFIG_PATH

    with open(DEFAULT_CONFIG_PATH) as fh:
        cfg = yaml.safe_load(fh.read())
    return cfg.get("workspace_routing", {})


def audit() -> tuple[list[dict], list[dict]]:
    """Returns (hard_failures, warnings)."""

    from portal.platform.inference.config import load_persona_map, load_portal_config
    from portal.platform.inference.router.preinject import _known_backend_models

    portal_cfg = load_portal_config()
    workspaces = portal_cfg.workspaces
    personas = load_persona_map()

    known_models = _known_backend_models()
    group_models = _group_models()
    ws_routing = _workspace_routing()

    hard_failures: list[dict] = []
    warnings: list[dict] = []

    for slug, p in sorted(personas.items()):
        ws = workspaces.get(p.workspace_model)
        if ws is None:
            hard_failures.append(
                {
                    "check": 0,
                    "persona": slug,
                    "detail": f"workspace_model {p.workspace_model!r} does not exist",
                }
            )
            continue

        # Check 1: discipline(module) == discipline(workspace_model's module)
        persona_discipline = _discipline_of_module(p.module)
        ws_discipline = _discipline_of_module(ws.module)
        if persona_discipline != ws_discipline:
            hard_failures.append(
                {
                    "check": 1,
                    "persona": slug,
                    "detail": (
                        f"module={p.module!r} (discipline {persona_discipline!r}) "
                        f"but workspace_model={p.workspace_model!r} is module "
                        f"{ws.module!r} (discipline {ws_discipline!r})"
                    ),
                }
            )

        # Check 2: system_prompt lineage claim vs actually-served model
        claimed = _claimed_lineage(p.system_prompt)
        if claimed:
            served_model = p.model_pin or ws.model_hint
            served_lineage = _lineage_of(served_model or "")
            if served_lineage and served_lineage != claimed:
                hard_failures.append(
                    {
                        "check": 2,
                        "persona": slug,
                        "detail": (
                            f"system_prompt claims {claimed!r} lineage, but "
                            f"served model {served_model!r} is {served_lineage!r} "
                            f"lineage (model_pin={p.model_pin!r})"
                        ),
                    }
                )

        # Check 3: model_pin, if set, is a real catalog id
        if p.model_pin and p.model_pin not in known_models:
            hard_failures.append(
                {
                    "check": 3,
                    "persona": slug,
                    "detail": f"model_pin {p.model_pin!r} not in config/backends.yaml's catalog",
                }
            )

        # Check 5: model_pin, if set, is reachable by the workspace's
        # routing groups (not just a valid catalog id — check 3 catches
        # that; this catches the "valid id, wrong group" leak).
        if p.model_pin:
            groups = ws_routing.get(p.workspace_model, [])
            reachable = any(p.model_pin in group_models.get(g, ()) for g in groups)
            if not reachable:
                hard_failures.append(
                    {
                        "check": 5,
                        "persona": slug,
                        "detail": (
                            f"model_pin {p.model_pin!r} not reachable by "
                            f"workspace_model={p.workspace_model!r}'s routing "
                            f"groups {groups!r} — request silently falls back "
                            "to the pool default instead of serving the pin"
                        ),
                    }
                )

        # Check 4 (warn): preferred_models[0] contradicts model_pin's lineage
        if p.model_pin and p.preferred_models:
            pin_lineage = _lineage_of(p.model_pin)
            pref_lineage = _lineage_of(p.preferred_models[0])
            if pin_lineage and pref_lineage and pin_lineage != pref_lineage:
                warnings.append(
                    {
                        "check": 4,
                        "persona": slug,
                        "detail": (
                            f"preferred_models[0]={p.preferred_models[0]!r} "
                            f"({pref_lineage!r} lineage) contradicts authoritative "
                            f"model_pin={p.model_pin!r} ({pin_lineage!r} lineage) — "
                            "preferred_models is dead metadata (§6), remove it"
                        ),
                    }
                )

    return hard_failures, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    hard_failures, warnings = audit()

    for w in warnings:
        print(f"WARN  [check {w['check']}] {w['persona']}: {w['detail']}")
    for f in hard_failures:
        print(f"FAIL  [check {f['check']}] {f['persona']}: {f['detail']}")

    if args.verbose:
        print(f"\n{len(hard_failures)} hard failure(s), {len(warnings)} warning(s).")

    return 1 if hard_failures else 0


if __name__ == "__main__":
    sys.exit(main())
