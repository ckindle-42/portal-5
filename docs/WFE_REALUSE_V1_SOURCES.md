# Real-use v1 source note

Access date for every page below: 2026-10-29.
Thirty-five scenarios. None were dropped. Categories the opened studies do not support were re-sourced, and two scenarios moved to a workspace whose tools can do the task.

## Studies opened

### OpenAI, How People Use ChatGPT (2025)

Chatterji, Cunningham, Deming, Hitzig, Ong, Shan, and Wadman, NBER Working Paper 34255, 15 September 2025. DOI 10.3386/w34255.
Blog: https://openai.com/index/how-people-are-using-chatgpt/
PDF: https://cdn.openai.com/pdf/a253471f-8260-40c6-a2cc-aa93fe9f142e/economic-research-chatgpt-usage-paper.pdf
The PDF was downloaded and the text extracted with pdfminer (113,120 characters). Quotes below are from that text.

- Practical Guidance, Seeking Information, and Writing collectively account for about 77% of conversations (the introduction says nearly 80%). Practical Guidance stayed at roughly 29%. Writing fell from 36% in July 2024 to 24% a year later. Seeking Information grew from 14% to 24%. Technical Help fell from 12% to around 5%. Multimedia grew from 2% to just over 7%.
- Writing is 40% of work-related messages. About two-thirds of Writing messages ask the model to modify user text (editing, critiquing, translating) rather than create new text. The introduction also lists editing, critiquing, summarizing, and translating. Writing subcategories, in frequency order: Editing or Critiquing Provided Text, Personal Writing or Communication, Translation, Argument or Summary Generation, Writing Fiction.
- Practical Guidance versus Seeking Information: a factual lookup (Boston Marathon qualifying times) is Seeking Information. A customized workout plan is Practical Guidance. How-to advice is 8.5% of messages and 30% of Practical Guidance. Tutoring or Teaching is 10.2% of messages and 36% of Practical Guidance.
- Doing is 40% of messages, Asking 49%, Expressing 11%. About 56% of work-related messages in July 2025 are Doing. The paper says generative AI can produce writing, software code, spreadsheets, and other digital products.
- Technical Help: Computer Programming 4.2% of messages, Mathematical Calculation 3%, Data Analysis 0.4%. The paper contrasts that 4.2% with Handa et al., where 37% of Claude conversations map to computer-and-mathematical.
- Multimedia includes Create an Image, Analyze an Image, and Generate or Retrieve Other Media. Self-Expression includes Relationships and Personal Reflection at 1.9% and Games and Role Play at 0.4%.
- Sample: about 1.1 million conversations, 15 May 2024 through 26 June 2025, shares averaged on a 28-day window.

A later OpenAI data dictionary was not used. Its topic shares are a later release, not this 2025 paper.

### Anthropic Economic Index

Handa et al., Which Economic Tasks are Performed with AI? Evidence from Millions of Claude Conversations, arXiv:2503.04761.
PDF: https://assets.anthropic.com/m/2e23255f1e84ca97/original/Economic_Tasks_AI_Paper.pdf
Blog, 10 February 2025: https://www.anthropic.com/news/the-anthropic-economic-index
The PDF was downloaded and extracted (85,079 characters).

- Computer and Mathematical occupations comprise 37.2% of queries. Arts, Design, Entertainment, Sports, and Media were second at 10.3%. Augmentation is 57% of interactions and automation is 43%.
- The February paper says a significant portion of traffic falls under Business and Financial, Office and Administrative Support, and Management. It does not publish one percentage for those three combined.

Third report, geography chapter, opened 2026-10-29: https://www.anthropic.com/research/economic-index-geography and https://www.anthropic.com/research/anthropic-economic-index-september-2025-report

- Since December 2024, computer and mathematical uses have been around 37–40% of conversations. Educational instruction rose from 9% to 13%. Physical and social sciences rose from 6% to 8%. Management fell from 5% to 3%. Business and financial operations halved from 6% to 3%.
- Directive automation rose from 27% to 39%. Automation is 49.1% and augmentation is 47%.
- API traffic maps 44% to computer or mathematical tasks, against 36% on Claude.ai. Education is 4% of API traffic and 12% on Claude.ai. Arts are 5% and 8%.

