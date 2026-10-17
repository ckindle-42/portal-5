# WFE surface audit, 2026-10-17 (S1)

`scripts/wfe_surface_audit.py` finds the five defect classes the documents slice found one at a
time, across every workspace and MCP. Re-run it with `uv run python scripts/wfe_surface_audit.py
--md <file>`; exit 0 means no unreviewed finding.

## What it found and what was done

| Class | Finding | Disposition |
|---|---|---|
| 1 prompt does not name a tool | general-fast and general-deep named `read_excel` only | fixed: pipeline-side `system_prompt_append` naming their document tools (1ff032be) |
| 1 | auto-daily (8192-token window), and incidental read/CAD/sandbox tools in code, compliance, nemotron and CAD lanes | justified in the script, with the reason; auto-daily waits for the S2 P-4 measurement |
| 2 manifest schema | create_excel required `title` but never defined it (548576e5); create_powerpoint `slides` had no item keys (593db5db); whisper advertised `audio_path` while the function takes `file_path` (7d79b369); create_excel and create_word_document array items undefined | all fixed; a test holds every document manifest to its function signature |
| 3 unknown arguments | the whisper dispatcher filtered unknown keys and ran the call, so `audio_path` transcribed the latest upload instead of the named file (7d79b369); create_* tools silently dropped unknown nested keys (2244ad6b) | both reject with a structured error naming the accepted keys; a static scan fails if any dispatcher filters again |
| 4 prompt cross-talk | the documents prompt told the seat to ALWAYS give a download link, so reads got a made-up link (2f137fa8) | fixed; four remaining hits reviewed, none tied to a tool result |
| 5 delivery drift | live presets were stale after prompt edits because `seed` skips existing presets (ff4dd222); the persona stale-preset case `bench-qwen36-abl-27b`; 21 orphan presets with no source file | drift check at sync-config now covers workspaces and personas; the stale persona and 21 Portal-generated orphans (`bench-*`, `test-*`) deleted and reseeded; two orphans kept for the operator (`cadquerydesigner`, `transcriptanalyst`); 11 personas share a workspace id and are never seeded (information) |

## Serving: the 8b seat shadow

The oMLX `granite-4.1-8b-mxfp8` conversion emitted U+200B inside paths and mangled names when
tools were in the request (see the KNOWN_LIMITATIONS entry OMLX-GRANITE-8B-MXFP8-GARBLE-001 and
`scripts/wfe_garble_probe.py`). The `granite4.1:8b-ctx16k` seat is no longer aliased onto it in
`omlx-general` or `omlx-reasoning` (2244ad6b, 227bc615). The `8b-ctx8k` alias stays: probed 10/10
clean with tools-specialist's, security-reviewer's and auto-security's own tool sets and with no
tools, and a test pins the allowed set.

Serving impact checked in real Open WebUI turns: auto-video and auto-image now load
`granite4.1:8b-ctx16k` on Ollama (6.5 GB at a 16384 window); the 2K router stays resident; 84%
of memory free afterwards.

## Production behaviours found by probing the real path (documents)

- Open WebUI injects an attached file's extracted text into the user message, and the seat
  sometimes answers from it without calling a read tool; when it does call, it passes the
  resource-id (`read_*` now resolves an id to the stored `<id>_<name>` upload, f17d4521).
- A prompt edit reaches users only after `./launch.sh reseed`; a pipeline-side
  `system_prompt_append` does not need it.
- Under an evaluation scope a refused read returns HTTP 403 rather than the structured
  `success:false` error.

## Tables


## Class 1: tool not named in the prompt

Counts: info 194, justified 15

