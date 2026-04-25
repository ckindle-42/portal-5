"""S9: delegated to monolith."""

from tests.acceptance._common import _monolith


async def run() -> None:
    await _monolith().S9()