Coding scenarios use the 37.2% figure because that is the share Anthropic measured on a coding-heavy product. The same scenarios also sit next to OpenAI's 4.2% consumer programming share. The draft's coding 23%, writing 17%, analysis 14%, education 9%, and customer support 7% are not in either opened report.

### WildChat (2024, not 2025)

Zhao et al., WildChat: 1M ChatGPT Interaction Logs in the Wild, arXiv:2405.01470, 2 May 2024.
https://arxiv.org/html/2405.01470
Dataset: https://huggingface.co/datasets/allenai/WildChat-1M-Full and https://wildchat.allen.ai

Table 4, first turn of English conversations, a 1,000-conversation subsample classified with valpy/prompt-classification: assisting/creative writing 61.9%, analysis/decision explanation 13.6%, coding 6.7%, factual info 6.3%, math reason 6.1%. The draft dated this study 2025. It is a 2024 preprint. It has no vision category.

### LMSYS-Chat-1M (2023, qualitative only)

Zheng et al., arXiv:2309.11998. Section 3.2 of https://arxiv.org/html/2309.11998v1 was opened on 2026-10-29.

From 100,000 English prompts clustered into 20 groups, the paper says: "The majority of questions are related to coding and software (Clusters 1, 2, 6, 16, 18)." The remaining clusters include unsafe topics and, in the paper's words, general knowledge, business inquiries, and writing assistance. Figure 3 is an image. The paper text does not publish a percentage split. LMSYS is not used as a percentage key for any scenario.

## Source keys

| Key | What it supports |
|---|---|
| openai-2025-writing | Writing, 40% of work messages; about two-thirds of Writing modifies user text, including summarizing. |
| openai-2025-practical-guidance | How-to advice, 8.5% of messages. The paper's own example of a customized plan. |
| openai-2025-seeking-information | Seeking Information grew from 14% to 24%. Factual lookup, distinct from a customized plan. |
| openai-2025-technical-help | Computer Programming, 4.2% of messages. Technical Help overall fell from 12% to around 5%. |
| openai-2025-multimedia | Multimedia grew from 2% to just over 7%. Includes Create an Image and Analyze an Image. |
| openai-2025-doing | Doing is 40% of messages. The paper names spreadsheets among the products generative AI produces. |
| anthropic-2025-02-computer-mathematical | Computer and Mathematical occupations, 37.2% of Claude queries (February 2025 paper). |
| wildchat-2024-analysis | analysis/decision explanation, 13.6% of the English first-turn subsample. |

OpenAI Data Analysis is 0.4% of messages. That is too thin to carry the three analysis scenarios, so they cite WildChat's 13.6% and the 0.4% figure is recorded here as the weaker consumer share.

## Scenario map

