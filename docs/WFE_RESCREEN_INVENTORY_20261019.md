# WFE re-screen inventory — 2026-10-19

The tool loop changed in two commits: `c8fe27e87d6ab8778e4702905ba25eb1d4e72604`
(2026-10-18 21:53 -0500), which carries reasoning and prose across tool hops, and
`68bfbd9a88978a7c6eddafc7a1bc89175d9281c4` (2026-10-19 00:04 -0500), which runs each hop's
calls in emitted order. WFE rows dated before both fixes may under-measure thinking models that
use tools. A report that explicitly says its campaign ran on the corrected pipeline is marked
POST even if its raw manifest is absent.

## Scope and evidence rules

The inventory includes production workspaces and routed seat variants with a non-empty tool
surface whose current model card declares a thinking mode or always-on reasoning. It also includes
a non-thinking seat when a thinking-capable challenger has recorded WFE evidence for that seat.
Challengers in plans without campaign rows are not counted as recorded evidence. Entries are
ordered with live seats and seat variants first, then the challenger-only case.

Where available, the campaign row's `env.git_sha` is compared with the two fix commits. For report
only evidence, the campaign date and the report's statement about the executed pipeline are used.
The checkout has five raw campaign manifests, all dated 2026-10-12 or 2026-10-13; the decision
reports for 2026-10-16 through 2026-10-19 do not have their raw manifests here. Those rows are
therefore labeled from the reports, and the one report that abbreviates campaign IDs retains that
limitation below.

## Inventory

| Production seat / variant | Why included | Latest decision evidence (campaign and date) | Relation to fixes |
|---|---|---|---|
| `auto-compliance` | Qwen3.8 thinking seat; 46 tools | `wfe_compliance_decision_20261016` (2026-10-16); follow-up screen `wfe_compliance_decision_20261016cf` (2026-10-16, screen-only, no fitness cell) | **PRE** — both campaign dates precede the fixes; reports have no row `env.git_sha` in this checkout |
| `auto-data` | Qwen3.6 thinking seat; recorded Qwen3.8 challenger; 7 tools | `wfe_data_decision_20261016` (2026-10-16); follow-ups `wfe_data_decision_20261016cf` and `wfe_data_guard_confirm_20261016` (both 2026-10-16; the latter re-measured the incumbent only) | **PRE** — all are dated before the fixes; raw decision manifests are absent |
| `tools-specialist` | Qwen3.6 thinking seat; 3 tools | The 2026-10-19 decision report identifies confirm campaigns as `g` and `h` | **POST** — the report explicitly says both reasoning carry-forward and ordered calls were present |
| `general-fast` | Qwen3.6 thinking seat; 13 tools | No decision-grade WFE campaign found in the ledger or reports | No evidence to compare; seat qualifies for a future screen |
| `general-deep` | Qwen3.8 thinking seat; 13 tools | No decision-grade WFE campaign. Latest campaign rows are `wfe_prompt_surface_seat_20261012` (2026-10-12; `env.git_sha=2b27d8c4`) | **PRE** — manifest SHA and date precede both fixes; this is a prompt-surface run, not a seat decision |
| `auto-general-uncensored` | Huihui Qwen3.6 thinking seat; 6 tools | No decision-grade WFE campaign found | No evidence to compare; seat qualifies for a future screen |
| `auto-uncensored-throwaway` | HauhauCS Qwen3.6 thinking seat; 7 tools | No decision-grade WFE campaign found | No evidence to compare; seat qualifies for a future screen |
| `auto-vision` | Qwen3-VL Thinking build; always reasons; 3 tools | No decision-grade WFE campaign found | No evidence to compare; seat qualifies for a future screen |
| `auto-security::pentest` | HauhauCS Qwen3.6 thinking variant; 7 tools | No decision-grade WFE campaign found | No evidence to compare; variant qualifies for a future screen |
| `auto-coding::uncensored-fast` | Qwen3.8 thinking variant; 9 tools | No decision-grade WFE campaign found | No evidence to compare; variant qualifies for a future screen |
| `auto-coding::lite` | AgentWorld seat variant; card says thinking on by default; 15 tools | No decision-grade WFE campaign found | No evidence to compare; variant qualifies for a future screen |
| `auto-coding::reap288` | Qwen3.8-Flash-Next thinking variant; 13 tools | No decision-grade WFE campaign found | Removed 2026-10-21 (stack-down-only). Do not screen. |
| `auto-documents` | Granite seat, but Qwen3.8 thinking challenger has recorded WFE rows; 7 tools | `wfe_documents_20261017h` (2026-10-17; confirm and screen) | **PRE** — the ledger records the rows on 2026-10-18 02:35 UTC (2026-10-17 21:35 -0500), before `c8fe`; raw manifest absent |

## Review notes

- The 2026-10-19 `tools-specialist` report names the confirm campaigns only as `g` and `h`; their
  full IDs and raw row fingerprints are not present in this worktree. Its explicit post-fix
  statement supports the POST classification, but the campaign names should be reconciled if those
  manifests become available.
- The 2026-10-13 instrument audit invalidated older WFE verdicts; this inventory does not treat
  pre-audit broad screens as current seat decisions. The 2026-10-18 seat census reports that the
  general, coding, CAD, and reading decision plans had not yet run, so plan-only challengers in
  those workspaces are not presented as recorded rows here.
- `auto-research` is not included: its 2026-10-18 Nex-N2.5 screen is recorded, but neither its seat
  nor that challenger has a thinking mode in the checked model-card expectations. `auto-creative`
  is not included because its configured workspace has no tools.
