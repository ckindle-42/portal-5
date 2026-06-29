"""Section wrapper functions and orchestration for Portal 5 ComfyUI acceptance tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.resolve()


async def C0() -> None:
    """C0: Prerequisites — delegates to c00_prereqs.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c00_prereqs as _s

    await _s.run()


async def C1() -> None:
    """C1: ComfyUI direct API — delegates to c01_direct_api.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c01_direct_api as _s

    await _s.run()


async def C2() -> None:
    """C2: MCP bridge health — delegates to c02_mcp_health.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c02_mcp_health as _s

    await _s.run()


async def C3() -> None:
    """C3: Model discovery via MCP — delegates to c03_model_discovery.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c03_model_discovery as _s

    await _s.run()


async def C4() -> None:
    """C4: Image gen: FLUX schnell — delegates to c04_flux_schnell.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c04_flux_schnell as _s

    await _s.run()


async def C5() -> None:
    """C5: Image gen: FLUX dev — delegates to c05_flux_dev.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c05_flux_dev as _s

    await _s.run()


async def C6() -> None:
    """C6: Image gen: SDXL variants — delegates to c06_sdxl.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c06_sdxl as _s

    await _s.run()


async def C7() -> None:
    """C7: Image gen: parameter sweep — delegates to c07_param_sweep.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c07_param_sweep as _s

    await _s.run()


async def C8() -> None:
    """C8: Video gen: Wan2.2 T2V — delegates to c08_video_wan22.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c08_video_wan22 as _s

    await _s.run()


async def C9() -> None:
    """C9: Pipeline round-trips — delegates to c09_pipeline_roundtrip.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c09_pipeline_roundtrip as _s

    await _s.run()


async def C10() -> None:
    """C10: Output validation — delegates to c10_output_validation.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c10_output_validation as _s

    await _s.run()


async def C11() -> None:
    """C11: All-LoRA coverage — delegates to c11_lora_coverage.py."""
    sys.path.insert(0, str(ROOT / "tests"))
    from comfyui import c11_lora_coverage as _s

    await _s.run()


ALL_SECTIONS: dict[str, object] = {
    "C0": C0,
    "C1": C1,
    "C2": C2,
    "C3": C3,
    "C4": C4,
    "C5": C5,
    "C6": C6,
    "C7": C7,
    "C8": C8,
    "C9": C9,
    "C10": C10,
    "C11": C11,
}

ALL_ORDER = ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11"]


def _parse_sections(spec: str) -> list[str]:
    """Parse section specification (e.g., 'C4', 'C4,C5', 'C4-C8', 'ALL')."""
    import re

    if not spec or spec.upper() == "ALL":
        return list(ALL_ORDER)

    # Range: C4-C8
    if re.match(r"^C\d+-C\d+$", spec.upper()):
        start, end = spec.upper().split("-", 1)
        try:
            si = ALL_ORDER.index(start)
            ei = ALL_ORDER.index(end)
        except ValueError as e:
            sys.exit(f"Unknown section in range: {e}. Valid: {sorted(ALL_SECTIONS)}")
        if si > ei:
            si, ei = ei, si
        return ALL_ORDER[si : ei + 1]

    # Comma-separated
    requested = [s.strip().upper() for s in spec.split(",") if s.strip()]
    for sid in requested:
        if sid not in ALL_SECTIONS:
            sys.exit(f"Unknown section: {sid}. Valid: {sorted(ALL_SECTIONS)}")
    # Always prepend C0 (prereqs) unless it's the only or already included
    if requested and requested[0] != "C0" and "C0" not in requested:
        return ["C0"] + requested
    return requested


async def run_sections(sections: list[str], verbose: bool = False) -> tuple[list[str], int]:
    """Run the given sections in order. Returns (sections_run, elapsed_seconds)."""
    import time

    from ._common import record

    start_time = time.time()

    try:
        for sec in sections:
            if sec in ALL_SECTIONS:
                try:
                    await ALL_SECTIONS[sec]()
                except Exception as e:
                    record(sec, f"{sec}-ERR", "Section error", "FAIL", str(e)[:200])
                await asyncio.sleep(1)
    finally:
        pass

    elapsed = int(time.time() - start_time)
    return sections, elapsed