| Id | Workspace | Category | Source | Why this source fits |
|---|---|---|---|---|
| ru-v1-001 | auto-daily | writing | openai-2025-writing | A thank-you note that edits the user's invoice into prose. Personal writing is a Writing subcategory. |
| ru-v1-002 | auto-daily | practical_guidance | openai-2025-practical-guidance | A drive plan customized to the user's notes. That is the paper's Practical Guidance example, not a factual lookup. |
| ru-v1-003 | auto-daily | practical_guidance | openai-2025-practical-guidance | How-to advice for a new manager (8.5%). Relationships and Personal Reflection is only 1.9% and is not this task. |
| ru-v1-004 | auto-daily | writing | openai-2025-writing | Summarizing text the user supplied. Summarizing is named in the Writing introduction. |
| ru-v1-005 | auto-daily | technical_help | openai-2025-technical-help | A small programming fix. Computer Programming is 4.2% of ChatGPT messages. |
| ru-v1-006 | auto-daily | writing | openai-2025-writing | Summarizing four notes the user supplied, then writing them up. |
| ru-v1-007 | auto-daily::fast | seeking_information | openai-2025-seeking-information | A factual forecast lookup. Seeking Information, not a customized plan. |
| ru-v1-008 | auto-daily::deep | analysis | wildchat-2024-analysis | Decide which region and which week stand out. WildChat analysis/decision explanation is 13.6%. OpenAI Data Analysis is 0.4%. |
| ru-v1-009 | tools-specialist | technical_help | openai-2025-technical-help | Run a small program and compose a second tool around it. Technical Help / Computer Programming, 4.2%. |
| ru-v1-010 | tools-specialist::fast | technical_help | openai-2025-technical-help | A small text-processing program. Same Technical Help cite. |
| ru-v1-011 | auto-coding | coding | anthropic-2025-02-computer-mathematical | Software modification. Anthropic measured 37.2% of queries in computer and mathematical occupations. OpenAI's consumer programming share is 4.2%. |
| ru-v1-012 | auto-coding::laguna | coding | anthropic-2025-02-computer-mathematical | Same computer-and-mathematical cite. The seat can read and edit a repo file. |
| ru-v1-013 | auto-coding::uncensored-agentic | coding | anthropic-2025-02-computer-mathematical | Same computer-and-mathematical cite. A small parser, run in the sandbox. |
| ru-v1-014 | auto-coding | coding | anthropic-2025-02-computer-mathematical | Same cite. A wrong multiplier in a short function. |
| ru-v1-015 | auto-coding::lite | coding | anthropic-2025-02-computer-mathematical | Same cite. A line-count task over a few source files. |
| ru-v1-016 | auto-coding::heavy | coding | anthropic-2025-02-computer-mathematical | Same cite. Find an unbounded list and a bare open, then demonstrate the fix. |
| ru-v1-017 | auto-documents | writing | openai-2025-writing | Produce a document and a deck from sentences the user provided. Writing is 40% of work messages. |
| ru-v1-018 | auto-documents | writing | openai-2025-writing | Summarize a services agreement the user supplied, then write notes. |
| ru-v1-019 | auto-documents | writing | openai-2025-writing | Summarize three fields from a one-page PDF the user supplied. |
| ru-v1-020 | auto-documents | doing | openai-2025-doing | Build a spreadsheet. Doing is 40%, and the paper names spreadsheets as a generative-AI product. |
| ru-v1-021 | auto-research | seeking_information | openai-2025-seeking-information | Look up how other companies describe a hybrid week. Seeking Information. |
| ru-v1-022 | auto-research::data | analysis | wildchat-2024-analysis | Which region rates lowest, from a table. WildChat analysis 13.6%. OpenAI Data Analysis is 0.4%. |
| ru-v1-023 | auto-research | seeking_information | openai-2025-seeking-information | Check a claimed commute figure. Seeking Information. |
| ru-v1-024 | auto-research | analysis | wildchat-2024-analysis | Agree, conflict, and a gap across two notes. WildChat analysis 13.6%. |
| ru-v1-025 | auto-vision | multimedia | openai-2025-multimedia | Analyze an image, then create one. Multimedia rose from 2% to just over 7%. |
| ru-v1-026 | auto-vision | multimedia | openai-2025-multimedia | Analyze an image, then edit one. Same Multimedia cite. |
| ru-v1-027 | auto-vision | multimedia | openai-2025-multimedia | Create an image. Multimedia includes Create an Image. |
| ru-v1-028 | auto-documents | writing | openai-2025-writing | Read two notes and compare them. About two-thirds of Writing is modifying user text. |
| ru-v1-029 | auto-documents | writing | openai-2025-writing | Read a flyer and write a short note about the clash. Same Writing cite. |
| ru-v1-030 | auto-research | analysis | wildchat-2024-analysis | Two sources disagree. WildChat analysis/decision explanation, 13.6%. |
| ru-v1-031 | auto-coding | coding | anthropic-2025-02-computer-mathematical | A function that fails when run. Computer and mathematical, 37.2%. |
| ru-v1-032 | auto-daily | practical_guidance | openai-2025-practical-guidance | A week plan fitted to the user's constraints. Practical Guidance, the customized-plan example. |
| ru-v1-033 | auto-vision | multimedia | openai-2025-multimedia | Analyze an image and edit it. Multimedia, Analyze an Image. |
| ru-v1-034 | auto-coding::laguna | coding | anthropic-2025-02-computer-mathematical | Find two direct config lookups and edit one file. Computer and mathematical, 37.2%. |
| ru-v1-035 | auto-research::data | analysis | wildchat-2024-analysis | Compute an internal rate and the gap to a figure the user already has. WildChat analysis 13.6%. OpenAI Data Analysis is 0.4%. |

