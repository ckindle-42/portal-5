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
    """Candidate newer file stems for 'CIP-007-6' -> ['cip-007-7', 'cip-007-8']."""
    m = re.match(r"(CIP-\d{3})-(\d+)(?:\.\d+\w*)?$", std_ver, re.I)
    if not m:
        return []
    base, v = m.group(1).lower(), int(m.group(2))
    return [f"{base}-{v + 1}", f"{base}-{v + 2}"]


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
    return {
        "status": "ok",
        "source": "nerc.com/globalassets/standards/reliability-standards/cip/ (PDF reachability)",
        "note": "PDF reachability is evidence a newer version EXISTS, not that it "
        "is enforceable. Enforcement dates come from the Implementation Plan and "
        "are never inferred here.",
        "n_standards": len(per),
        "n_with_newer_version": sum(1 for p in per if p["newer_version_pdf_reachable"]),
        "per_standard": per,
    }