| subject | severity | detail |
|---|---|---|
| auto-bigfix / execute_bash | info | prompt is silent on this tool family |
| auto-bigfix / execute_python | info | prompt is silent on this tool family |
| auto-bigfix / web_search | info | prompt is silent on this tool family |
| auto-cad / cad_render | info | described by its words, not named |
| auto-cad / convert_cad | justified | prompt covers other cad_render_mcp tools, not this one / reason: self-describing utility tool in a lane whose prompt is about CAD or code |
| auto-cad / execute_bash | info | described by its words, not named |
| auto-cad / kb_search | info | prompt is silent on this tool family |
| auto-cad / read_pdf | info | prompt is silent on this tool family |
| auto-cad / read_word_document | info | prompt is silent on this tool family |
| auto-cad / recall | info | prompt is silent on this tool family |
| auto-cad / remember | info | prompt is silent on this tool family |
| auto-cad / render_mesh | info | described by its words, not named |
| auto-cad / sandbox_status | justified | prompt covers other code_sandbox_mcp tools, not this one / reason: self-describing utility tool in a lane whose prompt is about CAD or code |
| auto-cad / web_fetch | info | prompt is silent on this tool family |
| auto-cad / web_search | info | prompt is silent on this tool family |
| auto-coding / execute_bash | info | described by its words, not named |
| auto-coding / execute_nodejs | info | described by its words, not named |
| auto-coding / execute_python | info | described by its words, not named |
| auto-coding / read_pdf | justified | prompt covers other document_mcp tools, not this one / reason: document reading is incidental in a non-document lane; the tool description carries it |
| auto-coding / read_word_document | info | described by its words, not named |
| auto-coding / recall | info | prompt is silent on this tool family |
| auto-coding / remember | info | prompt is silent on this tool family |
| auto-coding / sandbox_status | justified | prompt covers other code_sandbox_mcp tools, not this one / reason: self-describing utility tool in a lane whose prompt is about CAD or code |
| auto-compliance / check_kev | info | prompt is silent on this tool family |
| auto-compliance / compliance_answers | info | described by its words, not named |
| auto-compliance / compliance_compare | info | described by its words, not named |
| auto-compliance / compliance_conflicts | info | described by its words, not named |
| auto-compliance / compliance_correct | info | described by its words, not named |
| auto-compliance / compliance_draft_revisions | info | described by its words, not named |
| auto-compliance / compliance_flexibility | info | described by its words, not named |
| auto-compliance / compliance_ingest | info | described by its words, not named |
| auto-compliance / compliance_intentionality | info | described by its words, not named |
| auto-compliance / compliance_mappings | info | described by its words, not named |
| auto-compliance / compliance_note | info | described by its words, not named |
| auto-compliance / compliance_orphans | info | described by its words, not named |
| auto-compliance / compliance_review_decide | info | described by its words, not named |
| auto-compliance / compliance_scope | info | described by its words, not named |
| auto-compliance / compliance_sources | info | described by its words, not named |
| auto-compliance / compliance_standing_questions | info | described by its words, not named |
| auto-compliance / compliance_trace | info | described by its words, not named |
| auto-compliance / create_word_document | info | described by its words, not named |
| auto-compliance / get_epss | info | prompt is silent on this tool family |
| auto-compliance / ics_advisories | info | prompt is silent on this tool family |
| auto-compliance / kb_list | info | prompt is silent on this tool family |
| auto-compliance / kb_search | info | prompt is silent on this tool family |
| auto-compliance / lookup_control | info | prompt is silent on this tool family |
| auto-compliance / lookup_cve | info | prompt is silent on this tool family |
| auto-compliance / map_frameworks | info | described by its words, not named |
| auto-compliance / patch_evidence | info | prompt is silent on this tool family |
| auto-compliance / read_pdf | justified | prompt covers other document_mcp tools, not this one / reason: document reading is incidental in a non-document lane; the tool description carries it |
| auto-compliance / refresh_catalogs | info | prompt is silent on this tool family |
| auto-compliance / scan_dependencies | info | prompt is silent on this tool family |
| auto-compliance / search_controls | info | prompt is silent on this tool family |
| auto-compliance / triage_cve | info | prompt is silent on this tool family |
| auto-daily / create_excel | justified | prompt covers other document_mcp tools, not this one / reason: 8192-token window: any prompt addition needs the S2 P-4 measurement first |
| auto-daily / create_powerpoint | justified | prompt covers other document_mcp tools, not this one / reason: 8192-token window: any prompt addition needs the S2 P-4 measurement first |
| auto-daily / create_word_document | info | described by its words, not named |
| auto-daily / execute_python | info | prompt is silent on this tool family |
| auto-daily / kb_list | info | prompt is silent on this tool family |
| auto-daily / kb_search | info | prompt is silent on this tool family |
| auto-daily / minimax_generate | info | prompt is silent on this tool family |
| auto-daily / minimax_status | info | prompt is silent on this tool family |
| auto-daily / read_excel | justified | prompt covers other document_mcp tools, not this one / reason: 8192-token window: any prompt addition needs the S2 P-4 measurement first |
| auto-daily / read_pdf | justified | prompt covers other document_mcp tools, not this one / reason: 8192-token window: any prompt addition needs the S2 P-4 measurement first |
| auto-daily / read_word_document | info | described by its words, not named |
| auto-daily / recall | info | prompt is silent on this tool family |
| auto-daily / remember | info | prompt is silent on this tool family |
| auto-daily / transcribe_audio | info | prompt is silent on this tool family |
| auto-daily / web_fetch | info | prompt is silent on this tool family |
| auto-daily / web_search | info | prompt is silent on this tool family |
| auto-data / attach_source | info | prompt is silent on this tool family |
| auto-data / create_excel | info | prompt is silent on this tool family |
| auto-data / execute_python | info | prompt is silent on this tool family |
| auto-data / kb_search | info | prompt is silent on this tool family |
| auto-data / list_session | info | prompt is silent on this tool family |
| auto-data / profile_table | info | prompt is silent on this tool family |
| auto-data / run_sql | info | prompt is silent on this tool family |
| auto-documents / create_excel | info | described by its words, not named |
| auto-documents / create_powerpoint | info | described by its words, not named |
| auto-documents / create_word_document | info | described by its words, not named |
| auto-general-uncensored / execute_bash | info | prompt is silent on this tool family |
| auto-general-uncensored / execute_python | info | prompt is silent on this tool family |
| auto-general-uncensored / read_pdf | info | prompt is silent on this tool family |
| auto-general-uncensored / read_word_document | info | prompt is silent on this tool family |
| auto-general-uncensored / recall | info | prompt is silent on this tool family |
| auto-general-uncensored / remember | info | prompt is silent on this tool family |
| auto-music / minimax_models | info | described by its words, not named |
| auto-nemotron / kb_list | info | prompt is silent on this tool family |
| auto-nemotron / kb_search | info | prompt is silent on this tool family |
| auto-nemotron / read_pdf | justified | prompt covers other document_mcp tools, not this one / reason: document reading is incidental in a non-document lane; the tool description carries it |
| auto-nemotron / read_word_document | info | described by its words, not named |
| auto-nemotron / recall | info | prompt is silent on this tool family |
| auto-nemotron / remember | info | prompt is silent on this tool family |
| auto-nemotron / web_fetch | info | prompt is silent on this tool family |
| auto-nemotron / web_search | info | prompt is silent on this tool family |
| auto-research / entity_timeline | info | prompt is silent on this tool family |
| auto-research / graph_recall | info | prompt is silent on this tool family |
| auto-research / kb_list | info | prompt is silent on this tool family |
| auto-research / kb_search | info | prompt is silent on this tool family |
| auto-research / kb_search_all | info | prompt is silent on this tool family |
| auto-research / neighbors | info | prompt is silent on this tool family |
| auto-research / news_search | info | prompt is silent on this tool family |
| auto-research / recall | info | prompt is silent on this tool family |
| auto-research / remember | info | prompt is silent on this tool family |
| auto-research / web_fetch | info | prompt is silent on this tool family |
| auto-research / web_search | info | prompt is silent on this tool family |
| auto-security / asset_inventory | info | prompt is silent on this tool family |
| auto-security / check_kev | info | prompt is silent on this tool family |
| auto-security / classify_vulnerability | info | described by its words, not named |
| auto-security / correlate_advisories | info | prompt is silent on this tool family |
| auto-security / dissect_pcap | info | prompt is silent on this tool family |
| auto-security / execute_bash | info | prompt is silent on this tool family |
| auto-security / execute_python | info | prompt is silent on this tool family |
| auto-security / get_epss | info | prompt is silent on this tool family |
| auto-security / ics_advisories | info | prompt is silent on this tool family |
| auto-security / kb_list | info | prompt is silent on this tool family |
| auto-security / kb_search | info | prompt is silent on this tool family |
| auto-security / list_ics_protocols | info | prompt is silent on this tool family |
| auto-security / lookup_cve | info | prompt is silent on this tool family |
| auto-security / lookup_ioc | info | prompt is silent on this tool family |
| auto-security / scan_dependencies | info | prompt is silent on this tool family |
| auto-security / triage_cve | info | prompt is silent on this tool family |
| auto-security / web_fetch | info | described by its words, not named |
| auto-spl / asset_inventory | info | prompt is silent on this tool family |
| auto-spl / check_kev | info | prompt is silent on this tool family |
| auto-spl / classify_vulnerability | info | prompt is silent on this tool family |
| auto-spl / compile_yara | info | prompt is silent on this tool family |
| auto-spl / conversations | info | prompt is silent on this tool family |
| auto-spl / convert_sigma | info | prompt is silent on this tool family |
| auto-spl / correlate_advisories | info | prompt is silent on this tool family |
| auto-spl / dissect_pcap | info | prompt is silent on this tool family |
| auto-spl / extract_fields | info | prompt is silent on this tool family |
| auto-spl / get_epss | info | prompt is silent on this tool family |
| auto-spl / ics_advisories | info | prompt is silent on this tool family |
| auto-spl / kb_list | info | prompt is silent on this tool family |
| auto-spl / kb_search | info | prompt is silent on this tool family |
| auto-spl / list_ics_protocols | info | prompt is silent on this tool family |
| auto-spl / lookup_cve | info | prompt is silent on this tool family |
| auto-spl / lookup_ioc | info | prompt is silent on this tool family |
| auto-spl / protocol_hierarchy | info | prompt is silent on this tool family |
| auto-spl / query_splunk | info | described by its words, not named |
| auto-spl / query_windows_events | info | prompt is silent on this tool family |
| auto-spl / scan_dependencies | info | prompt is silent on this tool family |
| auto-spl / scan_yara | info | prompt is silent on this tool family |
| auto-spl / triage_cve | info | prompt is silent on this tool family |
| auto-spl / validate_sigma | info | prompt is silent on this tool family |
| auto-uncensored-throwaway / execute_bash | info | prompt is silent on this tool family |
| auto-uncensored-throwaway / execute_python | info | prompt is silent on this tool family |
| auto-uncensored-throwaway / news_search | info | prompt is silent on this tool family |
| auto-uncensored-throwaway / recall | info | prompt is silent on this tool family |
| auto-uncensored-throwaway / remember | info | prompt is silent on this tool family |
| auto-uncensored-throwaway / web_fetch | info | prompt is silent on this tool family |
| auto-uncensored-throwaway / web_search | info | prompt is silent on this tool family |
| auto-vision / transcribe_audio | info | prompt is silent on this tool family |
| bench-qwen36-cad / convert_cad | justified | prompt covers other cad_render_mcp tools, not this one / reason: self-describing utility tool in a lane whose prompt is about CAD or code |
| bench-qwen36-cad / execute_bash | justified | prompt covers other code_sandbox_mcp tools, not this one / reason: self-describing utility tool in a lane whose prompt is about CAD or code |
| bench-qwen36-cad / execute_python | info | described by its words, not named |
| bench-qwen36-cad / kb_search | info | prompt is silent on this tool family |
| bench-qwen36-cad / read_pdf | info | prompt is silent on this tool family |
| bench-qwen36-cad / read_word_document | info | prompt is silent on this tool family |
| bench-qwen36-cad / recall | info | prompt is silent on this tool family |
| bench-qwen36-cad / remember | info | prompt is silent on this tool family |
| bench-qwen36-cad / render_mesh | info | described by its words, not named |
| bench-qwen36-cad / sandbox_status | justified | prompt covers other code_sandbox_mcp tools, not this one / reason: self-describing utility tool in a lane whose prompt is about CAD or code |
| bench-qwen36-cad / web_fetch | info | prompt is silent on this tool family |
| bench-qwen36-cad / web_search | info | prompt is silent on this tool family |
| bench-qwen38-cad / cad_render | info | described by its words, not named |
| bench-qwen38-cad / convert_cad | justified | prompt covers other cad_render_mcp tools, not this one / reason: self-describing utility tool in a lane whose prompt is about CAD or code |
| bench-qwen38-cad / execute_bash | info | described by its words, not named |
| bench-qwen38-cad / kb_search | info | prompt is silent on this tool family |
| bench-qwen38-cad / read_pdf | info | prompt is silent on this tool family |
| bench-qwen38-cad / read_word_document | info | prompt is silent on this tool family |
| bench-qwen38-cad / recall | info | prompt is silent on this tool family |
| bench-qwen38-cad / remember | info | prompt is silent on this tool family |
| bench-qwen38-cad / render_mesh | info | described by its words, not named |
| bench-qwen38-cad / sandbox_status | justified | prompt covers other code_sandbox_mcp tools, not this one / reason: self-describing utility tool in a lane whose prompt is about CAD or code |
| bench-qwen38-cad / web_fetch | info | prompt is silent on this tool family |
| bench-qwen38-cad / web_search | info | prompt is silent on this tool family |
| compliance-reading / compliance_answers | info | described by its words, not named |
| compliance-reading / compliance_correct | info | described by its words, not named |
| compliance-reading / compliance_note | info | described by its words, not named |
| compliance-reading / compliance_review_decide | info | described by its words, not named |
| compliance-reading / compliance_review_decide_batch | info | described by its words, not named |
| compliance-reading / compliance_review_list | info | described by its words, not named |
| compliance-reading / compliance_sources | info | described by its words, not named |
| compliance-reading / compliance_standing_questions | info | described by its words, not named |
| compliance-reading / compliance_timeline | info | described by its words, not named |
| general-deep / kb_list | info | prompt is silent on this tool family |
| general-deep / kb_search | info | prompt is silent on this tool family |
| general-deep / recall | info | prompt is silent on this tool family |
| general-deep / remember | info | prompt is silent on this tool family |
| general-deep / web_fetch | info | prompt is silent on this tool family |
| general-deep / web_search | info | prompt is silent on this tool family |
| general-fast / kb_list | info | prompt is silent on this tool family |
| general-fast / kb_search | info | prompt is silent on this tool family |
| general-fast / recall | info | prompt is silent on this tool family |
| general-fast / remember | info | prompt is silent on this tool family |
| general-fast / web_fetch | info | prompt is silent on this tool family |
| general-fast / web_search | info | prompt is silent on this tool family |
| security-reviewer / review_cancel | info | described by its words, not named |
| security-reviewer / review_doctor | info | described by its words, not named |
| security-reviewer / review_queue | info | described by its words, not named |
| security-reviewer / review_result | info | described by its words, not named |
| security-reviewer / review_start | info | described by its words, not named |
| security-reviewer / review_status | info | described by its words, not named |
| security-reviewer / review_verdict | info | described by its words, not named |
| tools-specialist / execute_python | info | prompt is silent on this tool family |
| tools-specialist / recall | info | prompt is silent on this tool family |
| tools-specialist / remember | info | prompt is silent on this tool family |

