"""Opt-in analyst feedback for generalized hunt case signatures."""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from .knowledge import PROOF_INDEXES

VERDICTS = frozenset({"true_positive", "false_positive", "benign_expected", "needs_review"})
SOURCES = frozenset({"operator", "judge"})
GENERATOR_NAMES = frozenset(
    {"alerts", "peer_rare", "deviation", "misfit", "similar_to_known", "set_novelty"}
)
ENTITY_ROLES = frozenset(
    {
        "actor",
        "action",
        "object",
        "from",
        "to",
        "outcome",
        "host",
        "user",
        "process",
        "service",
        "file",
        "account",
        "device",
        "source",
        "destination",
        "ip",
        "network",
        "entity",
    }
)
SIGNATURE_KEYS = frozenset({"family", "generators", "entity_roles", "sourcetypes"})
MAX_PRIOR_DELTA = 0.25
SUPPORT_DAMPING = 4.0
RECENCY_HALF_LIFE_DAYS = 180.0
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_HOSTNAME = re.compile(r"(?:[a-z0-9-]+\.)+[a-z]{2,}\Z", re.IGNORECASE)

Store = str | Path | duckdb.DuckDBPyConnection


def stage4_verdicts_enabled() -> bool:
    """Read the explicit Stage 4 opt-in flag, which defaults to off."""
    return os.environ.get("PORTAL_HUNT_STAGE4_VERDICTS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _table(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS hunt_verdicts ("
        "verdict_id VARCHAR PRIMARY KEY, created_at TIMESTAMP NOT NULL, "
        "index_name VARCHAR NOT NULL, case_id VARCHAR, entity_key VARCHAR, "
        "behaviour_sig VARCHAR NOT NULL, verdict VARCHAR NOT NULL, "
        "confidence DOUBLE NOT NULL, rationale VARCHAR NOT NULL, source VARCHAR NOT NULL, "
        "family VARCHAR NOT NULL)"
    )


@contextmanager
def _connection(store: Store) -> Iterator[duckdb.DuckDBPyConnection]:
    if isinstance(store, duckdb.DuckDBPyConnection):
        yield store
        return
    path = Path(store)
    if not path.is_file():
        raise FileNotFoundError(f"hunt knowledge store not found: {path}")
    connection = duckdb.connect(str(path))
    try:
        yield connection
    finally:
        connection.close()


