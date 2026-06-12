"""S10: Persona tests (Ollama-routed) — driven by PERSONAS, grouped by workspace."""
import asyncio
import itertools
import time

from tests.acceptance._common import (
    _assert_routing,
    _chat_with_model,
    _get_ollama_workspaces,
    _get_persona_prompts,
    _get_persona_prompts_excluded,
    _get_personas,
    record,
)


async def run() -> None:
    PERSONAS = _get_personas()
    PERSONA_PROMPTS = _get_persona_prompts()
    PERSONA_PROMPTS_EXCLUDED = _get_persona_prompts_excluded()
    OLLAMA_WORKSPACES = _get_ollama_workspaces()
    """S10: Persona tests (Ollama-routed) — driven by PERSONAS, grouped by workspace."""
    print("\n━━━ S10. PERSONAS (OLLAMA) ━━━")
    sec = "S10"

    # Compliance personas → S10c; benchmark personas → bench_tps; skip both here.
    candidates = [
        p for p in PERSONAS
        if p.get("workspace_model") in OLLAMA_WORKSPACES
        and p.get("category") not in ("compliance", "benchmark")
    ]
    candidates.sort(key=lambda p: p["workspace_model"])

    test_num = 1
    for ws_id, group in itertools.groupby(candidates, key=lambda p: p["workspace_model"]):
        members = list(group)
        print(f"\n  ── Workspace: {ws_id} ({len(members)} personas) ──")
        for p in members:
            slug = p["slug"]
            tid = f"S10-{test_num:02d}"
            t0 = time.time()
            if slug in PERSONA_PROMPTS_EXCLUDED:
                record(
                    sec, tid, f"Persona {slug}", "INFO",
                    "excluded from text-prompt smoke (attachment-driven)", t0=t0,
                )
                test_num += 1
                continue
            if slug not in PERSONA_PROMPTS:
                record(sec, tid, f"Persona {slug}", "FAIL", "no PERSONA_PROMPTS entry", t0=t0)
                test_num += 1
                continue
            prompt, signals = PERSONA_PROMPTS[slug]
            system = p.get("system_prompt", "")[:500]
            code, response, model, _route = await _chat_with_model(
                ws_id,
                prompt,
                system=system,
                max_tokens=250,
                timeout=180,
            )
            if code != 200:
                record(sec, tid, f"Persona {slug}", "FAIL", f"HTTP {code}", t0=t0)
                test_num += 1
                continue
            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]
            route_status, route_detail = await _assert_routing(
                sec, tid, ws_id, model, persona_slug=slug,
            )
            if found and route_status in ("match", "no_expectation", "no_actual"):
                status = "PASS"
            elif found and route_status == "mismatch":
                status = "WARN"
            else:
                status = "WARN"
            detail = (
                f"signals: {found[:3]} | {route_detail}"
                if found else f"no signals in: {response[:60]} | {route_detail}"
            )
            record(sec, tid, f"Persona {slug}", status, detail, t0=t0)
            test_num += 1
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)
