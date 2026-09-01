#!/usr/bin/env python3
"""Regenerate the distilled compliance control catalogs used by compliance_mcp.

Fetches the OSCAL JSON for NIST SP 800-53 Rev5 and NIST CSF 2.0 from
``usnistgov/oscal-content`` and distils each to the compact
``{control_id: {title, family/function, statement}}`` shape the MCP reads
(``portal/modules/compliance/data/``). The ~5MB source catalogs are never
vendored — only the ~380KB / ~85KB distillations.

Thin wrapper over ``compliance_mcp.refresh_catalogs`` so the CLI path and the
tool path share one implementation.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    from portal.modules.compliance.tools.compliance_mcp import refresh_catalogs

    out = refresh_catalogs()
    print(json.dumps(out, indent=2))
    return 0 if all("ok" in v for v in out.get("results", {}).values()) else 1


if __name__ == "__main__":
    sys.exit(main())