## Tool resolution

A tool is usable only when the workspace allowlist includes it and an MCP server registers it. `merge_workspace_variant` in `portal/platform/inference/config.py` replaces the parent `tools` list when a variant sets one. A variant that omits `tools` inherits the parent.

Allowlists were read from `config/portal.yaml` for auto-daily (and ::fast, ::deep), auto-coding (and ::laguna, ::uncensored-agentic, ::lite, ::heavy), tools-specialist (and ::fast), auto-documents, auto-research (and ::data), and auto-vision.

Wiki unit `unit-fact-tool-authorizations` matches those base workspace lists and does not list variant overrides, so the variant lists come from the YAML. Wiki unit `unit-fact-tool-registry` (queried 2026-10-29) marks the `mflux` and `research` servers unresolved, server file not found. A source grep the same day finds `@mcp.tool()` `generate_image` and `edit_image` in `portal/modules/media/tools/mflux_mcp.py`, and `web_search`, `news_search`, and `web_fetch` in `portal/modules/research/tools/web_search_mcp.py`. This suite follows the source registrations. The same grep confirms `execute_python`, `read_pdf`, `read_word_document`, `create_word_document`, `create_excel`, `create_powerpoint`, `attach_source`, `run_sql`, `kb_search`, `remember`, `recall`, `explore_repository`, and `write_file`.

`enable_web_search: true` on auto-research::data is an Open WebUI flag. The variant's `tools` list replaces the parent and does not include `web_search`.

There is no production workspace id `reading`. The alias `compliance-reading` points at `auto-compliance::reading`, whose tools only read that corpus. There is no variant `auto-coding::agentic`.

## Fixture and checker notes

Computed from the fixtures and copied into the checks: orders region winner north 76, dip week 4 total 21, south 57. Ratings lowest north 2.0. Low counts stove 2, lantern 1. Adopted 8 of 25 = 32 percent, gap 8 against the user-supplied 40 percent.

`ru-v1-016` `app.py` is generated so line 18 is `CACHE = []` and line 42 is `handle = open(path, encoding="utf-8")`. The builder must not reflow it.

`ru-v1-015` line counts, files ending in a newline: a.py 3, b.py 2, c.py 4, tests/t1.py 5, tests/t2.py 1. Totals 15 and, without tests/, 9.

Document and sandbox reads of user files use `/workspace/uploads/realuse_v1/<id>/<file>`. Laguna repo files use `fixtures/realuse_v1/<id>/` under `PIPELINE_MCP_REPO_ROOT`, because `write_file` allows the repo root only and `explore_repository` searches that root. `attach_source` under an eval scope is confined to the row's fixtures (`sub="in"`); the user message uses the bare filename. Session ids are `ru_v1_022` and `ru_v1_035` because a hyphen fails the session-id check.

Knowledge-base fixtures name `kb_id` `realuse-v1` and the exact text to ingest. Memory fixtures are the exact `remember` text to seed before the run. This lane does not build that ingest.

Checks stay prose. A line that starts with `judge:` is the subjective part. Other lines name a tool, a file, or an exact value.

## Flags

