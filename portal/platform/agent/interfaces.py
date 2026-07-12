"""Structural contracts for the platform agent loop.

Capabilities are duck-typed: any object exposing `id`, `tools`, and (optionally)
`oracle` / `phase` satisfies the engine. This lets security keep its rich
Capability dataclass unchanged while the platform stays generic.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Capability(Protocol):
    """One thing the system can do. Structural — modules supply their own type."""

    id: str
    tools: list[str]


@runtime_checkable
class CapabilityProvider(Protocol):
    """Grounds the decide-turn: given observations, return real candidates.

    Never free-form — the loop chooses only from what query() returns.
    """

    def query(
        self,
        observations: dict[str, Any],
        *,
        domain: str | None = None,
        goal: str | None = None,
        limit: int = 8,
    ) -> list[Any]: ...


@runtime_checkable
class Executor(Protocol):
    """Performs one chosen action and returns an observation delta.

    Return shape: {"observation_delta": {...}, "oracle_result": bool | None,
    "raw": Any}. Errors should be represented in the return, not raised, so the
    loop can score a failed step rather than crash.
    """

    def execute(self, decision: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]: ...