## Class 2: manifest schema integrity

Counts: info 30

| subject | severity | detail |
|---|---|---|
| browser_mcp / browser_get_markdown | info | no function found to compare against |
| cad_render_mcp / cad_build | info | adapter: run by the build123d-mcp engine through b123d_bridge, which injects session and out_dir |
| cad_render_mcp / cad_execute | info | adapter: run by the build123d-mcp engine through b123d_bridge, which injects session and out_dir |
| cad_render_mcp / cad_finalize | info | adapter: run by the build123d-mcp engine through b123d_bridge, which injects session and out_dir |
| cad_render_mcp / cad_find_holes | info | adapter: run by the build123d-mcp engine through b123d_bridge, which injects session and out_dir |
| cad_render_mcp / cad_measure | info | adapter: run by the build123d-mcp engine through b123d_bridge, which injects session and out_dir |
| cad_render_mcp / cad_render | info | adapter: run by the build123d-mcp engine through b123d_bridge, which injects session and out_dir |
| cad_render_mcp / generate_part | info | function params not in the manifest: ['request_id'] |
| code_sandbox_mcp / execute_bash | info | adapter: REST endpoint accepts both `command` and `code` |
| memory_mcp / clear_memories | info | no function found to compare against |
| memory_mcp / entity_timeline | info | no function found to compare against |
| memory_mcp / forget | info | no function found to compare against |
| memory_mcp / graph_recall | info | no function found to compare against |
| memory_mcp / link | info | no function found to compare against |
| memory_mcp / list_memories | info | no function found to compare against |
| memory_mcp / neighbors | info | no function found to compare against |
| memory_mcp / recall | info | no function found to compare against |
| memory_mcp / remember | info | no function found to compare against |
| rag_mcp / kb_ingest | info | no function found to compare against |
| rag_mcp / kb_list | info | no function found to compare against |
| rag_mcp / kb_optimize | info | no function found to compare against |
| rag_mcp / kb_restore | info | no function found to compare against |
| rag_mcp / kb_search | info | no function found to compare against |
| rag_mcp / kb_search_all | info | no function found to compare against |
| rag_mcp / kb_versions | info | no function found to compare against |
| video_mlx_mcp / animate_image | info | function params not in the manifest: ['fps'] |
| video_mlx_mcp / generate_video | info | function params not in the manifest: ['fps'] |
| web_search_mcp / news_search | info | no function found to compare against |
| web_search_mcp / web_fetch | info | no function found to compare against |
| web_search_mcp / web_search | info | no function found to compare against |

