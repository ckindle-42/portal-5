"""Local trusted-reviewer authentication (P7 / F09).

Portal 5 has no platform-wide auth system — Open WebUI owns that (CLAUDE.md:
"A web chat interface, auth system... Open WebUI handles those") — and no MCP
tool in this fleet threads a request/user identity through to its handler
(verified: no other module does this either; every `@mcp.tool()` function is
a plain call with no session context). A review decision's authority
therefore cannot come from a caller-supplied ``decided_by`` string, because
nothing distinguishes that string from a model inventing a name.

Per the design's explicit fallback ("If no trusted interactive review channel
exists, implement a local reviewer entry point with a trusted principal;
reject approval through an unauthenticated/agent-only path"): a review
decision must present a REVIEWER TOKEN the operator configured out-of-band,
in a file this module never writes to itself. The effective ``decided_by`` is
DERIVED from the verified token — never taken from caller-supplied text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"
REVIEWERS_PATH = Path(
    os.environ.get("COMPLIANCE_REVIEWERS_PATH", _DATA / "compliance_reviewers.json")
)


class UnauthenticatedReviewError(RuntimeError):
    """No valid reviewer token was presented — the decision did not happen."""


def _load_reviewers() -> dict[str, str]:
    if REVIEWERS_PATH.exists():
        data = json.loads(REVIEWERS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise UnauthenticatedReviewError(f"{REVIEWERS_PATH} must contain a token->name object")
        return data
    return {}


def reviewers_configured() -> bool:
    return bool(_load_reviewers())


def verify_reviewer(token: str) -> str:
    """Returns the trusted principal's name for a valid ``token``. Raises
    ``UnauthenticatedReviewError`` for a missing/invalid/unconfigured token
    — this never falls back to trusting caller-supplied text, and never
    returns a default identity when no reviewers file exists."""
    if not token:
        raise UnauthenticatedReviewError(
            "no reviewer_token presented — a review decision requires an "
            "operator-issued token (see REVIEWERS_PATH), never a model-supplied name"
        )
    reviewers = _load_reviewers()
    if not reviewers:
        raise UnauthenticatedReviewError(
            f"no reviewers configured at {REVIEWERS_PATH} — an operator must create this "
            'file ({"<token>": "<name>"}) before any review decision can be authenticated'
        )
    name = reviewers.get(token)
    if not name:
        raise UnauthenticatedReviewError("reviewer_token does not match any configured reviewer")
    return name
