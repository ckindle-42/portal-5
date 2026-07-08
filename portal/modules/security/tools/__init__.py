"""Public surface for the SPL detection library."""

from tests.benchmarks.bench_security.siem.spl_detections import (
    spl_for,
    spl_variants_for,
    technique_signature_full,
    techniques_covered,
)

__all__ = ["spl_for", "spl_variants_for", "technique_signature_full", "techniques_covered"]
