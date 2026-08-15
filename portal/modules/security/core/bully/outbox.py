"""bully.outbox -- transactional index-outbox retry/backoff policy (P1.2).

Pure compute over outbox row state; `store.py` is the only module that
performs the actual SQL I/O (MASTER SS3). This module decides *when* a
lease expires and *whether* an item should dead-letter -- store.py calls
it and persists the result.
"""

from __future__ import annotations

MAX_ATTEMPTS = 8
BASE_DELAY_S = 2.0
MAX_DELAY_S = 900.0


def backoff_delay_s(attempt: int) -> float:
    """Bounded exponential backoff: `min(MAX_DELAY_S, BASE_DELAY_S * 2**attempt)`."""
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    return min(MAX_DELAY_S, BASE_DELAY_S * (2**attempt))


def should_dead_letter(attempts: int) -> bool:
    """A required dead letter blocks hunt closure (DATA_MODEL SS1.10)."""
    return attempts >= MAX_ATTEMPTS


def next_attempt_at(now: float, attempt: int) -> float:
    return now + backoff_delay_s(attempt)