- Vision describe turns (025, 026, 033) have empty `expect_tools`. No registered tool describes an image. The seat is a vision-language model and the picture is an attachment. Generation and edit turns call `generate_image` or `edit_image`. Legible text on 025 requires `model` `qwen-image`. Pixel-perfect text is marked `judge:`.
- 028 and 029 moved from `reading` to `auto-documents`. The reading seat cannot read an ordinary upload, and the brief forbids that corpus's subject matter anywhere in the scenarios.
- 034 moved from `auto-coding::agentic` to `auto-coding::laguna`. That variant is not in `config/portal.yaml`. Laguna already has 012. A second scenario on the same variant is allowed.
- `execute_python` sees `/workspace` only when `SANDBOX_WORKSPACE_DIR` is mounted there. The code default is `/workspace-src`. The sandbox is read-only and has the Python standard library only, so these scenarios do not expect pandas or a persisted host file.
- `write_file` can write under the repo root only. A live run dirties that tree unless the harness sets `PIPELINE_MCP_REPO_ROOT` to a scratch root. The sandbox may not import that path, so the verify step inlines the corrected function.
- auto-coding, ::heavy, ::lite, and ::uncensored-agentic cannot persist an edit. Apply-the-fix turns check `execute_python` stdout.
- `kb_search` needs `kb_id` `realuse-v1` and an ingest the harness does not have yet. The fixture states the text. This lane does not add the ingest.
- OpenAI Data Analysis at 0.4% is thin support for 008, 022, and 035. WildChat 13.6% is the cite those three use.
- LMSYS-Chat-1M has no numeric category table in the paper text. It is not a scenario key.

## Dropped claims

The drafting lane had no web access. Its citation keys were labels, not papers, and several percentages are not in the studies above. Dropped as scenario keys: openai-usage-2025-writing-editing, openai-usage-2025-personal-advice, openai-usage-2025-planning, openai-usage-2025-technical-help, openai-usage-2025-learning, openai-usage-2025-vision, openai-usage-2025-coding, openai-usage-2025-reading-analysis, anthropic-econ-index-coding, anthropic-econ-index-planning, anthropic-econ-index-analysis, anthropic-econ-index-writing-editing, anthropic-econ-index-creative, lmsys-chat-1m-information-seeking, lmsys-chat-1m-document, lmsys-chat-1m-conversation, lmsys-chat-1m-vision, lmsys-chat-1m-technical-help.

Also dropped, because the opened pages do not say them: Anthropic coding 23%, writing 17%, analysis 14%, education 9%, customer support 7%; LMSYS coding 30–35%, writing 20%, conversation 15%; any claim that LMSYS has a vision category; the draft's dating of WildChat and LMSYS as 2025 studies.

No scenario was removed. 028 and 029 changed subject and workspace. 034 changed workspace. 014 and 031 changed the bug so the scenario no longer uses a secret-scanning or sign-in story. 024 changed from a regulation comparison to two product notes. 033 changed the banner text.

## Per-scenario change

