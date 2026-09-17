# P5 tool-selection probe — 2026-09-16

The source workspace was probed through the local Ollama `/v1/chat/completions`
endpoint with the configured Qwen3.8 model, the complete `auto-compliance` tool
surface, and a posture question:

> Where are our gaps in CIP-007-6 R2, and how severe is each one?

| measure | observed |
| --- | --- |
| tools presented | 52 |
| elapsed time | 79.43 s |
| first tool selected | `compliance_gaps` |
| expected first tool | `compliance_ask` |
| result | selection degraded; split the focused reading workspace |

The probe is a routing/selection measurement, not evidence that the selected
tool produced a valid compliance answer. `compliance-reading` therefore binds
the same measured reading seat to a smaller 23-tool surface containing the
register, reading, currency, citation, context, and review paths. The broader
`auto-compliance` surface remains available for catalog and legacy operations;
the focused workspace is the default binding used by `runtime_config.reading_seat`.
