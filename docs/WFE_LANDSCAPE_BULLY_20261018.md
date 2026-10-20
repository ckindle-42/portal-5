# Bully / Crogl landscape review (2026-10-18)

Read-only. Models the program actually wires, what 2025–2026 measurements say under the box (Apple Silicon, ≤ ~35 GB at 4-bit including KV, GGUF or MLX, prefer a release since about 2026-01), and whether the design assumptions still hold. No security-log or BOTS retrieval number was found for any model below. MTEB/BEIR/MMTEB are not that task.

Production today is `no_reader`. The engine does not issue a model verdict. `security-reviewer` chat (`granite4.1:8b-ctx8k`) only helps the analyst drive the tools. Propose uses EmbeddingGemma 2. `organ.recall()` does not rerank (`reranker_version=None`). The :8942 VL reranker is not on this path.

## Recommendation

| role | current | recommended | why (numbers + sources) | in backends.yaml? | size at Q4 | confidence |
|---|---|---|---|---|---|---|
| Embedder (propose) | `google/embeddinggemma-2`, :8946, 768-d, task `sentence similarity`, role query. Stamped on every real-corpus report. | Keep as the platform embedder. Do not cut over. First local check is the retrieval task-prefix on this same model. Text challenger, Bully shadow index only: `microsoft/harrier-oss-v1-0.6b` (already the retired :8917 default, not a new family). | Vendor card 2026-10-06: MTEB multilingual v2 mean 61.36, English v2 68.46, MTEB Code v1 nDCG@10 78.68. Independent MTEB run: not found (The Frontier 2026-10-06; 9io 2026-10-13). Same-metric vendor/leaderboard field is higher for text: Harrier-0.6B MMTEB v2 69.0 (HF card, 2026-03-30); Qwen3-Embedding-4B MMTEB mean 69.45 / retrieval 69.60 (KaLM card snapshot, CodeSOTA 2026-10-07) and MTEB(eng, v2) 74.61 (undominated.ai 2026-10-18). EG2 STS split: not found. Local cutover: not-worse than Qwen3-Embedding-0.6B on `bully_projection` (p=0.20, `embedding_candidates` note). mxfp8 vs :8946 bf16 cosine 0.9992, top-1 20/20 (`reports/embedding_consumers/RUNTIME.md`). Swapping the identity invalidates every conformal null, and T3 has zero paired slices, so a public text gap is not yet a Bully recall gap. | EG2 yes (`embedding_candidates`). Harrier no. Qwen3-Embedding-0.6B and -8B yes as candidates; -4B no. 8B is noted too large to co-reside. | EG2 Ollama mxfp8 1.4 GB (PHASE0, 2026-10-07). Harrier HF tree 1.21 GB (bf16-class, 2026-03-30). Q4 of a 0.6B embedder is unnecessary. | medium (keep). low (any swap) |
| Reranker | Not in the product. :8942 serves `Qwen3-VL-Embedding-2B-mxfp8` + `Qwen3-VL-Reranker-2B-mxfp8` for visual RAG. `qwen3-vl:32b` in backends.yaml is a different chat model. | Do not send Bully text through :8942. If a rerank stage is added after a paired slice exists, arm `Qwen3-Reranker-0.6B` (Apache, was loaded and never called on retired :8925, 2026-10-07). Skip the 4B/8B rerankers until 0.6B moves candidate recall. | Vendor, one table, top-100 from Qwen3-Embedding-0.6B (blog 2025-06-05, arXiv:2506.05176): MTEB-R 61.82 → 65.80 (0.6B reranker) → 69.76 (4B) → 69.02 (8B). MMTEB-R 64.64 → 66.36 / 72.74 / 72.94. MTEB-Code 75.41 → 73.42 / 81.20 / 81.22. 4B wins English and FollowIR (14.84 vs 8.05); 8B wins multilingual. Release is June 2025, before the 2026-01 preference; no newer Apache text reranker with a better same-harness number was found. VL-Reranker-2B vendor MMTEB retrieval 70.0 (HF README, ~2026-01-09) is a multimodal protocol. Independent text run, different harness: LightOn 2026-07-16, BM25 top-100, 11-dataset BEIR clean mean nDCG@10, Qwen3-VL-Reranker-2B 49.08 vs jina-reranker-m0 51.97. Jina’s own 2026 claim that a 0.6B listwise model edges Qwen3-Reranker-4B: license and an independent number were not verified. | VL reranker: not an Ollama id. `qwen3-vl:32b` yes, unused here. Qwen3-Reranker-0.6B no. | 2B mxfp8 weights not sized in PHASE0 (server RSS 163 MB excluding unified memory). Reranker-0.6B weight GB: not found (container was 21 MiB, model unloaded). | medium |
| Reader (comparator) | Off (`no_reader`). Designated reasoning seat `granite4.1:30b-ctx16k` → `granite-4.1-30b-4bit`. T3 probe: `reasoning_chars=0`. | When a paired slice exists, one reader: `Qwen3.8-27B` with thinking on (already probed, `reasoning_chars=161`, served `Qwen3.8-27B-oQ4e-mtp`). Use a short context bake (8k–16k). The ctx96k tag is the general-deep workspace, larger than 40 events. Do not turn the reader on before that slice and a fixed examined-count. | Granite 4.1 30B is no-think. Vendor HF card (page 2026-09-14): IFEval 89.65, BFCL v3 73.68, GPQA 45.76, MMLU 80.16. Secondary aggregator (Design for Online, AA refresh 2026-10-15): GPQA Diamond 48.1, IFBench 44.4. Qwen3.8-27B vendor table (Unsloth docs 2026-10-15, Qwen card): GPQA Diamond 89.2, IFBench 79.5, LiveCodeBench v6 90.3, SWE-bench Pro 61.7, vs Qwen3.6-27B 87.8 / 69.1 / 83.9 / 53.5. Released 2026-08-14, Apache 2.0, GGUF+MLX. Q4-vs-BF16 loss on those tasks: not found. Draw Things (quant vendor) reports BF16 GPQA 90.91 / IFEval 94.09; their sub-4-bit checkpoints drop, which is not a Q4_K_M measurement. Abliterated variants: do not inherit these scores. | Qwen3.8-27B yes (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k`, oMLX `Qwen3.8-27B-oQ4e-mtp`). Granite 4.1 30B yes. | Unsloth UD-Q4_K_M file 16.5 GB (HF, 2026-10-07). Reader KV at 40 events / 2048 tokens: not measured. 96k is the wrong budget for this role. Granite catalog figure ~17 GB Q4. | high that granite is the wrong reader. medium that Qwen3.8 is the right one |
| Challenger | Expert seat `Foundation-Sec-8B-Reasoning` Q8. T3 probe: `reasoning_chars=0`. Panel (granite 30B, Mistral-Small-3.2-24B, qwen3.6:27b): 1 of 3 reasoned (qwen3.6:27b only). | Do not adopt the panel. After the think channel is actually visible to the probe, challenger = Foundation-Sec-8B-Reasoning (silence only on independent agreement). Until then the only other probe-passing seat already on disk is `Qwen3.6-35B-A3B` (`reasoning_chars=478`). Same-family self-challenge is the weaker design (see AIDA below). | Foundation-Sec vendor (HF card + arXiv:2601.21051, 2026-01-28): CTI-MCQA 0.691, CTI-RCM 0.753, CTI-VSP 0.856, CTI-Reasoning 0.411, vs Llama-3.1-8B 0.607 / 0.531 / 0.811 / 0.335. CWE-Prediction 70.4% in the report. Independent CTI re-run: not found. Scores are this model’s, not Llama’s, and they assume the vendor think setup the probe did not observe. Mistral-Small-3.2 is a June 2025 instruct model and produced no reasoning. Public GPQA/IFBench for the 35B-A3B tag: not retrieved. | Foundation-Sec yes. Qwen3.6-35B-A3B yes. Mistral-Small-3.2 yes. | Foundation-Sec Q8 ~8.5 GB (catalog). 35B-A3B is 3B active, Q4 MoE, exact file GB not extracted; it is the seat that replaced a ~55 GB dense resident set on auto-data. | medium |
| Analyst chat | `security-reviewer` → `granite4.1:8b-ctx8k`. Not the judge. | Keep. No WFE instrument exists for this seat (census 2026-10-18). | Vendor BFCL v3 68.27 (HF card, 8B column). That is tool use, which is this seat’s job. It lost auto-documents to other models; that workload is not review. | yes | 8B Q4 file GB: not extracted | high (do not swap on public boards) |
| Classifier | No learned classifier in the product. `ActionClassifier` / behavior class are deterministic. `classify_vulnerability` (CIRCL RoBERTa) is not a review-MCP tool. The embedding anchor classifier lost to the LLM router (p=0.039) and was kept off EG2. | Do not add one. Similarity stays a null quantile plus a reader. | Program rule I-4 / I-7. No 2025–2026 result found that says a security text classifier should replace grounded reading. | n/a | n/a | high |

Harrier-27B (vendor MMTEB 74.3) and Qwen3-Embedding-8B (MMTEB 70.58, MTEB Code 80.68, both vendor) are the text quality ceiling. 27B bf16 is ~54 GB (secondary report of the HF weights) and does not fit beside a reader. The 8B embedder is already marked too large to co-reside. Neither is recommended.

## What the program uses

Propose: `PlatformEmbedder` at `review/service.py` calls :8946 with `Task.SENTENCE_SIMILARITY`. Identity stamped everywhere is `google/embeddinggemma-2;dim=768;task=sentence similarity;role=query`. Bully `Organ` (`EMBED_MODEL`) is the same model. Thresholds are benign-slice quantiles, refit when that identity changes (`review/calibration.py`, I-3).

Read: `review/reader.py` `resolve_candidate_models()` returns four seats. T3 probe stamp `41eaed5720a9844f` (commit `4a6eeb9ccd01`):

| role | served | reasoning |
|---|---|---|
| general_deep | `Qwen3.8-27B-oQ4e-mtp` | yes, 161 chars |
| general_fast | `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit` | yes, 478 chars |
| auto_security_reasoning | `granite-4.1-30b-4bit` | no |
| expert_role | Foundation-Sec-8B-Reasoning Q8 | no |
| panel qwen3.6:27b | `qwen3.6:27b-q4_K_M` | yes, 378 chars |
| panel mistral | Mistral-Small-3.2-24B-Instruct-2506-4bit | no |

`core_reasoning_candidate_rate` 0.5 (n=4). `panel_reasoning_seat_rate` 0.333 (n=3). `paired_truth_slice_yield` 0. `workload_B_available` 0. `alpha_open_available` 0. T6 (`725bebcc8911ba4b`): cousin recall 0 at n=1, `claim_proven_fraction` 0.25, processed corpus fraction 1.27e-5. The binding stage is unmeasured because every paired slice was excluded before the product ran.

Rerank history, not current architecture: 2026-10-07 PHASE0 found `mlx-community/Qwen3-Reranker-0.6B-mxfp8` on :8925 with zero rerank calls, and a retired Harrier server that was no longer listening. Harrier-0.6B had been the :8917 default (`ROADMAP.md` P5-FUT-EMBED-001). CHANGELOG 7.1.0 (2026-05-28) already recorded Harrier as competitive on the wider MTEB v2 field and EmbeddingGemma as best-in-class only under 500M. EG2 replaced that line as the one multimodal embedder (2026-10-06 release, cut over 2026-10-08). B1.4 compared EG2 distance bands with old Harrier constants; that is not a recall bake-off.

## Evidence

### Embedders

Same-harness text field, MMTEB / MTEB v2 mean(task), unless noted. EG2 has no retrieval-only or STS split on the card.

| model | text number | retrieval / code | source | kind | date |
|---|---|---|---|---|---|
| EmbeddingGemma 2, 768-d, full precision | MMTEB v2 61.36; English v2 68.46 | Code v1 78.68 nDCG@10. At 256-d, English 67.78, Code 76.18 (card via 9io). At 128-d, English 65.68, MMEB overall 45.65 | Google model card, cited by Google blog, MarkTechPost, 9io, CodeSOTA | vendor | 2026-10-06 |
| EmbeddingGemma 2 | — | — | The Frontier: no folder in the public MTEB results repo at check time. 9io: no independent eval found | independent absence | 2026-10-06 / 2026-10-13 |
| Harrier-OSS v1 0.6B | MMTEB v2 69.0 | retrieval split not on the card excerpt. 1024-d, 32k, MIT, instruction required | HF card `microsoft/harrier-oss-v1-0.6b` | vendor | released 2026-03-30 |
| Harrier-OSS v1 27B | 74.3 | — | same card. MTEB issue #4871 (2026-07-01): independent run started; 27B loader broken as of 2026-07-13 | vendor; independent not found | 2026-03-30 / 2026-07-13 |
| Qwen3-Embedding-0.6B | MMTEB 64.34; eng v2 70.47 | retrieval 64.65; Code 75.41; MTEB-R 61.82 | CodeSOTA 2026-10-07 (KaLM table); undominated.ai 2026-10-18; Qwen paper | leaderboard compilation + vendor | 2025-06-05 paper; boards 2026-10 |
| Qwen3-Embedding-4B | MMTEB 69.45; eng v2 74.61 | retrieval 69.60 | same | leaderboard compilation | 2026-10-07 / 2026-10-18 |
| Qwen3-Embedding-8B | MMTEB 70.58; eng v2 75.23 | retrieval 70.88; Code 80.68 | Qwen blog 2025-06-05 (70.58, 80.68); CodeSOTA; undominated.ai | vendor + leaderboard compilation | 2025-06-05 / 2026-10-18 |
| Qwen3-VL-Embedding-2B | — | MMTEB retrieval 68.1 (their protocol, not the text leaderboard) | HF README / arXiv:2601.04720 | vendor | ~2026-01-09 |

Local quantization: :8946 is bf16. fp16 NaNs (fact unit `unit-capability-eg2-embedding`). Ollama mxfp8 matches bf16 on the parity set (mean cosine 0.9992 text, 20/20 top-1). That is agreement with itself, not an MTEB delta. Q4 loss for EG2: not found. v1 QAT loss is not inherited.

Bully’s prefix is sentence similarity. The card’s retrieval and code numbers use a retrieval setup. A prefix A/B is the measurement that matches the code, and it needs no download.

### Rerankers

Vendor, one table (Qwen blog 2025-06-05 and arXiv:2506.05176). First stage is always Qwen3-Embedding-0.6B top-100. Metric is the retrieval subset, not the full MTEB mean.

| model | MTEB-R (eng) | MMTEB-R | MTEB-Code | FollowIR |
|---|---|---|---|---|
| embedder 0.6B only | 61.82 | 64.64 | 75.41 | 5.09 |
| Reranker-0.6B | 65.80 | 66.36 | 73.42 | 5.41 |
| Reranker-4B | 69.76 | 72.74 | 81.20 | 14.84 |
| Reranker-8B | 69.02 | 72.94 | 81.22 | 8.05 |

0.6B reranker loses Code versus the embedder alone on this table (−1.99) and gains English retrieval (+3.98). 4B is the English/instruction pick and is a June 2025 4B cross-encoder: bf16 is ~8 GB, Q4 unpublished. It fits, but it is the wrong first spend while candidate recall is unmeasured and the 0.6B weights were already on the machine.

VL-Reranker-2B, vendor, candidates from VL-Embedding-2B: MMTEB retrieval 70.0 vs the embedder’s 68.1; MMEB-v2 retrieval avg 75.1; ViDoRe v3 60.8. Independent text BEIR (LightOn, 2026-07-16, BM25 top-100): clean mean 49.08, behind jina-reranker-m0 at 51.97. jina-reranker-m0 is not recommended here; the commercial-license check was not completed, and the result is only a reason to keep the VL model off the text funnel.

Security, log, CTI, or code-as-commands retrieval for any reranker: not found.

### Readers

| model | number | source | kind | fits / probe |
|---|---|---|---|---|
| Granite 4.1 30B | IFEval 89.65, BFCL v3 73.68, GPQA 0-shot CoT 45.76, HumanEval 88.41 | HF `ibm-granite/granite-4.1-30b` | vendor | yes, ~17 GB Q4. Probe: no reasoning |
| Granite 4.1 30B | GPQA Diamond 48.1, IFBench 44.4, τ²-bench 42.1 | Design for Online citing Artificial Analysis, refresh 2026-10-15 | secondary compilation | same |
| Granite 4.1 8B | BFCL v3 68.27, IFEval 87.06 | same HF card | vendor | yes. Not the judge |
| Qwen3.8-27B | GPQA Diamond 89.2, IFBench 79.5, LiveCodeBench v6 90.3, SWE-bench Pro 61.7, Terminal-Bench 2.1 73.0 | Qwen comparison table via Unsloth docs, 2026-10-15 | vendor | UD-Q4_K_M 16.5 GB. Probe: reasoning on |
| Qwen3.6-27B | GPQA 87.8, IFBench 69.1, LCB v6 83.9, SWE-bench Pro 53.5 | same table, predecessor column | vendor | Probe: reasoning on. Census already flags the +10.4 IFBench same-card gap |
| Foundation-Sec-8B-Reasoning | CTI-MCQA 0.691, CTI-RCM 0.753, CTI-VSP 0.856, CTI-Reasoning 0.411; CWE-Prediction 0.704 | HF card 2026-01-28; arXiv:2601.21051 | vendor | Q8 ~8.5 GB. Probe: reasoning not observed |
| Qwen3.6-35B-A3B | — | not retrieved | — | Probe: reasoning on |

No independent LiveBench / Artificial Analysis primary page was opened for Qwen3.8; the AA figures above are for Granite only, via a secondary page. Do not treat the Qwen table as a leaderboard rank. It is one vendor running several of its own models plus published comparators.

Foundation-Sec is the only cyber-specific reader with a cited CTI suite. CTI-Bench is multiple-choice and CVE→CWE mapping, not “read these 40 events and say something / nothing / unsure.” A high CTI-RCM does not answer T3. The probe failure blocks it as the reader until think tokens survive the pipeline. It remains the right challenger family because it is a different training line, small enough to sit beside Qwen3.8 (16.5 + 8.5 GB), and its card is about evidence-like security judgments.

## Design assumptions

**Reading is the comparator (I-7).** Still supported, and the current `no_reader` default is the honest state until the preconditions exist. Arithmetic distance is the wrong verdict: the program’s own history is that fitted thresholds absorbed embedder scale. External evidence agrees that an LLM verdict without a retrieved record becomes a dismissal. arXiv:2610.10608 (2026-10-07, single study, not replicated) replayed 1,247 alerts through a live SIEM. Every tool-using strategy missed at least 40.4% of attack alerts. Empty search was followed by dismissal. Same-context self-review had negative net correction. Their AIDA setup (a proposed decision, then an independent challenge, stricter evidence before dismissal) reported F1 0.958 against 0.371–0.744, false negatives 40.4% → 3.1%, with 18.4% of alerts escalated. That is the program’s shape: code proposes, one reader, a real challenger required to silence, grounding before a claim counts, `unsure` left for the analyst. It argues against the three-seat panel that includes two seats which do not reason. It does not argue for turning the reader on while `paired_truth_slice_yield` is 0.

**Conformal nulls (I-3).** Supported as the false-alarm control. Not supported as a one-time fit. Coverage needs the future benign window to be exchangeable with the calibration slice. 2025–2026 IDS work treats that as false under drift and uses a sliding calibration set plus a drift test (FIRCE, arXiv:2605.01962, 2026-05-03; FADES, Electronics 2026-05-13, the journal extension; conformal anomaly detection with a sliding window, Reliability Engineering & System Safety, 2026-10). C-PP-COAD (arXiv:2505.01783, submitted 2025-05, revised 2026-08) wraps any anomaly score with online conformal p-values aimed at FDR control when calibration labels are scarce; numeric IDS deltas were not extracted. Journal of Information Security and Applications, 2025-09 (10.1016/j.jisa.2025.104120): conformal pseudo-labels were inconsistent on cybersecurity sets, and a larger drift cut the gain. That argues against writing analyst-free labels back into the model. The program already does the right two things (quantile, not a fitted constant; analyst verdict outranks the reader; refit when the embedder identity changes) and misses the third (refresh the benign slice when the traffic shifts, not only when the model id changes). Mondrian grouping by channel and level is already in the calibration key; keep it. Per-source coverage is the known hole in a single global quantile.

**Candidate recall.** Supported, and it is the unbound constraint. A reader cannot recover a cousin that never entered its budget. T6’s cousin recall is 0 at n=1, and T2/T3 never produced the recall-versus-alpha curve (`alpha_open_available` 0). Public retrieval work says the points after a decent embedder are in the top-100 rerank (+4 nDCG English for the 0.6B reranker on Qwen’s table, +8 for the 4B) and in a lexical/entity channel beside the dense score. Security telemetry is entity-heavy (host, user, hash, command line). No MTEB number measures that. The program’s table-free rule still holds for curated behavior tables. It does not forbid an entity pivot whose keys are the event’s own fields. `artifact_graph` already builds those edges with a deterministic classifier. The propose stage should be scored only on recall into the reader budget, which is what the program says, and which has not been measured on a `real:` paired slice.

**Analyst workload B.** Supported, and unset. The headline “cousin recall at budget B” matches both the AIDA escalation cap (18.4% handed to a person) and the 2026 SOC load descriptions (Vectra figure 2,992 alerts/team/day with 63% unaddressed; Microsoft/Omdia ~46% false positives; both via Secure.com 2026-10-14, secondary). B cannot be tuned until T1 records it. A proxy that does not invent B: cap examined events, which the reader already records (`evidence_shown` / `evidence_total`, `MAX_EVENTS` 40). Do not fit a threshold to a headline F1.

## Cheapest local check

No new WFE suite. The census (2026-10-18) lists `security-reviewer` under “no instrument.” The instruments that exist are the review stamps.

1. Prefix, same embedder, no download. On the next eligible paired slice only: candidate recall at the reader budget, `sentence similarity` versus the retrieval/search prefix, dim 768, alpha untouched. Stop if no paired slice (current yield is 0). That is `review_eval` attribution, not a new harness.
2. Shadow embedder, one slice. Harrier-0.6B versus EG2, same prefix choice as (1), recall at budget only. Harrier is not in `backends.yaml`; weights were the old :8917 default. Refit the null for that identity inside the arm. Do not repoint :8946. Platform consumers (memory, OWUI RAG, compliance) stay on EG2.
3. Rerank arm, only if (1) shows the cousin in a wide candidate list and missing from the budget. Qwen3-Reranker-0.6B on those candidates. The VL server stays out of the arm.
4. Reader arm, only after (1) and a non-zero candidate recall. One concern, two calls: Qwen3.8-27B think on, then Foundation-Sec only if a fresh reasoning probe shows `reasoning_chars>0`. Score cousin recall among concerns the analyst would see at a fixed examined-count, against the deterministic arm. Do not run the three-seat panel. Do not start this while another eval is on the GPU.
5. Drift, no model. Recompute the benign quantile on a later benign window of the same index and report the shift. That is the conformal assumption. No download.

## Sources

Vendor or vendor table:

- Google, EmbeddingGemma 2, 2026-10-06. https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/
- Model card figures as republished with the English/MRL splits: https://9io.ai/blog/embeddinggemma-2-multimodal-search (2026-10-13); https://www.marktechpost.com/2026/10/06/google-deepmind-releases-embeddinggemma-2-a-740m-open-multimodal-embedding-model-built-on-gemma-4/ (2026-10-06); https://www.codesota.com/benchmarks/mteb (checked 2026-10-07)
- Qwen embedding and reranker blog, 2025-06-05. https://qwenlm.github.io/blog/qwen3-embedding/ and arXiv:2506.05176
- Qwen3-VL-Reranker README / arXiv:2601.04720. https://huggingface.co/Qwen/Qwen3-VL-Reranker-2B and https://arxiv.org/html/2601.04720
- Harrier card. https://huggingface.co/microsoft/harrier-oss-v1-0.6b (released 2026-03-30)
- Granite 4.1 30B card. https://huggingface.co/ibm-granite/granite-4.1-30b (page dated 2026-09-14)
- Qwen3.8 table via Unsloth, 2026-10-15. https://unsloth.ai/docs/models/qwen3.8 and GGUF sizes https://huggingface.co/unsloth/Qwen3.8-27B-GGUF (2026-10-07). Release context: https://metallab.ai/en/2026/8/qwen3-8-27b-open-weights-local-run (2026-08-14)
- Foundation-Sec-8B-Reasoning card, 2026-01-28. https://huggingface.co/fdtn-ai/Foundation-Sec-8B-Reasoning and arXiv:2601.21051

Independent, compilation, or single-lab (not the vendor’s card):

- Absence of an EG2 MTEB submission: https://www.thefrontier.dev/articles/embeddinggemma-2-apache-multimodal-embeddings (2026-10-06); 9io as above (2026-10-13)
- MTEB(eng, v2) compilation: https://undominated.ai/embeddings/ (2026-10-18). Qwen3-Embedding-8B 75.23, 4B 74.61, 0.6B 70.47. EG2 not listed
- LightOn BEIR text run of Qwen3-VL-Reranker-2B: https://huggingface.co/blog/lightonai/lighton-rerank (2026-07-16)
- MTEB reproduction request for Harrier, unresolved for 27B: https://github.com/embeddings-benchmark/mteb/issues/4871 (2026-07-01)
- SOC investigation failures: https://arxiv.org/abs/2610.10608 (2026-10-07)
- Conformal IDS / drift: https://arxiv.org/abs/2505.01783 (2025-05, rev 2026-08); https://arxiv.org/html/2605.01962v1 (2026-05-03); https://www.mdpi.com/2079-9292/15/10/2114 (2026-05-13); JISA https://doi.org/10.1016/j.jisa.2025.104120 (2025-09)
- SOC survey, no operational number used: https://arxiv.org/abs/2509.10858 (2025-09-13)
- Alert-volume figures, secondary: https://www.secure.com/blog/cybersecurity/ai-soc-analyst-tasks (2026-10-14)
- Granite AA compilation, secondary: https://designforonline.com/ai-models/ibm-granite-4-1-30b/ (AA refresh cited 2026-10-15)

Local, already stamped (not re-run):

- T3 probe `reports/review_eval/41eaed5720a9844f/t3_prerequisites.json`
- T6 `docs/BULLY_REVIEW_STATE.md` stamp `725bebcc8911ba4b`
- EG2 parity `reports/embedding_consumers/RUNTIME.md`; PHASE0 `reports/embedding_consumers/PHASE0_LIVE_TRUTH.md` (2026-10-07)
- Fact units: `unit-capability-eg2-embedding`, `unit-known-limitations-vl-retrieval-runtime`, `unit-capability-review`
- Seat census `docs/WFE_SEAT_EVIDENCE_CENSUS_20261018.md`

## RESULT
done

## WHAT CHANGED
`landscape_bully.md`: landscape review of the Bully reviewer models and the four design assumptions. No other file edited. Stack not called. Nothing committed.

## EVIDENCE
Repo reads: `docs/BULLY_REVIEW_PROGRAM.md`, `docs/BULLY_REVIEW_STATE.md`, `portal/modules/security/core/review/reader.py`, `review/embedding.py`, `review/service.py` (`Task.SENTENCE_SIMILARITY`), `bully/organ.py` (`EMBED_MODEL`, recall does not rerank), `config/portal.yaml` seats, `config/backends.yaml` `embedding_candidates`, T3 probe JSON, `reports/embedding_consumers/RUNTIME.md` and `PHASE0_LIVE_TRUTH.md`, census. Wiki: `unit-capability-eg2-embedding`, `unit-known-limitations-vl-retrieval-runtime`, `unit-capability-review`.

Web sources used in the table: 14 vendor/card pages, 10 independent or third-party (including two that report an independent number as absent), plus the local stamps. Security-log retrieval numbers: 0 found. Qwen3.8 Q4-vs-BF16 loss: not found. Foundation-Sec independent CTI: not found.

## OPEN / RISK
T3 never ran a reader, so the Qwen3.8 recommendation is “what to arm,” not a claim it raises cousin recall. Harrier’s 69.0 and EG2’s 61.36 are different submissions of MMTEB-style means, not one harness this review re-ran. The Foundation-Sec probe failure may be pipeline think-stripping rather than the model; the report treats the probe as the contract. Per-commit unit gate not run: the brief is read-only and the only write is this file.
