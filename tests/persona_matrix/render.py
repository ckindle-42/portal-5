"""Console and JSON rendering for persona-matrix output."""
from __future__ import annotations

from typing import Any


def render_matrix_table(report: dict[str, Any]) -> str:
    cells = report["cells"]
    if not cells:
        return "(no cells — dry run or empty plan)"

    personas = sorted({c["persona"] for c in cells})
    models = []
    seen: set[tuple[str, str]] = set()
    for c in cells:
        key = (c["backend"], c["model"])
        if key not in seen:
            seen.add(key)
            models.append((c["backend"], c["model"]))

    by_pm: dict[tuple[str, str, str], dict[str, int]] = {}
    for c in cells:
        by_pm[(c["persona"], c["backend"], c["model"])] = c["summary"]

    def short(model: str) -> str:
        return model.split("/")[-1][:24]

    persona_w = max(len(p) for p in personas) + 1
    lines = []
    header = " " * persona_w + " | " + " | ".join(short(m) for _, m in models)
    lines.append(header)
    lines.append("-" * len(header))
    for p in personas:
        cells_for_p = []
        for be, m in models:
            s = by_pm.get((p, be, m), {})
            label = f"P{s.get('PASS', 0)}/W{s.get('WARN', 0)}/F{s.get('FAIL', 0)}" if s else "-"
            cells_for_p.append(label.ljust(24))
        lines.append(p.ljust(persona_w) + " | " + " | ".join(cells_for_p))
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────

