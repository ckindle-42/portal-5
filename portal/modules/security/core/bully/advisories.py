"""Live threat-advisory source with honest sparse signatures."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.request import Request, urlopen

from .connectors import QUERY_IN_PLACE_MODE, NativeQuery, QueryIntent, QueryResult
from .data_plane import DataPlane, SourceProfile

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CISA_KEV_LICENCE = "CISA KEV public feed"


def fetch_cisa_kev(url: str = CISA_KEV_URL) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "portal5-bully-sa7/1.0"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - URL is an explicit feed input
        return json.loads(response.read().decode("utf-8"))


def _advisory_record(
    item: Mapping[str, Any], *, retrieved_at: float, source_url: str
) -> dict[str, Any]:
    cve_id = str(item.get("cveID") or item.get("cve_id") or "")
    vendor = str(item.get("vendorProject") or item.get("vendor") or "")
    product = str(item.get("product") or "")
    return {
        "record_class": "threat_advisory",
        "advisory_id": cve_id or str(item.get("vulnerabilityName") or "unknown"),
        "title": str(item.get("vulnerabilityName") or ""),
        "description": str(item.get("shortDescription") or ""),
        "attack_mappings": [
            {
                "external_id": cve_id,
                "mapping_type": "vulnerability",
                "source": "CISA KEV",
            }
        ],
        "artifacts": [{"type": "cve", "value": cve_id}] if cve_id else [],
        "context_topology": {"vendor": vendor, "product": product},
        "source": source_url,
        "retrieved_at": retrieved_at,
        "licence": CISA_KEV_LICENCE,
        "date_added": item.get("dateAdded"),
        "required_action": item.get("requiredAction"),
        "due_date": item.get("dueDate"),
        "known_ransomware_campaign_use": item.get("knownRansomwareCampaignUse"),
    }


class LiveAdvisoryConnector:
    """Fetch advisory documents in place; retain no feed copy in the Store."""

    source_id = "live-advisories"
    mode = QUERY_IN_PLACE_MODE
    language = "HTTPS JSON"

    def __init__(
        self,
        fetcher: Callable[[], Mapping[str, Any]] = fetch_cisa_kev,
        *,
        source_url: str = CISA_KEV_URL,
    ) -> None:
        self.fetcher = fetcher
        self.source_url = source_url

    def translate(self, intent: QueryIntent) -> NativeQuery:
        return NativeQuery(
            self.source_id,
            self.language,
            {"method": "GET", "url": self.source_url, "purpose": intent.purpose},
            intent,
        )

    def read(self, intent: QueryIntent) -> QueryResult:
        started = time.time()
        retrieved_at = time.time()
        try:
            payload = self.fetcher()
            raw_items = payload.get("vulnerabilities") or payload.get("records") or []
            records = [
                _advisory_record(item, retrieved_at=retrieved_at, source_url=self.source_url)
                for item in raw_items
                if isinstance(item, Mapping)
            ]
            finding = None
        except Exception as exc:  # the result is the durable finding surface
            records = []
            finding = {
                "kind": "advisory_fetch",
                "status": "unavailable",
                "source": self.source_url,
                "reason": f"{type(exc).__name__}: {exc}",
                "retrieved_at": retrieved_at,
            }
        truncated = intent.limit is not None and len(records) >= intent.limit
        if intent.limit is not None:
            records = records[: intent.limit]
        metadata = {
            "record_count": len(records),
            "source": self.source_url,
            "retrieved_at": retrieved_at,
            "licence": CISA_KEV_LICENCE,
            "finding": finding,
        }
        return QueryResult(
            self.source_id,
            self.mode,
            self.translate(intent),
            tuple(records),
            started,
            time.time(),
            truncated=truncated,
            metadata=metadata,
        )


def register_live_advisory_source(
    plane: DataPlane,
    *,
    fetcher: Callable[[], Mapping[str, Any]] = fetch_cisa_kev,
    source_url: str = CISA_KEV_URL,
    sample_limit: int = 128,
    source_id: str = "live-advisories",
) -> tuple[SourceProfile, dict[str, Any]]:
    connector = LiveAdvisoryConnector(fetcher, source_url=source_url)
    connector.source_id = source_id
    probe = connector.read(QueryIntent("profile live threat advisories", limit=sample_limit))
    metadata = dict(probe.metadata)
    profile = plane.connect(
        source_id,
        connector,
        probe.records,
        source_meta={
            "record_class": "advisory",
            "freshness_at": probe.metadata.get("retrieved_at"),
            "record_count_override": probe.metadata.get("record_count"),
            "capabilities": {
                "semantic_text": bool(probe.records),
                "shared_timeline": bool(probe.records),
            },
        },
    )
    plane.audit.record(probe, sensitivity=profile.access.sensitivity)
    return profile, metadata
