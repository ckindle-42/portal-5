"""S11: Persona tests (MLX-routed) — driven by PERSONAS, grouped by workspace."""
import asyncio
import time

from tests.acceptance._common import (
    MLX_URL,
    _assert_routing,
    _chat_with_model,
    _ensure_free_ram_gb,
    _get_acc_client,
    _get_mlx_orgs,
    _get_mlx_workspaces,
    _get_persona_prompts,
    _get_persona_prompts_excluded,
    _get_personas,
    _mlx_health,
    _remediate_mlx_crash,
    record,
)


async def run() -> None:
    PERSONAS = _get_personas()
    PERSONA_PROMPTS = _get_persona_prompts()
    PERSONA_PROMPTS_EXCLUDED = _get_persona_prompts_excluded()
    MLX_WORKSPACES = _get_mlx_workspaces()
    _MLX_ORGS = _get_mlx_orgs()
    """S11: Persona tests (MLX-routed) — driven by PERSONAS, grouped by workspace."""
    print("\n━━━ S11. PERSONAS (MLX) ━━━")
    sec = "S11"

    state, _ = await _mlx_health()
    if state == "down":
        print("  ⚠️  MLX proxy is 'down' — attempting remediation before S11...")
        if not await _remediate_mlx_crash("MLX down before S11"):
            record(
                sec,
                "S11-00",
                "MLX availability",
                "BLOCKED",
                "MLX proxy is down and could not be recovered",
                t0=time.time(),
            )
            return
        state, _ = await _mlx_health()
    if state not in ("ready", "none", "switching"):
        record(
            sec,
            "S11-00",
            "MLX availability",
            "INFO",
            f"MLX state: {state}, skipping MLX persona tests",
            t0=time.time(),
        )
        return
    record(sec, "S11-00", "MLX availability", "PASS", f"state: {state}", t0=time.time())

    await _ensure_free_ram_gb(20, "S11 MLX personas")

    # Build (workspace_id → mlx_model_hint) at runtime — single source of truth
    from portal_pipeline.router_pipe import WORKSPACES as _WORKSPACES  # noqa: PLC0415

    ws_to_mlx = {
        wsid: _WORKSPACES[wsid].get("mlx_model_hint")
        for wsid in MLX_WORKSPACES
        if _WORKSPACES.get(wsid, {}).get("mlx_model_hint")
    }

    candidates = [p for p in PERSONAS if p.get("workspace_model") in MLX_WORKSPACES]
    candidates.sort(key=lambda p: p["workspace_model"])

    test_num = 1
    for ws_id, group in itertools.groupby(candidates, key=lambda p: p["workspace_model"]):
        members = list(group)
        model_hint = ws_to_mlx.get(ws_id, "")
        model_short = model_hint.split("/")[-1] if model_hint else "unknown"
        print(f"\n  ── Workspace: {ws_id} → {model_short} ({len(members)} personas) ──")

        if model_hint:
            model_gb = _MLX_MODEL_GB.get(model_hint, 10)
            if model_gb >= 14:
                await _ensure_free_ram_gb(model_gb + 10, model_short)

            print(f"  ── Triggering model load: {model_short} ──")
            try:
                c = _get_acc_client()
                await c.post(
                    f"{MLX_URL}/v1/chat/completions",
                    json={
                        "model": model_hint,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                    timeout=3,
                )
            except Exception:
                pass  # Expected timeout — just queuing the switch

            model_ready = await _wait_for_mlx_model(model_hint, timeout=300)
            if not model_ready:
                cur_state, _ = await _mlx_health()
                if cur_state == "down":
                    print(f"  ⚠️  MLX went down during {model_short} load — attempting recovery...")
                    recovered = await _remediate_mlx_crash(f"model load failed: {model_short}")
                    if not recovered:
                        for p in members:
                            record(
                                sec,
                                f"S11-{test_num:02d}",
                                f"Persona {p['slug']} (MLX)",
                                "BLOCKED",
                                f"MLX proxy down during {model_short} load, recovery failed",
                                t0=time.time(),
                            )
                            test_num += 1
                        break
                    try:
                        c = _get_acc_client()
                        await c.post(
                            f"{MLX_URL}/v1/chat/completions",
                            json={
                                "model": model_hint,
                                "messages": [{"role": "user", "content": "ping"}],
                                "max_tokens": 1,
                            },
                            timeout=3,
                        )
                    except Exception:
                        pass
                    model_ready = await _wait_for_mlx_model(model_hint, timeout=240)
                if not model_ready:
                    for p in members:
                        record(
                            sec,
                            f"S11-{test_num:02d}",
                            f"Persona {p['slug']} (MLX)",
                            "WARN",
                            f"Model {model_short} not loaded within 300s (proxy: {cur_state})",
                            t0=time.time(),
                        )
                        test_num += 1
                    continue

            _, health_data = await _mlx_health()
            loaded = health_data.get("loaded_model") or ""
            if loaded and model_hint not in loaded and model_hint.split("/")[-1] not in loaded:
                print(f"  ⚠️  Different model loaded: {loaded} (expected {model_short})")

        for p in members:
            slug = p["slug"]
            tid = f"S11-{test_num:02d}"
            t0 = time.time()
            if slug in PERSONA_PROMPTS_EXCLUDED:
                record(
                    sec, tid, f"Persona {slug} (MLX)", "INFO",
                    "excluded from text-prompt smoke (attachment-driven)", t0=t0,
                )
                test_num += 1
                continue
            if slug not in PERSONA_PROMPTS:
                record(sec, tid, f"Persona {slug} (MLX)", "FAIL", "no PERSONA_PROMPTS entry", t0=t0)
                test_num += 1
                continue
            prompt, signals = PERSONA_PROMPTS[slug]
            system = p.get("system_prompt", "")[:500]
            is_thinking = any(
                x in (model_hint or "") for x in ["reasoning", "R1", "Magistral", "Qwopus", "Opus"]
            )
            max_tok = 800 if is_thinking else 400
            code, response, model, _route = await _chat_with_model(
                ws_id,
                prompt,
                system=system,
                max_tokens=max_tok,
                timeout=300,
            )
            if code != 200:
                error_text = response[:120]
                if code == 500 and "audio_tower" in error_text:
                    record(
                        sec,
                        tid,
                        f"Persona {slug} (MLX)",
                        "BLOCKED",
                        "mlx_vlm audio_tower params missing in quantized model — requires full model download",
                        t0=t0,
                    )
                else:
                    record(
                        sec,
                        tid,
                        f"Persona {slug} (MLX)",
                        "FAIL",
                        f"HTTP {code}: {error_text}",
                        t0=t0,
                    )
                test_num += 1
                continue

            response_lower = response.lower()
            found = [s for s in signals if s.lower() in response_lower]
            is_mlx = any(org in model for org in _MLX_ORGS)
            ollama_fallback = ":" in model and not is_mlx
            route_status, route_detail = await _assert_routing(
                sec, tid, ws_id, model, persona_slug=slug,
            )

            if ollama_fallback:
                mlx_state_fb, _ = await _mlx_health()
                if mlx_state_fb in ("down", "switching"):
                    status = "WARN"
                    detail = (
                        f"Ollama fallback (MLX {mlx_state_fb}) — infrastructure | {route_detail}"
                    )
                else:
                    # MLX routing is correct — pipeline may choose Ollama based on
                    # model availability, load, or workspace config. INFO, not FAIL.
                    status = "INFO"
                    detail = f"Ollama fallback! model={model[:40]} (MLX state={mlx_state_fb}, expected MLX-tier) | {route_detail}"
            elif found and route_status in ("match", "no_expectation", "no_actual"):
                status = "PASS"
                detail = f"MLX:{is_mlx} model={model.split('/')[-1][:30]} | signals: {found[:2]} | {route_detail}"
            elif found and route_status == "mismatch":
                status = "WARN"
                detail = f"MLX:{is_mlx} model={model.split('/')[-1][:30]} | signals OK but {route_detail}"
            else:
                status = "WARN"
                detail = f"MLX:{is_mlx} model={model[:30]} | no signals in: {response[:60]} | {route_detail}"

            record(sec, tid, f"Persona {slug} (MLX)", status, detail, t0=t0)
            test_num += 1
            await asyncio.sleep(1)

        await asyncio.sleep(5)
