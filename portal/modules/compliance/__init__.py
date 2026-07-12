"""The compliance module — config-only, like general (M5 of
BUILD_PROGRAM_MODULARIZATION_ALL_V1).

No dedicated compliance MCP server exists; the discipline is a workspace
(auto-compliance, config/portal.yaml) plus the security module's
compliance_report.py (multi-framework mapping — stays in security per
"RBP stays intact", it's the RBP engine's own compliance report
generator, not compliance-as-a-discipline's implementation).
"""