## Class 3: unknown-argument handling (live)

Counts: info 4, ok 8, skipped 126

| subject | severity | detail |
|---|---|---|
| cad_render / cad_build | skipped | not a read-only tool: not called live |
| cad_render / cad_execute | skipped | not a read-only tool: not called live |
| cad_render / cad_finalize | skipped | not a read-only tool: not called live |
| cad_render / cad_find_holes | skipped | not a read-only tool: not called live |
| cad_render / cad_measure | skipped | not a read-only tool: not called live |
| cad_render / cad_render | skipped | not a read-only tool: not called live |
| cad_render / convert_cad | skipped | not a read-only tool: not called live |
| cad_render / generate_part | skipped | not a read-only tool: not called live |
| cad_render / generate_scad | skipped | not a read-only tool: not called live |
| cad_render / render_mesh | skipped | not a read-only tool: not called live |
| cad_render / render_openscad | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| compliance /  | skipped | not a read-only tool: not called live |
| data /  | skipped | not a read-only tool: not called live |
| data /  | skipped | not a read-only tool: not called live |
| data /  | skipped | not a read-only tool: not called live |
| data /  | skipped | not a read-only tool: not called live |
| detection /  | skipped | not a read-only tool: not called live |
| detection /  | skipped | not a read-only tool: not called live |
| detection /  | skipped | not a read-only tool: not called live |
| detection /  | skipped | not a read-only tool: not called live |
| detection /  | skipped | not a read-only tool: not called live |
| detection /  | skipped | not a read-only tool: not called live |
| detections / spl_diff_hypothesis | skipped | not a read-only tool: not called live |
| detections / spl_explain_detection | skipped | not a read-only tool: not called live |
| detections / spl_search_library | skipped | not a read-only tool: not called live |
| detections / spl_techniques_covered | skipped | not a read-only tool: not called live |
| detections / spl_validate_syntax | skipped | not a read-only tool: not called live |
| documents / convert_document | skipped | not a read-only tool: not called live |
| documents / create_excel | skipped | not a read-only tool: not called live |
| documents / create_powerpoint | skipped | not a read-only tool: not called live |
| documents / create_word_document | skipped | not a read-only tool: not called live |
| documents / export_pdf | skipped | not a read-only tool: not called live |
| documents / list_generated_files | ok | takes no arguments: nothing can be dropped |
| documents / prepare_embed_image | skipped | not a read-only tool: not called live |
| documents / read_excel | ok | extra key rejected with a structured error |
| documents / read_pdf | ok | extra key rejected with a structured error |
| documents / read_powerpoint | ok | extra key rejected with a structured error |
| documents / read_word_document | ok | extra key rejected with a structured error |
| execution / execute_bash | skipped | not a read-only tool: not called live |
| execution / execute_nodejs | skipped | not a read-only tool: not called live |
| execution / execute_powershell | skipped | not a read-only tool: not called live |
| execution / execute_python | skipped | not a read-only tool: not called live |
| execution / list_sessions | ok | takes no arguments: nothing can be dropped |
| execution / reset_session | skipped | not a read-only tool: not called live |
| execution / sandbox_status | skipped | not a read-only tool: not called live |
| icsot /  | skipped | not a read-only tool: not called live |
| icsot /  | skipped | not a read-only tool: not called live |
| icsot /  | skipped | not a read-only tool: not called live |
| icsot /  | skipped | not a read-only tool: not called live |
| memory | info | MCP unreachable or serves no /tools |
| mflux / edit_image | skipped | not a read-only tool: not called live |
| mflux / generate_image | skipped | not a read-only tool: not called live |
| mitre / mitre_data_sources_for_technique | skipped | not a read-only tool: not called live |
| mitre / mitre_detections_for_technique | skipped | not a read-only tool: not called live |
| mitre / mitre_technique_lookup | skipped | not a read-only tool: not called live |
| mitre / mitre_techniques_list | skipped | not a read-only tool: not called live |
| mlx_transcribe / transcribe_audio | skipped | not a read-only tool: not called live |
| mlx_transcribe / transcribe_with_speakers | skipped | not a read-only tool: not called live |
| music-minimax / minimax_generate | skipped | not a read-only tool: not called live |
| music-minimax / minimax_models | skipped | not a read-only tool: not called live |
| music-minimax / minimax_status | skipped | not a read-only tool: not called live |
| netforensics /  | skipped | not a read-only tool: not called live |
| netforensics /  | skipped | not a read-only tool: not called live |
| netforensics /  | skipped | not a read-only tool: not called live |
| netforensics /  | skipped | not a read-only tool: not called live |
| pipeline | info | MCP unreachable or serves no /tools |
| rag | info | MCP unreachable or serves no /tools |
| research | info | MCP unreachable or serves no /tools |
| review / review_cancel | skipped | not a read-only tool: not called live |
| review / review_doctor | skipped | not a read-only tool: not called live |
| review / review_explain | skipped | not a read-only tool: not called live |
| review / review_queue | skipped | not a read-only tool: not called live |
| review / review_result | skipped | not a read-only tool: not called live |
| review / review_start | skipped | not a read-only tool: not called live |
| review / review_status | skipped | not a read-only tool: not called live |
| review / review_verdict | skipped | not a read-only tool: not called live |
| security / classify_vulnerability | ok | extra key rejected with a structured error |
| security / lab_perception | skipped | not a read-only tool: not called live |
| tts / clone_voice | skipped | not a read-only tool: not called live |
| tts / list_voices | ok | takes no arguments: nothing can be dropped |
| tts / register_voice | skipped | not a read-only tool: not called live |
| tts / speak | skipped | not a read-only tool: not called live |
| video_mlx / animate_image | skipped | not a read-only tool: not called live |
| video_mlx / generate_video | skipped | not a read-only tool: not called live |
| vulnintel /  | skipped | not a read-only tool: not called live |
| vulnintel /  | skipped | not a read-only tool: not called live |
| vulnintel /  | skipped | not a read-only tool: not called live |
| vulnintel /  | skipped | not a read-only tool: not called live |
| vulnintel /  | skipped | not a read-only tool: not called live |
| vulnintel /  | skipped | not a read-only tool: not called live |
| vulnintel /  | skipped | not a read-only tool: not called live |
| whisper / transcribe_audio | skipped | not a read-only tool: not called live |
| whisper / transcribe_with_speakers | skipped | not a read-only tool: not called live |
| wiki / wiki_explain | skipped | not a read-only tool: not called live |
| wiki / wiki_get_unit | skipped | not a read-only tool: not called live |
| wiki / wiki_search | skipped | not a read-only tool: not called live |

