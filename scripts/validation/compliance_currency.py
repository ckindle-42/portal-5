"""GS — the compliance corpus is current, and its index matches its store.

BILATERAL_CORPUS_V1 P8.5. Two ways the bilateral corpus can quietly stop being
true, both invisible from the outside:

* **the regulatory side goes stale.** NERC moves an effective date, a standard
  retires, a new revision is filed — and nothing fetched it. Every answer after
  that is read from a document that no longer governs, with full confidence and
  correct-looking citations. A sync that has not run is not a sync that found
  nothing.
* **the index stops being a projection.** A re-capture moves a section boundary
  and the retrieval manifest still claims the generation it built earlier. Hits
  then resolve to spans that have shifted under them, which is the
  two-identity-spaces failure returning by another route.

Neither is baselinable and neither is a warning: an answer from a stale corpus
is worse than no answer, because it is confident.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.validation.registry import register

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / "data" / "private" / "nerc_autosync_state.json"

#: the LaunchAgent fires daily; a day of grace absorbs a laptop that was asleep.
SYNC_INTERVAL_HOURS = 24
SYNC_GRACE_HOURS = 24


def _age_hours(stamp: str) -> float | None:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            when = datetime.strptime(stamp, fmt)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return (datetime.now(UTC) - when).total_seconds() / 3600
    return None


@register(
    "compliance_corpus_currency_and_projection_freshness",
    "GS. the NERC corpus is synced within its interval and the index is a FRESH "
    "projection of the section population",
    order=197,
)
def check_compliance_corpus_currency() -> tuple[str, str, list[dict]]:
    from portal.modules.compliance.core.projections import retrieval_projection_status
    from portal.modules.compliance.core.repository import Repository

    findings: list[dict] = []

    if not STATE_PATH.is_file():
        return (
            "FAIL",
            f"no auto-sync state at {STATE_PATH.relative_to(REPO_ROOT)} — the NERC sync has "
            "never completed, so the regulatory corpus's currency is unknown",
            [],
        )
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "FAIL", f"auto-sync state is unreadable: {exc}", []

    last = str(state.get("last_success", ""))
    if not last:
        return (
            "FAIL",
            "auto-sync state records no successful run — "
            f"last attempt {state.get('last_attempt', 'never')}, "
            f"last error {state.get('last_error', 'none recorded')}",
            [],
        )
    age = _age_hours(last)
    if age is None:
        return "FAIL", f"auto-sync state carries an unparseable timestamp: {last!r}", []
    limit = SYNC_INTERVAL_HOURS + SYNC_GRACE_HOURS
    if age > limit:
        return (
            "FAIL",
            f"the last successful NERC sync was {age:.1f}h ago, past its {SYNC_INTERVAL_HOURS}h "
            f"interval plus {SYNC_GRACE_HOURS}h grace — the regulatory corpus may not reflect "
            "NERC's own registry",
            [],
        )
    findings.append({"last_successful_sync": last, "age_hours": round(age, 1)})

    repo = Repository()
    try:
        status = retrieval_projection_status(repo)
    finally:
        repo.close()
    findings.append({"retrieval_projection": status["status"]})
    if status["status"] != "FRESH":
        return (
            "FAIL",
            f"the retrieval index is {status['status']} against the section population "
            f"(built from {str(status.get('built_from_fingerprint', ''))[:12]}…, store is now "
            f"{status['canonical_fingerprint'][:12]}…) — re-run "
            "scripts/project_compliance_sections.py",
            findings,
        )
    return "PASS", "", findings
