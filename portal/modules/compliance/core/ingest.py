"""Ingest the operator's folder: policies and procedures together (P3).

One command, idempotent and re-runnable: point at a directory holding policy
and procedure PDFs, ingest into the compliance retrieval composition, and
derive **layer** (policy/procedure/evidence) and **authority tier** per
document from the document's own self-description — title, filename,
document-number prefix, "Purpose"/"Scope" language. Every derivation writes a
``document_tier`` queue item, whatever the confidence — nothing defaults
silently. The layer census matters immediately: zero procedures means no cell
can reach ``FULL`` (§B), and that must be visible before anyone reads a matrix.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from portal.modules.compliance.core import review_queue as rq
from portal.modules.compliance.core.tiers import classify_tier

_DATA = Path(__file__).resolve().parent.parent / "data"
LAYER_SIDECAR = Path(
    os.environ.get("COMPLIANCE_LAYER_SIDECAR", _DATA / "compliance_document_layers.json")
)

# Strongest signal first: an explicit document-number prefix convention, then
# a title/header self-description. "Plan" and "Process" default to procedure
# (an operationalized set of steps); "Form"/"Report"/"Attestation"/"List" to
# evidence (a record). A blank line separates prefix checks (checked against
# the filename only) from title/header word checks (checked against filename,
# then falling back to the document's own first-page text at a discount).
_PREFIX_SIGNALS: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"OT-POL-", re.I), "policy", 0.95),
    (re.compile(r"OT-PROC-", re.I), "procedure", 0.95),
]
_WORD_SIGNALS: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"\bwork instruction\b", re.I), "procedure", 0.9),
    (re.compile(r"\bwi\b", re.I), "procedure", 0.85),  # "OT Vulnerability Management WI v1.pdf"
    (re.compile(r"\bprocedure\b", re.I), "procedure", 0.9),
    (re.compile(r"\bpolicy\b", re.I), "policy", 0.9),
    (re.compile(r"\bstandard\b", re.I), "policy", 0.6),
    (re.compile(r"\bplan\b", re.I), "procedure", 0.7),
    (re.compile(r"\bprocess\b", re.I), "procedure", 0.7),
    (re.compile(r"\battestation\b", re.I), "evidence", 0.8),
    (re.compile(r"\bform\b", re.I), "evidence", 0.8),
    (re.compile(r"\breport\b", re.I), "evidence", 0.7),
    (re.compile(r"\bcontact list\b", re.I), "evidence", 0.5),
]


def derive_tier(filename: str, first_page_text: str = "") -> dict:
    """(layer, authority_tier, confidence, evidence) from the document's own
    self-description. A document with no signal is not dropped — it is
    returned at low confidence with a best guess (``procedure``, the most
    common operator artifact) so a cell resting on it can be labelled rather
    than silently excluded."""
    for pat, layer, conf in _PREFIX_SIGNALS:
        if pat.search(filename):
            return {
                "layer": layer,
                "tier": classify_tier(layer),
                "confidence": conf,
                "evidence": f"document-number prefix matches {pat.pattern!r}",
            }
    for pat, layer, conf in _WORD_SIGNALS:
        m = pat.search(filename)
        if m:
            return {
                "layer": layer,
                "tier": classify_tier(layer),
                "confidence": conf,
                "evidence": f"filename contains {m.group(0)!r}",
            }
    for pat, layer, conf in _WORD_SIGNALS:
        m = pat.search(first_page_text[:3000])
        if m:
            return {
                "layer": layer,
                "tier": classify_tier(layer),
                "confidence": round(conf * 0.7, 2),
                "evidence": f"document text contains {m.group(0)!r} (no filename signal)",
            }
    return {
        "layer": "procedure",
        "tier": classify_tier("procedure"),
        "confidence": 0.2,
        "evidence": "no title, filename, or document-control-block signal found — defaulted",
    }


def read_sidecar(path: Path | str = LAYER_SIDECAR) -> dict:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def write_sidecar(data: dict, path: Path | str = LAYER_SIDECAR) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


_STANDARD_FOLDER_RE = re.compile(r"^CIP-(\d+)$", re.I)


def derive_standard_hint(file_path: Path) -> str | None:
    """The operator's own folder-per-standard organization is a strong
    association signal a proposer must not ignore: a PDF filed under
    ``CIP-007/`` is the operator's own claim that it implements CIP-007, not a
    hint to be rediscovered by lexical overlap alone. Returns the base
    standard id (``"CIP-007"``, matching every versioned register standard
    ``CIP-007-6``) from the file's immediate parent directory name, or
    ``None`` when the file isn't filed under a recognizable standard folder —
    an unhinted document is never excluded by ``propose()``, only one filed
    under a *different* standard's folder is."""
    m = _STANDARD_FOLDER_RE.match(file_path.parent.name)
    return f"CIP-{m.group(1)}" if m else None


