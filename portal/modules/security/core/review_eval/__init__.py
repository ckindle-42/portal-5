"""review_eval -- the scorer plane for the reviewer. OFFLINE; never part of a product path.

Nothing in ``portal.modules.security.core.review`` (or anything the product imports) may import
this package, the BOTS answer keys, the specimen ledger, or any generator/injection module --
``tests/security/review_eval/test_scorer_wall.py`` walks the import closure and fails if one
does. That is the compliance core's rule ("the scorer is an offline instrument; nothing in the
product path imports it") applied here, because the lab's measurement history is a catalogue of
instruments that could not fail:

* ``confidence`` that was schema-presence mass, ``precision 1.0`` over a population with no
  negatives, ``recall 1.0`` because misses were not counted, a harness whose "v1 base arm"
  silently became v2, a statistic computed over rows from another configuration.

So here: a known-answer self-test must pass before any report is written (``selftest``), every
report carries a stamp (``stamp``), every metric states how it can fail and is recomputed from
the raw rows (``report``), and a report that cannot be backed is never written.
"""

from __future__ import annotations

HARNESS_VERSION = "review-eval-v1"
