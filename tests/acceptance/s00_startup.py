"""S0: Prerequisites and environment check."""

from tests.acceptance._common import _monolith


async def run() -> None:
    await _monolith().S0()