async def ingest_folder(
    source_dir: str, kb_id: str = "operator_corpus", rebuild: bool = False
) -> dict:
    """Ingest every PDF under ``source_dir`` into the ``compliance_*``
    composition; derive and queue layer/tier for each; report the layer
    census. ``kb_*`` tables are never touched (compliance_retrieval's own
    prefix guarantee — verified by ``test_compliance_retrieval_seam.py``)."""
    from portal.modules.compliance.tools import compliance_retrieval as _cr
    from portal.platform.retrieval import extraction as _extraction
    from portal.platform.retrieval import pipeline as _pipeline

    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        return {"error": f"directory not found: {src}"}

    pdfs = sorted(f for f in src.rglob("*.pdf") if f.is_file())
    sidecar = read_sidecar()
    # idempotent re-run: a document already carrying an OPEN document_tier item
    # (still awaiting the operator) is not re-queued — a duplicate item every
    # re-ingest would make the queue unworkable, not more honest.
    already_open = {i.subject_id for i in rq.open_items(kind="document_tier")}
    census: dict[str, int] = {"policy": 0, "procedure": 0, "evidence": 0}
    queue_items: list[dict] = []

    for f in pdfs:
        rel = str(f.relative_to(src))
        try:
            text = await _extraction.read_text(f)
        except Exception:  # noqa: BLE001 - a bad PDF still gets a tier guess
            text = ""
        derived = derive_tier(f.name, text)
        derived["standard_hint"] = derive_standard_hint(f)
        if rel in already_open:
            item_id = sidecar.get(rel, {}).get("queue_item_id", "")
        else:
            item = rq.propose(
                "document_tier",
                subject_id=rel,
                proposed_value={"layer": derived["layer"], "tier": derived["tier"]},
                evidence=[
                    {
                        "document": rel,
                        "section": "title/filename",
                        "page": 1,
                        "span": derived["evidence"],
                    }
                ],
                confidence=derived["confidence"],
            )
            item_id = item.id
        sidecar[rel] = {**derived, "queue_item_id": item_id}
        census[derived["layer"]] = census.get(derived["layer"], 0) + 1
        queue_items.append({"document": rel, "layer": derived["layer"], "queue_item_id": item_id})

    write_sidecar(sidecar)

    # The underlying pipeline ingests every supported suffix (.pdf/.md/.txt/...
    # — see _DEFAULT_SUFFIXES), not only PDFs; the layer/tier derivation above
    # only concerns PDFs (the operator's real corpus), so this call always
    # runs regardless of whether any PDF was found in this pass.
    ingest_result: dict = {"files_ingested": 0, "chunks_added": 0, "pages_added": 0}
    ingest_error = None
    try:
        ingest_result = await _pipeline.ingest_document(_cr._composition(), kb_id, src, rebuild)
    except Exception as e:  # noqa: BLE001 - report, don't crash the ingest command
        ingest_error = str(e)

    return {
        "kb_id": kb_id,
        "source_dir": str(src),
        "files_seen": len(pdfs),
        "files_ingested": ingest_result.get("files_ingested", 0),
        "chunks_added": ingest_result.get("chunks_added", 0),
        "pages_added": ingest_result.get("pages_added", 0),
        "ingest_error": ingest_error,
        "layer_census": census,
        "zero_procedures_warning": census.get("procedure", 0) == 0,
        "document_tier_queue_items": queue_items,
    }
