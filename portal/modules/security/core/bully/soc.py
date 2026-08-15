"""bully.soc -- G3, the SOC visibility lane (P2.4). API per I-7a:
``deliver(candidate) -> SOCDeliveryReceipt``.

Proves the *Bully finding* reaches the real analyst path -- a producer ack
PLUS a consumer-side triage report via the existing `siem/blue_triage.py`
lane under a queue-load corpus -- never just a producer ack (I-7a: "producer
ack without a consumer query is insufficient"). This validates delivery of
the Bully finding, **not** the missed detector's firing (that is G1a/G1b's
job).

No model call is authored in this module: the default consumer step reuses
`siem/blue_triage.py::enrich_alert`, which itself goes through the pipeline
(that call lives in blue_triage.py, not here) -- `soc.py` only drives the
existing poll/enrich functions and never appears in the boundary test's
model-calling allowlist for that reason.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable

from .contracts import DecisionEvent, SOCDeliveryReceipt, new_id
from .store import Store

PublishFn = Callable[[dict], dict]
PollFn = Callable[..., list[dict]]
EnrichFn = Callable[[dict], dict]


def _content_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def build_redacted_envelope(candidate_row: dict, *, correlation_key: str) -> dict:
    """Redacted finding envelope (I-7a INPUT): identifying fields only,
    secrets excluded -- no evidence bytes, no raw model output, no
    credentials. `correlation_key` is stable per candidate+alert_version so
    redelivery is a new attempt, never a duplicate notable (I-7a
    IDEMPOTENCY/RETRY)."""
    return {
        "correlation_key": correlation_key,
        "candidate_id": candidate_row.get("candidate_id"),
        "alert_version": candidate_row.get("alert_version"),
        "current_state": candidate_row.get("current_state"),
        "gate_policy_version": candidate_row.get("gate_policy_version"),
        "source": "bully-bin",
    }


def correlation_key_for(candidate_row: dict) -> str:
    return f"bully-{candidate_row.get('candidate_id')}-v{candidate_row.get('alert_version')}"


def _default_producer_publish(envelope: dict) -> dict:
    from ..siem.hec_ship import ship_batch

    return ship_batch(
        [envelope],
        sourcetype="portal5:bully_finding",
        host="bully-bin",
        evidence_origin="observed_packet",
    )


def _default_consumer_poll(*, since_minutes: int = 5) -> list[dict]:
    from ..siem.blue_triage import poll_alerts

    return poll_alerts(since_minutes=since_minutes)


def _default_consumer_enrich(alert: dict) -> dict:
    from ..siem.blue_triage import enrich_alert

    return enrich_alert(alert)


def _find_matching_alert(alerts: list[dict], correlation_key: str) -> dict | None:
    for alert in alerts:
        if str(alert.get("correlation_key", "")) == correlation_key:
            return alert
    return None


def _record(
    store: Store, *, hunt_id, actor: str, subject_id: str, rationale: str, data: dict
) -> None:
    store.record_decision(
        DecisionEvent(
            event_id=new_id("de"),
            hunt_id=hunt_id,
            iteration_id=None,
            actor=actor,
            kind="gate",
            subject_id=subject_id,
            rationale=rationale,
            data=data,
        )
    )


def deliver(
    candidate_row: dict,
    *,
    store: Store,
    destination: str = "lab-siem",
    config_version: str = "soc-lane-v1",
    priority: str = "P3",
    load_profile: str = "queue-load-default",
    producer_publish: PublishFn | None = None,
    consumer_poll: PollFn | None = None,
    consumer_enrich: EnrichFn | None = None,
    actor: str = "system:soc",
) -> SOCDeliveryReceipt:
    """Drive the finding through producer publish -> consumer poll ->
    consumer enrich, and return a durable receipt (persisted to
    `soc_deliveries`). Infra hiccups at any step are reflected honestly in
    the receipt's own fields (producer_ack/consumer_query_ran/
    content_hash_match all default False) rather than raised -- G3's
    pass/fail decision (`SOCDeliveryReceipt.sufficient`, consumed by
    `promotion.py::_run_g3`) is entirely code over this receipt, never a
    model call."""
    producer_publish = producer_publish or _default_producer_publish
    consumer_poll = consumer_poll or _default_consumer_poll
    consumer_enrich = consumer_enrich or _default_consumer_enrich

    correlation_key = correlation_key_for(candidate_row)
    envelope = build_redacted_envelope(candidate_row, correlation_key=correlation_key)
    payload_hash = _content_hash(envelope)
    envelope["payload_hash"] = payload_hash

    start = time.time()
    producer_ack = False
    try:
        publish_result = producer_publish(envelope)
        producer_ack = bool(publish_result and publish_result.get("ok"))
    except Exception:
        producer_ack = False

    consumer_query_ran = False
    consumer_triage_report: dict | None = None
    content_hash_match = False
    matched_alert: dict | None = None
    if producer_ack:
        try:
            alerts = consumer_poll()
            consumer_query_ran = True
            matched_alert = _find_matching_alert(alerts, correlation_key)
        except Exception:
            consumer_query_ran = False

    if matched_alert is not None:
        try:
            consumer_triage_report = consumer_enrich(matched_alert)
            content_hash_match = matched_alert.get("payload_hash") == payload_hash
        except Exception:
            consumer_triage_report = None
            content_hash_match = False

    latency_s = time.time() - start
    delivery_id = f"soc-{uuid.uuid4().hex[:12]}"

    store.soc_delivery_put(
        delivery_id=delivery_id,
        candidate_id=candidate_row["candidate_id"],
        correlation_key=correlation_key,
        destination=destination,
        config_version=config_version,
        payload_hash=payload_hash,
        producer_ack=producer_ack,
        consumer_query_ran=consumer_query_ran,
        consumer_triage_report=consumer_triage_report,
        priority=priority,
        latency_s=latency_s,
        content_hash_match=content_hash_match,
        load_profile=load_profile,
        lifecycle_status="visible"
        if (producer_ack and consumer_query_ran)
        else "sent"
        if producer_ack
        else "failed",
    )
    _record(
        store,
        hunt_id=candidate_row.get("hunt_id"),
        actor=actor,
        subject_id=candidate_row["candidate_id"],
        rationale=(
            f"G3 SOC delivery: producer_ack={producer_ack} consumer_query_ran={consumer_query_ran} "
            f"content_hash_match={content_hash_match}"
        ),
        data={"delivery_id": delivery_id, "correlation_key": correlation_key},
    )

    return SOCDeliveryReceipt(
        delivery_id=delivery_id,
        candidate_id=candidate_row["candidate_id"],
        correlation_key=correlation_key,
        producer_ack=producer_ack,
        consumer_query_ran=consumer_query_ran,
        consumer_triage_report=consumer_triage_report,
        priority=priority,
        latency_s=latency_s,
        content_hash_match=content_hash_match,
        load_profile=load_profile,
    )


__all__ = ["deliver", "build_redacted_envelope", "correlation_key_for"]
