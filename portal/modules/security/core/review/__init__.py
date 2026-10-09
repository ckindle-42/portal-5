"""review -- the Bully reviewer: the product.

A source-agnostic security-data reviewer. It finds things that are NOT known but are the
same as, or similar to, something known; raises them to an analyst with grounded evidence;
and turns the analyst's verdict (something / nothing / unsure) into knowledge so the system
matures instead of being tuned. Known-bad matching is the floor, not the product.

Planes -- enforced by tests (``tests/security/review``), not by convention:

* observation plane  -- ``content``, ``intake``, ``calibration``, ``funnel``. What the data
  shows. These modules may never mention a label identifier (``wall.scan_source``).
* knowledge plane    -- ``knowledge``, ``verdicts``. Labels live here, as knowledge about
  KNOWN things (anchors), never as attributes of the thing under review.
* judgment           -- ``judge``, ``grounding``, ``panel``. A reasoning model reads; code
  gates. Every claim cites evidence a deterministic checker can locate.
* scorer plane       -- ``portal.modules.security.core.review_eval``. Nothing in this package
  may import it (``tests/security/review_eval/test_scorer_wall.py``).

No fixed constant decides an answer: thresholds are fit from benign data (``calibration``)
and re-fit automatically when the embedder identity changes.
"""

from __future__ import annotations

CONTRACT_VERSION = "review-contract-v1"
