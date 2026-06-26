"""Section wrapper functions and orchestration for Portal 5 acceptance tests."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.resolve()


async def S0() -> None:
    """S0: Prerequisites and environment check — delegates to s00_startup.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s00_startup as _s

    await _s.run()


async def S1() -> None:
    """S1: Configuration consistency — delegates to s01_static_config.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s01_static_config as _s

    await _s.run()


async def S2() -> None:
    """S2: Service health checks — delegates to s02_services.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s02_services as _s

    await _s.run()


async def S3a() -> None:
    """S3a: Workspace routing (Ollama) — delegates to s03_routing.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s03_routing as _s

    await _s.run()


async def S3() -> None:
    """S3: Workspace routing tests (runs S3a). S3b (MLX) retired in 3a0c58e."""
    await S3a()


async def S4() -> None:
    """S4: Document generation — delegates to s04_documents.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s04_documents as _s

    await _s.run()


async def S5() -> None:
    """S5: Code sandbox — delegates to s05_health.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s05_health as _s

    await _s.run()


async def S6() -> None:
    """S6: Security workspace tests — delegates to s06_security_workspaces.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s06_security_workspaces as _s

    await _s.run()


async def S7() -> None:
    """S7: Music generation tests — delegates to s07_music.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s07_music as _s

    await _s.run()


async def S8() -> None:
    """S8: TTS tests — delegates to s08_tts.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s08_tts as _s

    await _s.run()


async def S9() -> None:
    """S9: STT tests — delegates to s09_stt.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s09_stt as _s

    await _s.run()


async def S10() -> None:
    """S10: Persona tests (Ollama) — delegates to s10_personas_ollama.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s10_personas_ollama as _s

    await _s.run()


async def S10c() -> None:
    """S10c: Compliance personas — delegates to s10c_compliance_personas.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s10c_compliance_personas as _s

    await _s.run()


async def S12() -> None:
    """S12: Web search tests — delegates to s12_web_search.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s12_web_search as _s

    await _s.run()


async def S13() -> None:
    """S13: RAG/Embedding tests — delegates to s13_rag_embedding.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s13_rag_embedding as _s

    await _s.run()


async def S15() -> None:
    """S15: Shared workspace verification — delegates to s15_shared_workspace.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s15_shared_workspace as _s

    await _s.run()


async def S16() -> None:
    """S16: Security MCP tools — delegates to s16_security_mcp.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s16_security_mcp as _s

    await _s.run()


async def S17() -> None:
    """S17: CAD render MCP tests — delegates to s17_cad_render.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s17_cad_render as _s

    await _s.run()


async def S18() -> None:
    """S18: Lab-exec lane — live AD attack chain (skips if SANDBOX_LAB_EXEC not set)."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s18_lab_exec as _s

    await _s.run()


async def S21() -> None:
    """S21: LLM Intent Router — delegates to s21_llm_router.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s21_llm_router as _s

    await _s.run()


async def S23() -> None:
    """S23: Model diversity — delegates to s23_model_diversity.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s23_model_diversity as _s

    await _s.run()


async def S30() -> None:
    """S30: Image generation — delegates to s30_image_video.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s30_image_video as _s

    await _s.run()


async def S31() -> None:
    """S31: Video generation — delegates to s31_video_gen.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s31_video_gen as _s

    await _s.run()


async def S40() -> None:
    """S40: Metrics and monitoring — delegates to s40_metrics.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s40_metrics as _s

    await _s.run()


async def S41() -> None:
    """S41: M6 production hardening — delegates to s41_production_hardening.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s41_production_hardening as _s

    await _s.run()


async def S42() -> None:
    """S42: Browser automation — delegates to s42_browser_automation.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s42_browser_automation as _s

    await _s.run()


async def S50() -> None:
    """S50: Negative tests — delegates to s50_negative.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s50_negative as _s50

    await _s50.run()


async def S60() -> None:
    """S60: Tool-calling orchestration — delegates to s60_tool_calling.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s60_tool_calling as _s

    await _s.run()


async def S70() -> None:
    """S70: Information access MCPs — delegates to s70_information_access.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from acceptance import s70_information_access as _s

    await _s.run()


ALL_SECTIONS: dict[str, object] = {
    # Phase 1: No-model tests
    "S0": S0,
    "S1": S1,
    "S2": S2,
    "S12": S12,
    "S13": S13,
    "S15": S15,
    "S40": S40,
    "S50": S50,
    # Phase 2: Ollama tests
    "S3a": S3a,
    "S6": S6,
    "S16": S16,
    "S10": S10,
    "S10c": S10c,
    # Phase 3: router + diversity (Ollama)
    "S21": S21,
    "S23": S23,
    # Phase 4: MCP tests
    "S4": S4,
    "S5": S5,
    "S17": S17,
    "S18": S18,
    # Phase 5: Audio tests
    "S8": S8,
    "S9": S9,
    "S7": S7,
    # Phase 6: ComfyUI tests (LAST - huge memory)
    "S30": S30,
    "S31": S31,
    # Phase 7: M5/M6 features
    "S41": S41,
    "S42": S42,
    # Phase 8: M2/M3 tool-calling and information access
    "S60": S60,
    "S70": S70,
    # Legacy S3 wrapper
    "S3": S3,
}


def _parse_sections(spec: str) -> list[str]:
    """Parse section specification (e.g., 'S3', 'S3,S10', 'S3-S11', 'S3a', 'S3b')."""
    if not spec or spec.upper() == "ALL":
        return list(ALL_SECTIONS.keys())

    _upper_map = {k.upper(): k for k in ALL_SECTIONS}

    def _resolve(part: str) -> str | None:
        if not part.startswith("S") and not part.startswith("s"):
            part = f"S{part}"
        return _upper_map.get(part.upper())

    sections = []
    for part in spec.split(","):
        part = part.strip()
        upper = part.upper()
        if "-" in upper and not upper.startswith("S"):
            start, end = upper.split("-")
            for i in range(int(start), int(end) + 1):
                key = _resolve(str(i))
                if key:
                    sections.append(key)
        elif "-" in upper:
            start, end = upper.split("-")
            start_num = int(start[1:])
            end_num = int(end[1:])
            for i in range(start_num, end_num + 1):
                key = _resolve(str(i))
                if key:
                    sections.append(key)
        else:
            key = _resolve(part)
            if key:
                sections.append(key)

    return list(dict.fromkeys(sections))  # Remove duplicates, preserve order


async def run_sections(sections: list[str], verbose: bool = False) -> tuple[list[str], int]:
    """Run the given sections in order. Returns (sections_run, elapsed_seconds)."""
    import time

    from . import _common
    from .results import record

    phase_transitions = {
        "S10": "Personas → Audio/MCP",
        "S7": "Audio → ComfyUI",
    }
    running_full_suite = len(sections) > 10

    start_time = time.time()

    try:
        for sec in sections:
            if sec in ALL_SECTIONS:
                try:
                    await ALL_SECTIONS[sec]()
                except Exception as e:
                    record(sec, f"{sec}-ERR", "Section error", "FAIL", str(e)[:200])

                if running_full_suite and sec in phase_transitions:
                    await _common._memory_cleanup(phase_transitions[sec])
                else:
                    await asyncio.sleep(2)
    finally:
        if _common._acc_client and not _common._acc_client.is_closed:
            await _common._acc_client.aclose()

    elapsed = int(time.time() - start_time)
    return sections, elapsed
