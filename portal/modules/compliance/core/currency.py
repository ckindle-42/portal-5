"""NERC CIP currency probe (T3 Phase 8).

`refresh_catalogs()` covers NIST 800-53 and CSF 2.0 and **not** NERC, so
"current" was not a property the system could establish about its own data.

This probe reports, per held standard: our version, whether a newer version PDF
is reachable on nerc.com, and — because the standard PDFs defer their effective
date to a separate Implementation Plan — an explicit **verify against NERC's
enforcement schedule** rather than an inferred date. `honest-BLOCKED` when
nerc.com is unreachable, matching the precedent `refresh_catalogs` sets.
**Currency is never inferred.**
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from portal.modules.compliance.core.cip_register import _NERC_BASE, Register

_TIMEOUT = 15


def _pdf_exists(name: str) -> bool | None:
    """True/False if we got a definitive answer; None if the request failed."""
    try:
        req = urllib.request.Request(
            f"{_NERC_BASE}/{name}.pdf", method="HEAD", headers={"User-Agent": "portal5"}
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310 - fixed host
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        return e.code != 404 and e.code < 500
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


def _next_versions(std_ver: str) -> list[str]:
    """Candidate newer file stems for 'CIP-007-6'. F02's second half: the
    prior version of this function checked only the next TWO INTEGER
    versions — it could never discover a decimal/errata revision of the SAME
    major version (the design doc's real example: CIP-006-7.1). Includes
    both integer bumps and a decimal errata candidate for each."""
    m = re.match(r"(CIP-\d{3})-(\d+)(?:\.\d+\w*)?$", std_ver, re.I)
    if not m:
        return []
    base, v = m.group(1).lower(), int(m.group(2))
    return [
        f"{base}-{v}.1",
        f"{base}-{v + 1}",
        f"{base}-{v + 1}.1",
        f"{base}-{v + 2}",
    ]


def _held_family_numbers(standards: list[str]) -> set[int]:
    out = set()
    for s in standards:
        m = re.match(r"CIP-(\d{3})-", s, re.I)
        if m:
            out.add(int(m.group(1)))
    return out


def discover_new_families(standards: list[str], *, probe_ahead: int = 3) -> list[str]:
    """Probe for entirely new CIP-0XX families beyond the highest held family
    number (F02: "the held register's zero future nodes does not demonstrate
    that no future obligations exist" — the same is true for whole new
    families like the design doc's real CIP-015 example). PDF reachability
    is a discovery SIGNAL only, never proof of a complete catalog — a real
    verified official index is P3 work this function does not replace."""
    held = _held_family_numbers(standards)
    if not held:
        return []
    found = []
    for n in range(max(held) + 1, max(held) + 1 + probe_ahead):
        if _pdf_exists(f"cip-{n:03d}-1"):
            found.append(f"CIP-{n:03d}")
    return found


def nerc_currency(reg: Register | None = None) -> dict:
    """Per-standard currency report. Never infers an enforcement date."""
    reg = reg or Register.load()
    standards = sorted({n.standard for n in reg.nodes})

    # one cheap reachability probe first
    probe = _pdf_exists(standards[0].lower().replace("cip-", "cip-"))
    if probe is None:
        return {
            "status": "honest-BLOCKED",
            "reason": "nerc.com unreachable — currency cannot be established, and "
            "is never inferred. Retry, or verify manually at nerc.com/pa/Stand.",
            "held_standards": standards,
        }

    per: list[dict] = []
    for std in standards:
        newer = None
        for cand in _next_versions(std):
            if _pdf_exists(cand):
                newer = cand.upper()
                break
        life = next((n for n in reg.nodes if n.standard == std), None)
        per.append(
            {
                "standard": std,
                "held_version": std,
                "newer_version_pdf_reachable": newer,
                "our_lifecycle_state": life.lifecycle_state if life else "?",
                "our_valid_from": life.valid_from if life else None,
                "enforcement_date": "SEE Implementation Plan at nerc.com/pa/Stand — "
                "the standard PDF does not carry it; verify, do not infer.",
                "action": (
                    f"a newer version ({newer}) is published — download it, re-run the "
                    "register build, and verify its enforcement date before treating "
                    "it as current"
                    if newer
                    else "no newer version PDF found; still verify the enforcement "
                    "schedule for future-effective revisions"
                ),
            }
        )
    new_families = discover_new_families(standards)
    return {
        "status": "ok",
        "source": "nerc.com/globalassets/standards/reliability-standards/cip/ (PDF reachability)",
        "note": "PDF reachability is evidence a newer version EXISTS, not that it "
        "is enforceable. Enforcement dates come from the Implementation Plan and "
        "are never inferred here.",
        "n_standards": len(per),
        "n_with_newer_version": sum(1 for p in per if p["newer_version_pdf_reachable"]),
        "per_standard": per,
        "new_families_discovered": new_families,
        "new_family_discovery_note": (
            f"probed CIP-{max(_held_family_numbers(standards)) + 1:03d} through "
            f"CIP-{max(_held_family_numbers(standards)) + 3:03d} for reachability beyond "
            "the highest held family — a signal only, not a verified official index (P3)"
        ),
    }
