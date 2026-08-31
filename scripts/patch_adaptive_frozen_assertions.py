"""Patch machine_assertions in the frozen adaptive-UAT catalog in place.

One-shot reconciliation for ACTION_ITEMS AI-6 / AI-7 (FINDINGS B1 / B2): the
frozen suite baked a too-narrow boundary refusal matcher and appended a
positive "Code delivered" assertion to boundary rows where a refusal is the
correct outcome. The generator (tests/uat/adaptive/generate.py) is already
fixed; this brings the frozen fixtures the deferred-compliance and A2 rerun
rows replay into line without re-authoring any prompt.

Idempotent. Run: python3 scripts/patch_adaptive_frozen_assertions.py
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.uat.adaptive.generate import (
    _STANDARD_REFUSAL_KEYWORDS,
    _UNCENSORED_OVERREFUSAL_KEYWORDS,
)

FROZEN_DIR = Path("tests/uat_adaptive/frozen")


def _patch_challenge(ch: dict) -> bool:
    if ch.get("dimension") != "boundary":
        return False
    asserts = ch.get("machine_assertions") or []
    changed = False
    new_asserts = []
    for a in asserts:
        label = a.get("label")
        if label == "Code delivered":
            changed = True
            continue  # drop positive-delivery assertion on boundary rows
        if label == "Appropriate refusal (standard posture)":
            if a.get("keywords") != list(_STANDARD_REFUSAL_KEYWORDS):
                a = {**a, "keywords": list(_STANDARD_REFUSAL_KEYWORDS)}
                changed = True
        elif label == "No over-refusal (uncensored posture)":
            if a.get("keywords") != list(_UNCENSORED_OVERREFUSAL_KEYWORDS):
                a = {**a, "keywords": list(_UNCENSORED_OVERREFUSAL_KEYWORDS)}
                changed = True
        new_asserts.append(a)
    if changed:
        ch["machine_assertions"] = new_asserts
    return changed


def main() -> None:
    files = sorted(FROZEN_DIR.glob("*.json"))
    total_files = 0
    total_rows = 0
    for f in files:
        suite = json.loads(f.read_text())
        touched = sum(_patch_challenge(ch) for ch in suite)
        if touched:
            f.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")
            total_files += 1
            total_rows += touched
            print(f"  {f.name}: {touched} boundary row(s) patched")
    print(f"done — {total_rows} row(s) across {total_files} file(s)")


if __name__ == "__main__":
    main()
