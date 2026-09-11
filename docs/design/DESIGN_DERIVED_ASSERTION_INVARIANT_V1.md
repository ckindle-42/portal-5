# DESIGN_DERIVED_ASSERTION_INVARIANT_V1

**Status:** research/design complete; ledger registration is not applicable at current HEAD
**Reference implementation:** the wiki spine (`portal_wiki/canonical/`, `portal/platform/wiki/`)
**Corroborating external prior art:** Appendix A / `FINDINGS_EXTERNAL_FA_9e533db.md`

## 1. The invariant

**DAI-1.** A derived assertion carries a recomputable link to the evidence that licenses it.

**DAI-2.** The link is assigned by the system from execution evidence—never chosen by the producer of the assertion.

**DAI-3.** A validator detects missing, broken, or unsupported links without re-executing the producer.

At this HEAD the wiki is not a complete DAI reference implementation. It has
mechanical source resolution, derived-body freshness, coverage, executable
claim-vs-probe checks, and archive reachability, but its `SourceRef` is supplied
by the unit author and its old `last_generated_commit` pin axis was removed
(`portal/platform/wiki/schema.py:16-40`, `portal/platform/wiki/drift.py:14-21`).
The current tree therefore demonstrates parts of DAI-1/DAI-3 but not strong
DAI-2 or general claim-to-source SUPPORT. The supplied thesis counts
631/631, 1128 fresh pins, 0 stale, and 0 phantom are not current-tree facts and
are intentionally not repeated as design premises.

This is new construction serving the wiki and the compliance surface from one
platform contract, not propagation of a proven wiki pin mechanism.

## 2. Four validation levels

| Level | Checks | Catches |
| --- | --- | --- |
| EXISTENCE | a link is present | unpinned or uncited assertions |
| RESOLUTION | the target resolves to an allowed real artifact | phantom/fabricated links |
| FRESHNESS | the target or derived projection has not changed without recomputation | stale derived material |
| SUPPORT | the target actually licenses the assertion | citation mismatch |

Current wiki checks cover the first three only in domain-specific/mechanical
ways. BS's executable claims are the useful seed for SUPPORT, but its path-ref
axis does not establish that a `SourceRef` licenses the prose
(`scripts/validation/wiki.py:360-423`, `portal/platform/wiki/drift.py:9-21`).

## 3. Four instances

### 3.1 Wiki — instance zero

The unit schema stores authored `SourceRef` values (`type`, `path`, optional
`commit`, optional `section`) and requires at least one source
(`portal/platform/wiki/schema.py:16-40`, `portal/platform/wiki/schema.py:44-71`).
AJ audits local source resolution and corruption; AW compares regenerated bodies
and generated blocks; BR checks manifest coverage; BS checks declared claims and
dead paths; BT checks archive reachability (`portal/platform/wiki/audit.py:125-180`, `scripts/validation/wiki.py:154-266`, `scripts/validation/wiki.py:269-459`).

There is no current pin freshness predicate. `check_staleness` compares a
machine-derived body with the canonical body, not a source commit with a pin
(`portal/platform/wiki/maintain.py:51-79`). A separate append-only
`LedgerEntry` records cross-run audit events, but is not a pin record
(`portal/platform/wiki/provenance_ledger.py:43-61`). Any new DAI adapter must
preserve these distinctions and add system-assigned evidence links rather than
introduce another incompatible source field.

### 3.2 Compliance — claim → citation → register node

The current compliance register is a real 254-node JSON artifact with a typed
`RegisterNode` schema (`portal/modules/compliance/data/nerc_cip_register.json`, `portal/modules/compliance/core/cip_register.py:85-142`, `portal/modules/compliance/core/cip_register.py:316-320`). IDs are grammar-conformant (`portal/modules/compliance/core/cip_extract.py:38-43`, `portal/modules/compliance/core/cip_extract.py:78-96`). The task's claim that `ingest.py` currently discards this structure is false at HEAD: compliance forces Docling chunking with page/headings when available, and the shared pipeline stores file, index, character offsets, page, and headings (`portal/modules/compliance/tools/compliance_retrieval.py:20-27`, `portal/modules/compliance/tools/compliance_retrieval.py:71-103`, `portal/platform/retrieval/pipeline.py:95-127`). A fixed fallback remains possible when Docling is unavailable (`portal/platform/retrieval/chunking.py:168-184`), so locator quality must be explicit in the evidence record.