- ru-v1-001: Re-sourced to OpenAI Writing (work 40%; personal writing). Dropped create_word_document. Turn 2 is prose only. Rubric no longer asks for a download.
- ru-v1-002: Re-sourced to OpenAI Practical Guidance how-to (8.5%), the paper's customized-plan example. Notes are a docx, not a txt. Dropped kb_search and execute_python.
- ru-v1-003: Re-sourced off the 1.9% relationships topic onto Practical Guidance how-to (8.5%). Notes are a docx. Turn 1 has no tool.
- ru-v1-004: Re-sourced to OpenAI Writing (summarizing user text). Dropped the LMSYS information-seeking key. Filename says handbook. Turn 2 is three hyphen lines in the channel.
- ru-v1-005: Re-sourced to OpenAI Computer Programming (4.2%). Replaced the 20k-row pandas story with an 8-row stdlib script that drops the last row. No file_write, no read_text_file.
- ru-v1-006: Kept OpenAI Writing. Four notes are docx, not txt. Dropped the callout-box requirement. Contradiction is September vs October.
- ru-v1-007: Re-sourced to OpenAI Seeking Information (14% to 24%). Dropped the LMSYS conversation key. No hardcoded temperature.
- ru-v1-008: Re-sourced to WildChat analysis/decision explanation (13.6%). CSV via execute_python, not read_excel. No pandas. Totals are computed from the fixture.
- ru-v1-009: Tools limited to execute_python, remember, and recall. Dropped read_pdf and file_write. The missing-config check reruns in the sandbox with mode live.
- ru-v1-010: Re-sourced to OpenAI Technical Help. Dropped the fake LMSYS key and create_excel. The seat only has execute_python, remember, and recall.
- ru-v1-011: Kept Anthropic computer-and-mathematical 37.2%, and the sources note also records OpenAI programming at 4.2%. Dropped read_text_file, file_write, and pytest_run.
- ru-v1-012: Tools are explore_repository, read_text_file, write_file, and execute_python. Dropped file_write and Flask. Fixture is under the repo root write_file can see.
- ru-v1-013: Kept the seat. Dropped read_text_file and write_file, which this variant does not have. Fixture is on the /workspace mount because execute_bash cannot see the host repo.
- ru-v1-014: Removed the secret-scanning story. Same coding cite. The bug is a wrong rate. No pytest_run and no file write.
- ru-v1-015: Kept the lite seat. Dropped write_file and chmod of a host script. Counts are 3+2+4+5+1=15 and 3+2+4=9. Depends on the sandbox /workspace mount.
- ru-v1-016: Heavy has no explore_repository, read_text_file, or write_file. Dropped classify_vulnerability. The apply-the-fix turn is an execute_python stdout check.
- ru-v1-017: Re-sourced to OpenAI Writing (40% of work messages). Dropped the Anthropic writing-editing key, which was not a published percentage. Empty fixture is honest.
- ru-v1-018: Kept a commercial agreement. Re-sourced to OpenAI Writing. Dropped the LMSYS document key. No red text and no recommendation box.
- ru-v1-019: Replaced the image invoice. This seat has no vision tool. Re-sourced to OpenAI Writing. No generate_image.
- ru-v1-020: Re-sourced to OpenAI Doing (40%) and the paper's spreadsheets sentence. Dropped the fake analysis percentage. No conditional formatting. The notes file was dropped because this seat would need a docx to read it and the numbers are already in the prompt.
- ru-v1-021: Re-sourced to OpenAI Seeking Information. Dropped the Anthropic planning key. Internal comparison is a KB document. Both turns call a tool because tool_choice is required.
- ru-v1-022: Re-sourced to WildChat analysis 13.6%. Dropped read_excel and the 500-row file. Session id ru_v1_022 has no hyphen. No web_search on this variant.
- ru-v1-023: Re-sourced to OpenAI Seeking Information. Dropped the LMSYS percentage. Turn 2 is kb_search, not read_pdf. This seat cannot read PDFs.
- ru-v1-024: Removed the regulation topic. Re-sourced to WildChat analysis 13.6%. No read_text_file and no create_word_document. Turn 2 still calls kb_search because tool_choice is required.
- ru-v1-025: Re-sourced to OpenAI Multimedia (2% to just over 7%), Analyze an Image and Create an Image. Describe turn has empty expect_tools: no tool describes images. Legible text requires model qwen-image. Pixel match is judge:.
- ru-v1-026: Re-sourced to OpenAI Multimedia. Dropped execute_python. Describe turn has empty expect_tools. The edit checks image_url and the prompt, not pixels.
- ru-v1-027: Re-sourced to OpenAI Multimedia, Create an Image. Dropped the Anthropic creative key, which was not a measured category. Model is optional because the image has no rendered text.
- ru-v1-028: Moved off the reading seat, whose tools only read the regulated corpus, onto auto-documents. Ordinary backyard notes. Source is OpenAI Writing (modifying user text).
- ru-v1-029: Moved off the reading seat onto auto-documents. Replaced the regulated-corpus scenario with a potluck flyer. Source is OpenAI Writing.
- ru-v1-030: Re-sourced to WildChat analysis 13.6%. Dropped the learning key, the markdown file, and create_word_document. Turn 2 stays in the reply and still calls a tool.
- ru-v1-031: Removed the auth story. Same coding cite. The bug is a NameError. The check is execute_python, not pytest_run.
- ru-v1-032: Re-sourced to OpenAI Practical Guidance (customized plan, 8.5%). Dropped the unread txt. create_word_document is on auto-daily.
- ru-v1-033: Re-sourced to OpenAI Multimedia, Analyze an Image. Replaced the banner wording. Describe turn has empty expect_tools. Turn 2 is edit_image.
- ru-v1-034: Retargeted off auto-coding::agentic, which does not exist, onto auto-coding::laguna. The user message now says two files, and the edit fixes only entry_point.py.
- ru-v1-035: Re-sourced to WildChat analysis 13.6%. Dropped the live adoption-rate lookup. web_search is not on auto-research::data. Session id ru_v1_035. The rate is computed from the fixture.
