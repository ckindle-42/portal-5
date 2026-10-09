"""review.constants -- every number in the product, and what KIND of number it is.

Root cause this exists for: constants decided answers (a distance cap, a 0.6 gate, a 0.05
identity threshold, weights summing to 1.15), and every embedder change silently moved the
scale under them. The lab's rule -- "no fixed constant decides the answer" -- was written down
three times and violated each time, because nothing checked it.

Here the check is mechanical. ``tests/security/review/test_invariants.py`` finds every
module-level ALL_CAPS number, numeric dataclass default and numeric function default in this
package and requires it to be registered below with a kind:

  budget    a resource or workload budget (rounds, tokens, candidates read). Recorded in the
            evaluation stamp; chosen against the workload the reader and analyst can afford.
  bound     a size or presentation bound that does not change what is concluded.
  protocol  a minimum a wire/format rule needs (a quote shorter than this proves nothing).

``threshold``, ``cutoff`` and ``weight`` are deliberately NOT kinds. A number that decides an
answer is fit from benign data (``calibration``) or it does not exist.
"""

from __future__ import annotations

ALLOWED_KINDS = frozenset({"budget", "bound", "protocol"})

REGISTRY: dict[str, tuple[str, str]] = {
    "content.DEFAULT_LIMIT": ("bound", "terms on a unit card; card size, not a decision"),
    "content.DEFAULT_PER_FIELD_CAP": (
        "bound",
        "terms one field may add, so background cannot crowd a card",
    ),
    "grounding.MIN_QUOTE_CHARS": (
        "protocol",
        "a shorter quote occurs somewhere by chance and proves nothing",
    ),
    "intake.compress_classes.max_runs": ("bound", "runs shown in a card's class sequence"),
    "intake.render_event.max_chars": (
        "bound",
        "characters of an event shown to a reader; quotes check against the same text",
    ),
    "judge.run_judge.max_events": (
        "budget",
        "events shown to the reader; recorded as evidence_shown/evidence_total",
    ),
    "judge.run_judge.max_rounds": ("budget", "pivot rounds the reader may spend"),
    "judge.run_judge.max_tokens": ("budget", "reply budget per model call"),
    "model_client.CONNECT_TIMEOUT_S": ("budget", "connection setup budget for the shared pipeline"),
    "model_client.STREAM_IDLE_TIMEOUT_S": ("budget", "maximum idle interval for one model stream"),
    "model_client.TRACE_TIMEOUT_S": ("budget", "trace lookup budget after a model response"),
    "model_client.CATALOG_TIMEOUT_S": (
        "budget",
        "model identity lookup budget after a model response",
    ),
    "model_client.REASONING_PROBE_MAX_TOKENS": (
        "budget",
        "output budget for a non-sensitive reasoning capability probe",
    ),
    "model_client.MAX_ATTEMPTS": ("budget", "one initial model request plus one transport retry"),
    "model_client.CORRELATION_ID_HEX_CHARS": (
        "protocol",
        "hex characters retained in a reader trace correlation id",
    ),
    "reader.DEFAULT_CONCERN_TIMEOUT_S": ("budget", "total time budget for one judged concern"),
    "reader.MAX_EVENTS": ("budget", "events shown to each reader call and pivot result"),
    "reader.MAX_ROUNDS": ("budget", "reader and challenger turns allowed per concern"),
    "reader.MAX_TOKENS": ("budget", "reply budget per reader model call"),
    "reader.P95_PERCENTILE": (
        "protocol",
        "nearest-rank latency percentile used for measured reader depth",
    ),
    "tools.MAX_TERM_CHARS": ("bound", "maximum literal search term length accepted from a model"),
    "tools.MAX_PIVOT_RESULTS": (
        "budget",
        "events shown for one pivot call; truncation is receipted",
    ),
    "knowledge.AnchorIndex.search.k": (
        "budget",
        "anchors retrieved per unit; the reader's candidate budget",
    ),
    "review_eval.PROOF_WORKLOAD_B": (
        "budget",
        "concerns admitted per proof window for paired workload-B recall",
    ),
    "knowledge.embed_texts.batch": ("bound", "texts per embedding request; transport only"),
    "panel.run_panel.max_events": ("budget", "as judge.run_judge.max_events"),
    "panel.run_panel.max_rounds": ("budget", "as judge.run_judge.max_rounds"),
    "panel.run_panel.max_tokens": ("budget", "as judge.run_judge.max_tokens"),
    "pipeline.EVIDENCE_REFS_SHOWN": (
        "bound",
        "evidence refs a concern carries; the total is stated in the brief",
    ),
    "pipeline.ReviewConfig.top_k_anchors": ("budget", "anchors explained per concern"),
    "window.DEFAULT_PARTITION_SECONDS": (
        "budget",
        "maximum duration of one fully fetched Splunk partition; adjacent partitions cover the full request",
    ),
    "window.DEFAULT_TIMEOUT_SECONDS": (
        "budget",
        "maximum duration for one Splunk HTTP request before it fails visibly",
    ),
    "embedding.DEFAULT_BATCH_SIZE": (
        "bound",
        "texts per embedding request; transport bound only, not an answer cutoff",
    ),
    "embedding.DEFAULT_TIMEOUT_SECONDS": (
        "budget",
        "maximum duration for one embedding HTTP request before it fails visibly",
    ),
    "runs.RunStore.list.limit": ("bound", "rows returned by a listing"),
    "store.ReviewStore.queue.limit": ("bound", "rows returned by a queue listing"),
    "defense.SPLUNK_EPOCH_PRECISION_S": (
        "protocol",
        "one Splunk epoch tick because bounded search windows serialize to six decimals",
    ),
}

# D-T6-PROOF preregisters a single concern per replay window for both arms.
PROOF_WORKLOAD_B = 1
