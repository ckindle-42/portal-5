"""Security module's MCP tool surface: detections_mcp, mitre_mcp, security_mcp.

Each runs as a standalone MCP server process (see portal.modules.security.
tools.<name> and scripts/lib/util.sh / docker-compose for launch). The
detection-knowledge content they serve (SPL library, technique reference)
lives at portal.modules.security.knowledge — import from there, not here.
"""