The proposed compliance design is:

1. Resolve a user claim into an atomic claim object with a stable register-node ID and the retrieval locator actually returned.
2. Build an admissible node set from returned evidence, reject IDs absent from the closed register, and assign 1-based citation indices in a system-owned map.
3. Stamp the index on the evidence object passed to each council seat. Seats copy the tag; they do not choose a number by title matching.
4. Preserve uncited claims as qualified analysis or drop them. An untagged evidence node is not a citable source.
5. After generation, discard any producer-written bibliography, validate markers, and render a canonical references block from the indexed evidence.

This exploits the closed-corpus advantage: resolution to a 254-node register can
be a hard, enumerable check. The existing council is listwise over one
pre-analyzed packet and applies member-level quorum (`portal/modules/compliance/core/council.py:200-274`). Per-claim quorum is therefore new construction, not a small switch. The security agreement layer is decomposable to technique IDs but still not atomic claims (`portal/modules/security/core/council_agreement.py:75-173`). Build a claim-level aggregation contract only after the citation/index contract is stable.

The F3 defense is independent evidence assignment: a shared prompt and shared
admissible set can create correlated agreement. Use index-order permutation across
seats or an untagged control seat when evaluating whether agreement reflects
support rather than prompt correlation. Convergence is stability, not correctness.

### 3.3 Benchmarks — score → scorer version + raw transcript + environment

The benchmark artifact must be the transcript; a score is a derived annotation.
The current `bench_tps` aggregate already stores nested raw `response_text` in
`runs`, but emits no scorer version and no per-result `ctx_validated` or
`tool_choice` (`tests/benchmarks/bench/measure.py:357-364`, `tests/benchmarks/bench/measure.py:404-424`). WFE has a stronger row shape with transcript, tool log, sampling, environment, and schema version (`tests/wfe/schema.py:25-26`, `tests/wfe/schema.py:85-121`, `tests/wfe/campaign.py:662-728`).

Minimum additive result record:

| Field | Purpose |
| --- | --- |
| run identity | model tag, workspace, suite, arm, repeat, seed |
| environment | actual context validation, actual tool-choice mode, quantization, runtime, git and service fingerprint |
| raw output | verbatim stream, including reasoning-trace preamble |
| tool trace | calls/results before argument coercion |
| timing/economics | prefill, decode, wall, token counts |
| scorer identity | name and immutable version/content hash |
| score | derived verdict/quality annotation |

The fast path is safe only as an additive record change. The existing WFE
writer constructs a dataclass and serializes optional/defaulted fields, while
debug capture already separates final text and transcript
(`tests/wfe/schema.py:85-121`, `tests/wfe/campaign.py:662-728`). Run the real WFE
test suite and preserve the current campaign outputs before C2. If the historical
84-test/16-payload compatibility claim cannot be reproduced, defer the format
change rather than altering an unattended campaign. The four zero-score bench
records are on disk with raw response text, so capability-aware re-scoring is
possible without inference, but there is no scorer-version provenance for the
existing score.

### 3.4 Model catalog — verdict → preflight probe record

The supplied 62 pending and 10 `CONTEND-pending` queues do not exist in the
current tree as pending work. The former pending ledger is explicitly retired
and points to terminal closeout artifacts (`config/PENDING_MODEL_VERDICTS.md:1-21`).
This is not a reason to fabricate recomputation evidence. Going forward, every
catalog verdict should link to an immutable preflight/probe record containing
model identity, workspace config, actual context and tool-choice settings,
environment fingerprint, raw response/tool trace, scorer/checker identity, and
the derived disposition. `ctx_validated` today is a workspace YAML gate, not a
per-model probe artifact (`scripts/validation/personas.py:222-287`).

## 4. Enforcement — one check, not three

The current structural model is the validation registry plus Rule 6: register a
named check, derive both sides from live inputs, and report exact set differences
(`scripts/validation/registry.py:19-43`, `scripts/validation/config.py:25-72`).
The live registry has 213 checks and ends at GQ; there is no current AL doc
currency check (`scripts/validate_system.py:19-28`, `scripts/validation/security_bench.py:2023-2023`).

