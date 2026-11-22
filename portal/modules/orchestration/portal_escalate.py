"""Local Portal-seat escalation for blocked Jarvis jobs: Pipeline chat, never cloud lanes."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from portal.modules.orchestration.escalate import LaneChanges, LaneResult, _safe
from portal.modules.orchestration.worker import Engine

PORTAL_TARGETS = ("cloud", "portal", "portal_then_cloud")
#: Rung 1 is the kind's primary strong seat, rung 2 the deep seat; later attempts clamp.
DEFAULT_PORTAL_SEATS: dict[str, tuple[str, ...]] = {
    "code": ("auto-coding", "auto-reasoning::deep"),
    "security": ("auto-security", "auto-reasoning::deep"),
}
DEFAULT_PORTAL_TIMEOUT_S = 900.0
_SYSTEM_PROMPT = (
    "You are a local Portal escalation seat for a blocked Jarvis job. Diagnose the failure "
    "in the brief and give the minimal repair: exact code changes or commands, with file "
    "paths. This seat has no repository or shell access; do not claim to have edited, run "
    "or committed anything."
)


def escalation_target(policy: object) -> str:
    """Configured target mode; unset or unknown keeps the legacy cloud behavior."""
    env = os.environ.get("PORTAL_ESCALATION_TARGET", "").strip()
    if env:
        return env if env in PORTAL_TARGETS else "cloud"
    block = policy.get("escalation") if isinstance(policy, dict) else None
    configured = block.get("target") if isinstance(block, dict) else None
    if isinstance(configured, str) and configured in PORTAL_TARGETS:
        return configured
    return "cloud"


def portal_seats_map(policy: object) -> dict[str, list[str]]:
    """The per-kind seat ladder: operator map over the defaults, malformed entries ignored."""
    seats = {kind: list(rungs) for kind, rungs in DEFAULT_PORTAL_SEATS.items()}
    block = policy.get("escalation") if isinstance(policy, dict) else None
    raw = block.get("portal_seats") if isinstance(block, dict) else None
    if not isinstance(raw, dict):
        return seats
    for kind, rungs in raw.items():
        if not isinstance(kind, str):
            continue
        values = [rungs] if isinstance(rungs, str) else rungs
        if not isinstance(values, (list, tuple)):
            continue
        cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        if cleaned:
            seats[kind] = cleaned
    return seats


def cloud_fallback_allowed(policy: object) -> bool:
    """A cloud attempt after the portal ladder needs portal_then_cloud AND personal_cloud on."""
    if escalation_target(policy) != "portal_then_cloud":
        return False
    cloud = policy.get("personal_cloud") if isinstance(policy, dict) else None
    return isinstance(cloud, dict) and cloud.get("enabled") is True


def portal_url() -> str:
    return (
        os.environ.get("PIPELINE_URL")
        or os.environ.get("PORTAL_ARM_PIPELINE_URL")
        or "http://127.0.0.1:9099"
    ).rstrip("/")


class PortalSeatDispatcher:
    """One blocked-job attempt against a local Portal workspace over the Pipeline chat API."""

    def __init__(
        self,
        seats: Mapping[str, Sequence[str]] | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = DEFAULT_PORTAL_TIMEOUT_S,
        engine_factory: Callable[[str], Engine] | None = None,
    ) -> None:
        self.seats = {kind: list(rungs) for kind, rungs in (seats or DEFAULT_PORTAL_SEATS).items()}
        self.base_url = (base_url or portal_url()).rstrip("/")
        self.api_key = os.environ.get("PIPELINE_API_KEY", "") if api_key is None else api_key
        self.timeout_s = timeout_s
        self._engine_factory = engine_factory or self._engine

    def _engine(self, seat: str) -> Engine:
        return Engine(seat, "", self.base_url, self.api_key)

    def seat_for(self, kind: str, attempt: int) -> str:
        rungs = self.seats.get(kind) or self.seats.get("code") or list(DEFAULT_PORTAL_SEATS["code"])
        return rungs[max(0, min(attempt - 1, len(rungs) - 1))]

    def run(
        self,
        *,
        role: str,
        tier: str,
        kind: str,
        brief: Path,
        repo: Path,
        new: bool = True,
        cancel_check: Callable[[], bool] | None = None,
        attempt: int = 1,
    ) -> LaneResult:
        seat = self.seat_for(kind, attempt)
        try:
            text = brief.read_text(encoding="utf-8")
        except OSError as exc:
            return self._failed(role, seat, f"brief unreadable: {exc}")
        if cancel_check is not None and cancel_check():
            return self._failed(role, seat, "cancelled before dispatch")
        body = {
            "model": seat,
            "stream": True,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        try:
            response = self._engine_factory(seat).chat(body, self.timeout_s, lambda event: None)
            content = str(response["choices"][0]["message"]["content"] or "")
        except Exception as exc:  # noqa: BLE001 — a seat fault is a failed attempt, never a raise
            return self._failed(role, seat, f"portal seat {seat} failed: {exc}")
        if not content.strip():
            return self._failed(role, seat, f"portal seat {seat} returned an empty answer")
        return LaneResult(
            role,
            "portal",
            0,
            content,
            f"lane/{_safe(role)}",
            None,
            LaneChanges((), (), ()),
            status="done",
            model=seat,
        )

    def _failed(self, role: str, seat: str, detail: str) -> LaneResult:
        return LaneResult(
            role,
            "portal",
            1,
            detail,
            f"lane/{_safe(role)}",
            None,
            LaneChanges((), (), ()),
            status="error",
            model=seat,
        )
