"""Portal 5 — unified Release 1.0 Quality Acceptance Testing package.

Self-contained under tests/qat/; the legacy tests/uat/, tests/uat_catalog/
and tests/acceptance/ suites are retired. Discovery is live from
config/portal.yaml, imports/openwebui/workspaces/ and config/personas/.
"""

from .config import Settings, discover
from .models import DefectClass, QATResult, QATScenario, StageSummary, Status

__all__ = [
    "DefectClass",
    "QATResult",
    "QATScenario",
    "Settings",
    "StageSummary",
    "Status",
    "discover",
]
