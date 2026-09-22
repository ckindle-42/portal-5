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
    corpora = status.get("corpora", {})
    findings.append(
        {
            "retrieval_projection": status["status"],
            "corpora": {kb_id: entry["status"] for kb_id, entry in corpora.items()},
        }
    )
    if status["status"] != "FRESH":
        # Per corpus, because the status is per corpus: `built_from_fingerprint`
        # and the live fingerprint live on each entry, never at the top level.
        # Reading them from the top level raised KeyError, so the ONE branch that
        # reports the real drift crashed instead of naming it — and a check that
        # dies where it should explain is indistinguishable from a broken check.
        # An UNPROJECTED corpus has no fingerprints to compare — what it has is
        # sections in the store and none in the index — so the message names the
        # two counts instead (LOAD_AND_CONVERSE_V1 P1.2).
        drifted = [
            f"{kb_id} is UNPROJECTED — {entry.get('sections_in_store', 0)} sections in the "
            f"store, {entry.get('sections') or 0} in the index"
            if entry["status"] == "UNPROJECTED"
            else f"{kb_id} is {entry['status']} (built from "
            f"{str(entry.get('built_from_fingerprint', '') or 'nothing')[:12]}…, store is now "
            f"{str(entry.get('live_fingerprint', ''))[:12]}…)"
            for kb_id, entry in corpora.items()
            if entry["status"] != "FRESH"
        ]
        return (
            "FAIL",
            f"the retrieval index is {status['status']} against the section population: "
            + "; ".join(drifted or ["no corpus is projected"])
            + " — re-run scripts/project_compliance_sections.py",
            findings,
        )
    return "PASS", "", findings


@register(
    "jurisdiction_domain",
    "the jurisdiction domain has no value this module does not classify",
    order=198,
)
def check_jurisdiction_domain() -> tuple[str, str, list[dict]]:
    """FAIL when the store carries a jurisdiction outside {US, internal,
    operator_note, derived} — the exact failure mode that made ``operator_note``
    silently score as regulatory for the life of the module (CONTRACT_AND_CLOSE_V1
    §0 RC1): a sixth value must be a loud finding, never a guess."""
    from portal.modules.compliance.core.jurisdiction import unknown_jurisdictions
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        unknown = unknown_jurisdictions(repo)
    finally:
        repo.close()
    if unknown:
        named = ", ".join(f"{u['jurisdiction']!r} ({u['n_documents']} docs)" for u in unknown)
        return "FAIL", f"unclassified jurisdiction value(s): {named}", unknown
    return "PASS", "", []


@register(
    "citation_derivation_singleton",
    "section-id shape, jurisdiction side and requirement address are decided in exactly one place",
    order=199,
)
def check_citation_derivation_singleton() -> tuple[str, str, list[dict]]:
    """FAIL when a second module-level ``section-`` id regex exists outside
    ``answer_contract.py``, or a two-valued ``jurisdiction ==/!= "internal"``
    predicate survives anywhere. This is the guard against the habit
    CONTRACT_AND_CLOSE_V1 fixed: seven regexes and fourteen side rules,
    re-derived independently and disagreeing, because the material that already
    knew the answer discarded it. Two more of each were added by task files
    written AFTER the first fix — this check is what stops an eighth."""
    import re

    repo_root = Path(__file__).resolve().parents[2]
    section_regex = re.compile(r"section-\s*[\[\(]?\s*[0-9a-f]")
    jurisdiction_predicate = re.compile(r"""jurisdiction[^=!\n]{0,40}[=!]=\s*["']internal["']""")

    offenders: list[dict] = []
    for base in (repo_root / "portal", repo_root / "scripts"):
        for path in base.rglob("*.py"):
            if path.name in ("answer_contract.py", "compliance_currency.py"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(repo_root))
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "section-" in line and re.search(r"re\.compile\(.*section-", line):
                    offenders.append({"file": rel, "line": lineno, "kind": "section_id_regex"})
                if jurisdiction_predicate.search(line):
                    offenders.append(
                        {"file": rel, "line": lineno, "kind": "two_valued_jurisdiction"}
                    )
    if offenders:
        named = "; ".join(f"{o['file']}:{o['line']} ({o['kind']})" for o in offenders[:10])
        more = f" (+{len(offenders) - 10} more)" if len(offenders) > 10 else ""
        return "FAIL", f"the derivation habit survives: {named}{more}", offenders
    return "PASS", "", []
