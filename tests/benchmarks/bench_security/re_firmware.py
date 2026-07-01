"""RE / Firmware / Mobile / N-Day lane bench (Gap 1).

Firmware is the flagship: ICS/OT devices are firmware, and Portal began as an OT/ICS tool.
Scored on ground truth (emulated firmware target), not text patterns.
"""


def bench_firmware_extract(firmware_path: str, *, dry_run: bool = False) -> dict:
    """Run firmware extraction + analysis benchmark."""
    if dry_run:
        return {"status": "dry_run", "target": firmware_path, "phases": ["extract", "analyze", "emulate", "fuzz"]}
    return {"status": "placeholder", "reason": "firmware emulation target required"}


def bench_binary_re(binary_path: str, *, dry_run: bool = False) -> dict:
    """Binary RE: triage, disasm reasoning, vuln-spotting, ROP."""
    if dry_run:
        return {"status": "dry_run", "target": binary_path, "checks": ["triage", "disasm", "vuln_spot", "ROP"]}
    return {"status": "placeholder", "reason": "binary target required"}