def _is_indicator(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        return True
    return bool(_HOSTNAME.fullmatch(value))


def _token(value: Any, field: str) -> str:
    normalized = str(value or "").strip().casefold()
    if not _TOKEN.fullmatch(normalized) or _is_indicator(normalized):
        raise ValueError(f"{field} must be a generalized category, not an IOC value")
    return normalized


def _values(raw: Any, field: str) -> list[str]:
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{field} must be a category or a sequence of categories")
    normalized = {_token(value, field) for value in values}
    return sorted(normalized)


def _sourcetypes(raw: Any) -> list[str]:
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError("sourcetypes must be a category or a sequence of categories")
    return sorted(
        {_token(str(value).split(":", 1)[0].split("/", 1)[0], "sourcetypes") for value in values}
    )


def _signature(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not raw or set(raw) - SIGNATURE_KEYS:
        raise ValueError("behaviour signature must use only generalized category fields")
    result: dict[str, Any] = {}
    for key in ("family", "generators", "entity_roles", "sourcetypes"):
        value = raw.get(key)
        if value is None or value == "" or value == [] or value == ():
            continue
        if key == "family":
            result[key] = _token(value, key)
            continue
        values = _sourcetypes(value) if key == "sourcetypes" else _values(value, key)
        if key == "generators" and set(values) - GENERATOR_NAMES:
            raise ValueError("behaviour signature contains an unknown generator")
        if key == "entity_roles" and set(values) - ENTITY_ROLES:
            raise ValueError("behaviour signature contains an unknown entity role")
        if values:
            result[key] = values
    if not result:
        raise ValueError("behaviour signature needs at least one generalized category")
    return result


def _signature_text(signature: Mapping[str, Any]) -> str:
    return json.dumps(signature, sort_keys=True, separators=(",", ":"))


def _role(value: Any) -> str | None:
    role = str(value or "").strip().casefold()
    return role if role in ENTITY_ROLES else None


def _case_signature(case: Mapping[str, Any]) -> dict[str, Any] | None:
    supplied = case.get("behaviour_sig")
    if isinstance(supplied, Mapping):
        return _signature(supplied)
    members = [item for item in case.get("members") or () if isinstance(item, Mapping)]
    generators = {
        str(item.get("generator") or "").casefold()
        for item in members
        if str(item.get("generator") or "").casefold() in GENERATOR_NAMES
    }
    roles = {
        role
        for item in case.get("entities") or ()
        if (role := _role(str(item).partition(":")[0])) is not None
    }
    sources = [str(item.get("source_id") or "") for item in members]
    sources.extend(str(item) for item in case.get("sources") or ())
    sourcetypes = {
        source.partition(":")[2].split(":", 1)[0].split("/", 1)[0].split(".", 1)[0].casefold()
        for source in sources
        if ":" in source
    }
    raw: dict[str, Any] = {}
    if generators:
        raw["generators"] = sorted(generators)
    if roles:
        raw["entity_roles"] = sorted(roles)
    if sourcetypes:
        raw["sourcetypes"] = sorted(sourcetypes)
    family = case.get("family")
    if family:
        raw["family"] = family
    return _signature(raw) if raw else None


def _index_is_proof(index_name: str) -> bool:
    return index_name.strip().casefold() in PROOF_INDEXES


def carry_verdicts(source: Path, target: Path) -> None:
    """Retain feedback rows when the knowledge builder atomically refreshes its database."""
    if not source.is_file():
        return
    previous = duckdb.connect(str(source), read_only=True)
    try:
        tables = {str(row[0]) for row in previous.execute("SHOW TABLES").fetchall()}
        if "hunt_verdicts" not in tables:
            return
        rows = previous.execute(
            "SELECT verdict_id, created_at, index_name, case_id, entity_key, behaviour_sig, "
            "verdict, confidence, rationale, source, family FROM hunt_verdicts"
        ).fetchall()
    finally:
        previous.close()
    if not rows:
        return
    refreshed = duckdb.connect(str(target))
    try:
        _table(refreshed)
        refreshed.executemany(
            "INSERT INTO hunt_verdicts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
    finally:
        refreshed.close()


def record_verdict(
    *,
    store: Store,
    index_name: str,
    verdict: str,
    confidence: float,
    behaviour_sig: Mapping[str, Any],
    source: str,
    family: str,
    case_id: str | None = None,
    entity_key: str | None = None,
    rationale: str = "",
    allow_proof_for_tests: bool = False,
) -> str:
    """Persist one generalized verdict, refusing held-out proof indexes by default."""
    index = str(index_name or "").strip()
    if not index:
        raise ValueError("index_name is required")
    if _index_is_proof(index) and not allow_proof_for_tests:
        raise ValueError(f"proof index {index!r} cannot provide verdict feedback")
    normalized_verdict = str(verdict or "").strip().casefold()
    if normalized_verdict not in VERDICTS:
        raise ValueError(f"unsupported verdict: {verdict!r}")
    normalized_source = str(source or "").strip().casefold()
    if normalized_source not in SOURCES:
        raise ValueError(f"unsupported verdict source: {source!r}")
    numeric_confidence = float(confidence)
    if not math.isfinite(numeric_confidence) or not 0.0 <= numeric_confidence <= 1.0:
        raise ValueError("confidence must be finite and between zero and one")
    signature = _signature(behaviour_sig)
    normalized_family = _token(family, "family")
    normalized_entity = _role(entity_key) if entity_key is not None else None
    if entity_key is not None and normalized_entity is None:
        raise ValueError("entity_key must name a generalized entity role")
    case_identifier = str(case_id or "").strip() or None
    if case_identifier and len(case_identifier) > 160:
        raise ValueError("case_id is too long")
    reason = str(rationale or "")[:4000]
    identifier = str(uuid.uuid4())
    with _connection(store) as connection:
        _table(connection)
        connection.execute(
            "INSERT INTO hunt_verdicts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                identifier,
                datetime.now(UTC).replace(tzinfo=None),
                index,
                case_identifier,
                normalized_entity,
                _signature_text(signature),
                normalized_verdict,
                numeric_confidence,
                reason,
                normalized_source,
                normalized_family,
            ],
        )
    return identifier


def _prior(
    connection: duckdb.DuckDBPyConnection,
    *,
    index_name: str,
    family: str | None,
    entity_key: str | None,
    behaviour_sig: Mapping[str, Any],
) -> dict[str, float | int]:
    if _index_is_proof(index_name):
        return {"delta": 0.0, "support": 0}
    signature = _signature(behaviour_sig)
    conditions = ["behaviour_sig = ?"]
    parameters: list[Any] = [_signature_text(signature)]
    if family:
        conditions.append("family = ?")
        parameters.append(_token(family, "family"))
    normalized_entity = _role(entity_key) if entity_key is not None else None
    if entity_key is not None and normalized_entity is None:
        raise ValueError("entity_key must name a generalized entity role")
    if normalized_entity:
        conditions.append("(entity_key IS NULL OR entity_key = ?)")
        parameters.append(normalized_entity)
    proof_indexes = sorted(PROOF_INDEXES)
    conditions.append("lower(index_name) NOT IN (" + ",".join("?" for _ in proof_indexes) + ")")
    parameters.extend(proof_indexes)
    rows = connection.execute(
        "SELECT verdict, confidence, created_at FROM hunt_verdicts WHERE "
        + " AND ".join(conditions),
        parameters,
    ).fetchall()
    if not rows:
        return {"delta": 0.0, "support": 0}
    now = datetime.now(UTC)
    total_weight = 0.0
    evidence = 0.0
    for verdict, confidence, created_at in rows:
        confidence_value = float(confidence)
        if not math.isfinite(confidence_value) or not 0.0 <= confidence_value <= 1.0:
            continue
        moment = created_at.replace(tzinfo=UTC)
        age_days = max(0.0, (now - moment).total_seconds() / 86400.0)
        weight = confidence_value * math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)
        direction = (
            1.0
            if verdict == "true_positive"
            else -1.0
            if verdict
            in {
                "false_positive",
                "benign_expected",
            }
            else 0.0
        )
        evidence += weight * direction
        total_weight += weight
    support = len(rows)
    if total_weight <= 0.0:
        return {"delta": 0.0, "support": support}
    mean = evidence / total_weight
    damped = mean * support / (support + SUPPORT_DAMPING)
    delta = max(-MAX_PRIOR_DELTA, min(MAX_PRIOR_DELTA, MAX_PRIOR_DELTA * damped))
    return {"delta": round(delta, 8), "support": support}


def query_verdict_priors(
    *,
    store: Store,
    index_name: str,
    behaviour_sig: Mapping[str, Any],
    family: str | None = None,
    entity_key: str | None = None,
) -> dict[str, float | int]:
    """Return a bounded, recency-weighted delta and matching support count."""
    if _index_is_proof(index_name):
        return {"delta": 0.0, "support": 0}
    with _connection(store) as connection:
        _table(connection)
        return _prior(
            connection,
            index_name=index_name,
            family=family,
            entity_key=entity_key,
            behaviour_sig=behaviour_sig,
        )


def apply_verdict_priors(
    cases: Sequence[Mapping[str, Any]], *, store: Store, enabled: bool | None = None
) -> Sequence[Mapping[str, Any]]:
    """Apply opt-in case score deltas and expose their support beside the ranking."""
    if not (stage4_verdicts_enabled() if enabled is None else enabled):
        return cases
    eligible = [
        (position, row)
        for position, row in enumerate(cases)
        if not _index_is_proof(str(row.get("index_name") or ""))
    ]
    if not eligible:
        return cases
    adjusted = [dict(row) for row in cases]
    with _connection(store) as connection:
        _table(connection)
        for position, row in eligible:
            signature = _case_signature(row)
            if signature is None:
                prior: dict[str, float | int] = {"delta": 0.0, "support": 0}
            else:
                prior = _prior(
                    connection,
                    index_name=str(row.get("index_name") or ""),
                    family=str(row.get("family") or "") or None,
                    entity_key=str(row.get("entity_key") or "") or None,
                    behaviour_sig=signature,
                )
            delta = float(prior["delta"])
            adjusted[position]["verdict_prior_delta"] = delta
            adjusted[position]["verdict_support"] = int(prior["support"])
            score = float(row.get("score") or 0.0)
            if math.isfinite(score):
                adjusted[position]["score"] = score + delta
    adjusted.sort(
        key=lambda row: (
            -float(row.get("score") or 0.0),
            float(row.get("start") or 0.0),
            str(row.get("case_id") or ""),
        )
    )
    for rank, row in enumerate(adjusted):
        row["rank"] = rank
    return adjusted