## Class 4: prompt cross-talk

Counts: justified 4

| subject | severity | detail |
|---|---|---|
| auto-audio | justified | Either tool writes JSON, Markdown, and Word (.docx) files automatically and returns their download URLs — always surface the md_url and docx_url as cl / reason: conditioned on the transcription tools it follows: the URLs exist only after they ran |
| auto-compliance | justified | Do not use Full, Partial, None, or Ambiguous as a fixed output taxonomy; answer in prose with citations, uncertainty, and the closure receipt. / reason: an output-format rule, not tied to a tool's output |
| compliance-reading | justified | The answer's last section is always the citations. / reason: a citations rule and a rule against writing tool syntax in prose; neither names a tool result |
| compliance-reading | justified | The rest of your reply is prose for the analyst: NEVER write tool-call syntax in it — calls go through the tool mechanism, and markup in your answer i / reason: a citations rule and a rule against writing tool syntax in prose; neither names a tool result |

## Class 5: delivery drift

Counts: info 11, orphan 2

| subject | severity | detail |
|---|---|---|
| persona bench-gemma4-26b-optiq | info | slug is also a workspace id: never seeded |
| persona bench-gemma4-e4b-qat | info | slug is also a workspace id: never seeded |
| persona bench-glm | info | slug is also a workspace id: never seeded |
| persona bench-granite41-30b | info | slug is also a workspace id: never seeded |
| persona bench-granite41-8b | info | slug is also a workspace id: never seeded |
| persona bench-huihui-qwen36-27b | info | slug is also a workspace id: never seeded |
| persona bench-huihui-qwen36-35b-a3b | info | slug is also a workspace id: never seeded |
| persona bench-nex-n2-mini | info | slug is also a workspace id: never seeded |
| persona bench-omnicoder2 | info | slug is also a workspace id: never seeded |
| persona bench-qwen3-coder-30b | info | slug is also a workspace id: never seeded |
| persona bench-qwen35-abliterated | info | slug is also a workspace id: never seeded |
| preset cadquerydesigner | orphan | no source file; CAD 3D Designer |
| preset transcriptanalyst | orphan | no source file; Transcript Analyst |
