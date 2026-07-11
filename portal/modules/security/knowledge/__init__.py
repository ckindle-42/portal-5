"""Public surface for the security module's grounding knowledge.

The RBP engine (portal.modules.security.core) stays intact per
BUILD-SPEC-PORTAL-MODULES-V1 Slice 3 — this is a stable re-export
boundary over its detection knowledge, not a second copy. Other code
(and future modules) should depend on this surface instead of reaching
into core.siem or core.exec_chain internals directly.

Covers: the SPL detection library + technique reference (siem/
spl_detections.yaml), scenario definitions (exec_chain.SCENARIOS), and
the wiki-backed technique-signature seeding (portal.platform.wiki
adapters — a knowledge unit per technique, cited to this library).
"""

from portal.modules.security.core.exec_chain import SCENARIOS
from portal.modules.security.core.siem.spl_detections import (
    spl_for,
    spl_variants_for,
    technique_reference,
    technique_signature_full,
    techniques_covered,
)
from portal.platform.wiki.adapters.seed_security import (
    seed_dcsync_specifically,
    seed_technique_signatures,
)

__all__ = [
    "SCENARIOS",
    "seed_dcsync_specifically",
    "seed_technique_signatures",
    "spl_for",
    "spl_variants_for",
    "technique_reference",
    "technique_signature_full",
    "techniques_covered",
]
