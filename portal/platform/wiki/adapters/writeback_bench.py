"""Bench → wiki write-back — Phase P4.

Candidate-eval / multi-seat bench results write back as cited model-knowledge units.
"""

from __future__ import annotations


def writeback_bench_result(
    model: str,
    seat: str,
    verdict: str,
    delta: str = "",
    result_path: str = "",
    *,
    auto_confirm: bool = False,
) -> dict | None:
    """Write a bench result back to the wiki as a cited model-knowledge unit.

    Args:
        model: model name
        seat: which seat (exploit, blue-analyst, etc.)
        verdict: keep/promote/reject
        delta: performance delta vs incumbent
        result_path: path to the result JSON
        auto_confirm: if True, skip confirm gate

    Returns:
        proposed unit dict, or None on failure
    """
    from portal.platform.wiki.writeback import propose_unit

    sources = [{"type": "code", "path": result_path or f"bench:{model}/{seat}"}]

    try:
        pu = propose_unit(
            {
                "title": f"{model} — {seat} bench result ({verdict})",
                "kind": "what",
                "sources": sources,
                "body": (
                    f"# {model} — {seat} Bench Result\n\n"
                    f"**Model:** {model}\n\n"
                    f"**Seat:** {seat}\n\n"
                    f"**Verdict:** {verdict}\n\n"
                    f"**Delta:** {delta}\n\n"
                    f"**Result:** {result_path}\n"
                ),
                "tags": [model, seat, "bench", verdict],
            },
            proposed_by="bench",
            auto_confirm=auto_confirm,
        )
        return pu.to_dict()
    except Exception:
        return None
