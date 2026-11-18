"""The overview dashboard must reflect real pipeline usage, not a 5-minute window.

Two contracts meet here. The dashboard may only query metrics the pipeline emits
on a path real traffic takes, and a counter may only be read through
``rate()``/``increase()`` — the pipeline restarts often and every counter starts
again at zero. At the source, one served turn is one persona count, one model
call is one ``portal_requests_by_model_total`` sample even when the engine sends
no usage frame, and ``portal_concurrent_requests`` is summed across workers.
"""

from __future__ import annotations


def test_concurrent_requests_gauge_is_summed_across_workers() -> None:
    from portal.platform.inference.router.metrics import _concurrent_requests

    assert _concurrent_requests._multiprocess_mode == "livesum"
