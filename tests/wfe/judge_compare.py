#!/usr/bin/env python3
"""Compare local vs cloud judge outcomes for a campaign.

Reports, never gated.  Reads the same campaign directory twice — once per
``judgements/`` (local) and ``judgements/<profile>/`` — and summarises agreement / disagreement.

Usage:
  uv run python -m tests.wfe.judge_compare --campaign wfe_live
"""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path

from tests.wfe.judge import judgements_dir


def _load(profile_dir: Path) -> dict[str, dict]:
    """(sha12_key, record) for every file in profile_dir."""
    out: dict[str, dict] = {}
    if not profile_dir.is_dir():
        return out
    for f in sorted(profile_dir.glob("*.json")):
        with contextlib.suppress(Exception):
            rec = json.loads(f.read_text())
            key = rec.get("key") or f.stem
            out[key] = rec
    return out


def _kappa(pairwise: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for (local_pref, cloud_pref) pairs. Returns None when there
    is no data."""
    if not pairwise:
        return None
    cats: set[str] = set()
    for a, b in pairwise:
        cats.add(a)
        cats.add(b)
    n = len(pairwise)
    cm: dict[str, dict[str, int]] = {c1: dict.fromkeys(cats, 0) for c1 in cats for c2 in cats}
    for a, b in pairwise:
        cm[a][b] += 1
    po = sum(cm[c][c] for c in cats) / n
    row_totals = [sum(cm[c1].values()) for c1 in cats]
    col_totals = [sum(cm[c1][c2] for c1 in cats) for c2 in cats]
    pe = sum(r * c for r, c in zip(row_totals, col_totals, strict=True)) / (n * n)
    if pe >= 1.0:
        return None
    return (po - pe) / (1 - pe)


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912,PLR0915
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--campaigns-root", type=Path)
    ap.add_argument("--profiles", nargs="+", default=["local", "cloud"], help="profiles to compare")
    args = ap.parse_args(argv)

    from tests.wfe import campaign as camp

    root = args.campaigns_root or camp.CAMPAIGNS
    campaign_dir = root / args.campaign
    profiles = args.profiles

    stores: dict[str, dict[str, dict]] = {}
    for p in profiles:
        stores[p] = _load(judgements_dir(campaign_dir, p))
    keys_by_profile: dict[str, set[str]] = {p: set(recs) for p, recs in stores.items()}
    shared_keys = set.intersection(*keys_by_profile.values()) if keys_by_profile else set()

    print(f"Campaign: {args.campaign}")
    for p in profiles:
        recs = stores[p]
        errors = sum(1 for r in recs.values() if r.get("error"))
        print(f"  {p}: {len(recs)} record(s), {errors} error(s)")
    print(f"Pairs with all profiles: {len(shared_keys)}")
    if not shared_keys:
        return 0

    # Build per-key paired preferences (skip records with errors)
    paired: list[tuple[str, dict[str, str | None]]] = []
    for key in sorted(shared_keys):
        prefs = {}
        all_valid = True
        for p in profiles:
            rec = stores[p].get(key)
            if rec and not rec.get("error"):
                prefs[p] = rec.get("preference")
            else:
                prefs[p] = None
                all_valid = False
        if all_valid and any(prefs.values()):
            paired.append((key, prefs))

    if not paired:
        print("No valid paired preferences to compare.")
        return 0

    # Agreement
    agreeing = sum(1 for _, prefs in paired if len({v for v in prefs.values() if v}) == 1)
    agreement = agreeing / len(paired) if paired else 0.0

    # Kappa: pairwise (profile[0], profile[1])
    kappa_pairs = [
        (prefs[profiles[0]], prefs[profiles[1]])
        for _, prefs in paired
        if prefs.get(profiles[0]) and prefs.get(profiles[1])
    ]
    kappa = _kappa(kappa_pairs) if kappa_pairs else None

    print(f"\nAgreement: {agreeing}/{len(paired)} = {agreement:.2%}")
    if kappa is not None:
        print(f"Cohen's kappa: {kappa:.4f}")

    # Disagreements
    disagrees = [(key, prefs) for key, prefs in paired if len({v for v in prefs.values() if v}) > 1]
    if disagrees:
        print(f"\nDisagreements ({len(disagrees)}):")
        print(f"  {'key':<42} {'local':>8} {'cloud':>8}  {'reason (local / cloud)'}")
        print(f"  {'-' * 42} {'-' * 8} {'-' * 8}  {'-' * 40}")
        for key, prefs in disagrees:
            local_r = stores[profiles[0]].get(key) or {}
            cloud_r = stores[profiles[1]].get(key) or {}
            local_pref = prefs.get(profiles[0]) or "?"
            cloud_pref = prefs.get(profiles[1]) or "?"
            local_reason = (local_r.get("reason") or "")[:80]
            cloud_reason = (cloud_r.get("reason") or "")[:80]
            print(
                f"  {key:<42} {local_pref:>8} {cloud_pref:>8}  "
                f"{local_reason[:50]} / {cloud_reason[:50]}"
            )
    else:
        print("No disagreements.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