Proposed platform check, after ledger infrastructure is clarified:

- Enumerate registered assertions from wiki, compliance, benchmark, and catalog adapters.
- Require every assertion to carry an evidence identity and every identity to resolve in the domain's closed artifact set or explicitly declare an open-corpus locator policy.
- Recompute derived links without invoking the producer; compare the recorded link and report missing, broken, stale, or unsupported cases.
- Return exact adapter/domain counts and set differences. Do not turn retrieval errors into false compliance gaps.
- Keep support judgments separate from mechanical resolution: a real register node can still be the wrong node for a claim.

Do not implement this check in the present research task. The task's requested
Rule-12 ledger registration is not applicable at this HEAD: both
`docs/.doc_ledger.yaml` and `scripts/doc_ledger.py` are absent, and current
migration code intentionally treats a missing ledger as an empty path set
(`portal/platform/wiki/migration.py:312-320`). This is a stale task premise to
record, not a reason to invent a replacement ledger or hold the research output.

## 5. Sequencing

1. Before WFE C2, land only an additive transcript/scorer-version/environment
   record format if the actual WFE repair tests pass unchanged and current rows
   remain readable. This is the only time-sensitive item because after C2 a
   scorer defect becomes a re-sweep or unrecoverable evidence gap.
2. Re-score the four existing zero-score benchmark records using raw outputs,
   but do not treat the result as comparable until scorer identity and runtime
   fields are attached.
3. Define the common evidence/index contract, then implement compliance claim
   decomposition and catalog probe records.
4. Add one registry-level DAI check only after the missing doc-ledger/Rule-12
   ownership is resolved. No production code or model/config change belongs in
   this research task.

## 6. What deliberately does not transfer

FrontierAgent's runtime, TUI, sandbox, Docker path, approval flow, and web-URL
assumptions do not transfer. Portal 5's locators are register nodes, chunk
offsets, wiki sources, and benchmark transcripts. The invariant does not address
hardware incompatibility, inference performance, disk reclaim, module toggles,
or genuine capability absence.

## 7. Operator gate — resolved dispositions

1. **Per-claim rather than per-answer quorum:** adopt per-claim aggregation after
   the system-assigned index contract exists. Whole-answer quorum cannot detect
   two seats citing different claims or one seat's unsupported subclaim. This is
   a later build-program decision because it requires a decomposed claim schema,
   not a minor change to current council counting.
2. **WFE timing:** make the transcript/scorer-version change the next fast-path
   build candidate before C2, but only as an additive schema change validated by
   the actual repair tests and campaign readers. Do not alter the live campaign
   from this research task; if compatibility fails, defer the change rather than
   mutate an unattended run. The historical 84/16 claim is not confirmed at
   this HEAD.
3. **Scope:** build the evidence/index primitive as a platform capability for
   compliance, Research MCP, and RAG MCP, with separate domain adapters and
   support policies. The shared failure mode is boundary provenance; three
   bespoke implementations would drift. This task records the order and does
   not start that build.
4. **Scorer version:** use a human-readable scorer name plus a content hash of
   the scorer module/configuration. A monotonic integer cannot prove which code
   produced a historical score; a content hash is re-derivable and can be shown
   alongside the semantic name.

The operator gate is therefore closed for this research task: proceed to a future
build program in the order above, with no model promotion, config mutation, or
ledger recreation in this task.

## Appendix A — external corroboration

`ApodexAI/FrontierAgent` at commit
`9e533db6f6c34d16037ee5ec964c479d0eb51cde` independently implements the key
shape for open-corpus research: system-assigned citation indices stamped on
evidence, copy-not-guess prompt instructions, canonical post-generation
references, and derived score annotations
(`docs/research/derived_assertion/FINDINGS_EXTERNAL_FA_9e533db.md`, `workflows/_shared/citation_contract.py:454-597`).
Its strictest evidence tier is default-off and never reached by its own evidence
chain, so it is corroboration rather than proven behavior
(`workflows/agent_team/fast_reporter_v1_evidence.py:221-243`).
