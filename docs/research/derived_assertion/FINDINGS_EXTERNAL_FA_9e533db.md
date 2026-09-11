# External corroboration — FrontierAgent at pinned commit

Reference: `ApodexAI/FrontierAgent` at `9e533db6f6c34d16037ee5ec964c479d0eb51cde`.
The byte/line-verified read set was `workflows/_shared/citation_contract.py:1-610`,
`workflows/agent_team/fast_reporter_v1_evidence.py:1-319`,
`workflows/agent_team/report_fast_guard.py:1-215`,
`benchmarks/public/runner/rejudge.py:1-112`, and
`benchmarks/public/runner/run_subprocess.py:1-532`. This artifact records
corroboration and failure lessons only; it is not an authority over Portal 5.

## 1. Concrete DAI-2 mechanism

FrontierAgent computes a URL-to-index map from the system whitelist. The map is
1-based and deliberately aligned with both prompt rendering and final canonical
reference rendering (`workflows/_shared/citation_contract.py:454-483`). Its
docstring identifies the mismatch hole: the reporter reads evidence nodes and a
separate reference list, so absent a stamped index it guesses by topical
plausibility; stamping the index lets the model copy the number (`workflows/_shared/citation_contract.py:457-470`).

The evidence projection carries the source fields used by the admission gate,
including `fetch_status`, `snippet_verbatim`, source quality, URL, and claim
(`workflows/agent_team/fast_reporter_v1_evidence.py:218-264`). The reference-row
join then stamps each evidence snippet with `→ cite as [N]` when tagging is
enabled, making the prompt's copy instruction operational (`workflows/agent_team/fast_reporter_v1_evidence.py:267-305`).

The prompt contract explicitly forbids the producer from writing its own
reference list and explicitly forbids choosing an index by title matching; it
must copy the tag attached to the evidence node (`workflows/_shared/citation_contract.py:486-535`).
After generation, the system strips a heading-led LLM References footer,
normalizes malformed numeric markers, removes orphan footnote markers, and
renumbers against the canonical whitelist by first appearance before appending
the canonical references block (`workflows/_shared/citation_contract.py:541-597`).
The renumberer intentionally leaves out-of-range markers untouched rather than
silently retargeting them to a real source (`workflows/_shared/citation_contract.py:403-448`).

The transferable pattern is therefore: system derives admissible evidence from
execution, system assigns the citation index, the producer copies an adjacent
index, and system reconstructs the final reference block from the admissible
set. The last step is a derived annotation operation, not trust in the
producer's bibliography (`workflows/_shared/citation_contract.py:454-483`, `workflows/_shared/citation_contract.py:541-597`).

## 2. Failure-mode catalogue mapped to Portal 5 classes

| External failure | Class | Evidence and lesson |
| --- | --- | --- |
| Globbed/placeholder URLs such as `gild-202*.htm` were syntactically valid and could otherwise flow into a canonical References block. | F1 — shape-matching substituted for verification | The reference names the laundering failure and the observed glob forms (`workflows/_shared/citation_contract.py:23-36`); `coerce_citation_url` rejects the marker before it can anchor a citation (`workflows/_shared/citation_contract.py:52-64`). |
| Malformed markers such as `[2的相关背景]` could leak as descriptive brackets instead of a numeric citation. | F1 | The finalizer documents normalization of malformed citations before renumbering (`workflows/_shared/citation_contract.py:572-576`). This is format repair, not proof that the cited source supports the claim. |
| Orphan markdown footnotes such as `[^idc_infra]` were minted for un-whitelisted claims and rendered as literal broken-reference text. | F1 | The contract forbids footnote syntax (`workflows/_shared/citation_contract.py:511-515`) and the finalizer strips orphan markers because numeric renumbering cannot define them (`workflows/_shared/citation_contract.py:577-581`). |
| A rewrite could drop every requested deliverable, including `/outputs/` paths or fenced code blocks; citations did not compensate. | F2 — provenance destroyed at a boundary | `DeliverablesLostError` states that the rewrite lost the artifact and that citations do not compensate (`workflows/agent_team/report_fast_guard.py:48-54`); metrics compare native and rewritten paths/blocks and detect total loss (`workflows/agent_team/report_fast_guard.py:57-105`). |
| Bracketed data such as `qs[0]`, indices, or IDs could be mistaken for citations, while implausible numeric brackets could be treated as prose. | F1 | The neutralizer masks inline-code data and implausible citation groups while preserving exact text in tokens (`workflows/agent_team/report_fast_guard.py:138-161`, `workflows/agent_team/report_fast_guard.py:175-206`). |

None of these guards turns a citation into semantic SUPPORT by itself. They
reduce shape and boundary errors; the evidence-to-claim judgment still needs an
admissible, system-assigned link and an independent support check
(`workflows/_shared/citation_contract.py:76-119`).

## 3. Dead-flag guards and honest limitations

The strict evidence-admission tier is controlled by `provenance_strict`, which
adds the requirements that a snippet be verbatim and that fetch status not be
failed, but defaults to `False` (`workflows/_shared/citation_contract.py:76-119`).
The upstream evidence projection explicitly says the chain never passes this
flag today, and that visit snippets are LLM paraphrases rather than quotes
(`workflows/agent_team/fast_reporter_v1_evidence.py:221-243`). This tier is a
design option, not proven behavior.

The other relevant guard is `tag_citations`: the index stamp is only added when
the caller passes `tag_citations=True` (`workflows/agent_team/fast_reporter_v1_evidence.py:267-305`). The contract promises tagged nodes, so an untagged call path would
re-open the mismatch hole even though the finalizer still canonicalizes the
reference block (`workflows/_shared/citation_contract.py:516-524`). This is an
opt-in wiring hazard, not a universal invariant.

The external benchmark layout keeps scoring as a derived annotation. Rejudge
finds existing `trials/*/result.json` artifacts, skips already-scored records
unless forced, reloads the full question because the stored display question is
truncated, and atomically writes the updated score fields
(`benchmarks/public/runner/rejudge.py:26-75`). The subprocess runner separately
preserves per-question result files, synthesizes timeout/crash records without
calling them wrong under external scoring, and writes aggregate `results.json`
and `summary.txt` (`benchmarks/public/runner/run_subprocess.py:88-124`, `benchmarks/public/runner/run_subprocess.py:150-201`, `benchmarks/public/runner/run_subprocess.py:378-439`). The small rejudge script works because the raw run artifact is already the record of truth.

## 4. What does not transfer

FrontierAgent's runtime, TUI, sandbox, Docker, approval flow, and web-URL
assumptions are not Portal 5 interfaces (`workflows/_shared/citation_contract.py:23-64`, `benchmarks/public/runner/run_subprocess.py:113-150`). Portal 5 should adapt the invariant to closed register nodes, wiki units, WFE rows, and model preflight records; it should not vendor or copy the external runtime. The corroboration supports the shape of system-assigned links and derived scores, not the specific transport or artifact schema.
