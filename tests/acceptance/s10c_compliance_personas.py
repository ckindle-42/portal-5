"""S10c: Compliance persona tests — fixture-driven via auto-compliance."""
import asyncio
import time

from tests.acceptance._common import (
    _chat_with_model,
    _get_personas,
    record,
)


async def run() -> None:
    PERSONAS = _get_personas()
    """S10c: Compliance persona tests — fixture-driven via auto-compliance.

    Drives every compliance persona through every applicable scenario from
    tests/fixtures/compliance_scenarios.yaml. Uses the behavioral assertions
    in tests/lib/compliance_assertions.py instead of signal-string matching.

    Pipeline-routed (workspace = "auto-compliance"). One model answers per
    request — whichever the chain picks. Per-(persona,model) exhaustion of
    the routing chain is in tests/portal5_persona_matrix.py (TASK 004).
    """
    print("\n━━━ S10c. PERSONAS (COMPLIANCE — FIXTURE) ━━━")
    sec = "S10c"

    try:
        from tests.lib.compliance_fixtures import expand_scenarios, run_assertions
    except ImportError as e:
        record(sec, "S10c-00", "fixture import", "BLOCKED", str(e)[:120],
               t0=time.time())
        return

    try:
        scenarios = expand_scenarios()
    except Exception as e:
        record(sec, "S10c-00", "fixture expansion", "FAIL", str(e)[:120],
               t0=time.time())
        return

    if not scenarios:
        record(sec, "S10c-00", "fixture expansion", "FAIL",
               "expand_scenarios() returned empty list",
               t0=time.time())
        return

    record(sec, "S10c-00", "fixture loaded", "PASS",
           f"{len(scenarios)} concrete scenarios across compliance personas",
           t0=time.time())

    # Group scenarios by persona for cleaner console output and to allow
    # per-persona settling time between batches (model context warmth).
    by_persona: dict[str, list] = {}
    for s in scenarios:
        by_persona.setdefault(s.persona_slug, []).append(s)

    test_num = 1
    for persona_slug in sorted(by_persona.keys()):
        persona_scenarios = by_persona[persona_slug]
        print(f"\n  ── Persona: {persona_slug} ({len(persona_scenarios)} scenarios) ──")

        # Find this persona's system prompt for context preloading
        persona_data = next(
            (p for p in PERSONAS if p.get("slug") == persona_slug), None
        )
        if not persona_data:
            record(sec, f"S10c-{test_num:02d}", f"persona {persona_slug}",
                   "BLOCKED", "persona YAML not loaded by acceptance_v6 PERSONAS",
                   t0=time.time())
            test_num += 1
            continue
        system = persona_data.get("system_prompt", "")[:8000]

        for scenario in persona_scenarios:
            tid = f"S10c-{test_num:03d}"
            t0 = time.time()
            label = f"{persona_slug}/{scenario.scenario_id}[{scenario.framework_id or 'any'}]"

            code, response, model, _route = await _chat_with_model(
                "auto-compliance",
                scenario.prompt,
                system=system,
                max_tokens=600,
                timeout=240,
            )

            if code != 200:
                record(sec, tid, label, "FAIL",
                       f"HTTP {code}: {response[:100]}", t0=t0)
                test_num += 1
                continue

            outcome = run_assertions(scenario, response)
            status = outcome.status  # PASS / WARN / FAIL

            # Compose detail summary
            failed = [r for r in outcome.results if not r.passed]
            if status == "PASS":
                detail = f"all {len(outcome.results)} assertions OK | model={model[:40]}"
            elif status == "WARN":
                names = ", ".join(r.name for r in failed[:3])
                detail = f"MUSTs OK; SHOULD failed: {names} | model={model[:40]}"
            else:
                names = ", ".join(r.name for r in failed[:3])
                detail = f"MUST failed: {names} | model={model[:40]}"

            record(sec, tid, label, status, detail, t0=t0)
            test_num += 1
            await asyncio.sleep(0.3)  # back off between requests

        await asyncio.sleep(2)  # back off between personas
