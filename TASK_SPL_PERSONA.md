# TASK: Add Splunk SPL Engineer Persona — Portal 5

**Branch**: `feature/spl-engineer-persona`  
**Scope**: New workspace (`auto-spl`) + new persona YAML + keyword routing upgrade + unit tests  
**Touches**: 5 files, no new dependencies, no new Docker services, no port allocations  
**Must pass before commit**: `pytest tests/ -q --tb=no && ruff check . && ruff format --check .`

---

## Background & Decision Record

This task wires a dedicated Splunk SPL Engineer persona into Portal 5.

### Why a separate workspace instead of relying on `auto-coding`

SPL keywords (`"splunk"`, `"spl query"`) already exist in `_CODING_KEYWORDS` and route the
`auto` workspace to `auto-coding`. That coverage is coincidental, not intentional:

- `auto-coding` routes to `mlx-community/Qwen3-Coder-Next-8bit` (~32GB) — too heavy when the
  user just needs SPL translation, and brings no Splunk-specific tuning.
- The `blueteamdefender` persona lists SPL as one skill among many and routes to
  `lily-cybersecurity:7b-q4_k_m`, a SOC model with no code specialization.
- Neither gives a system prompt built around SPL syntax constraints, pipeline explanation,
  or the specific `eval` / `tonumber` / function-hallucination guardrails that make
  SPL generation reliable.

A dedicated `auto-spl` workspace with an appropriate model and hardened system prompt is the
right architectural unit per CLAUDE.md Rule 5 and Rule 6.

### Model selection: DeepSeek-Coder-V2-Lite-Instruct-8bit (MLX)

The `splunk_persona.md` conversation recommends StarCoder2-15B-Instruct as the most
SPL-lineage-appropriate public model. That recommendation is well-sourced but has two
Portal-5-specific problems:

1. **Single-turn model**: The StarCoder2-Instruct model card explicitly warns it is designed
   for single-turn coding instructions and may not behave well in multi-turn chat. Portal 5
   is a multi-turn chat interface; single-turn behavior is a disqualifying limitation.

2. **Not in the stack**: Adding a new Ollama model just for this persona requires adding it
   to `backends.yaml`, pulling it, and creating a new backend group. That is disproportionate
   overhead for a persona when a suitable model already exists.

`mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit` is already registered in
`backends.yaml` under `mlx-apple-silicon`, already labeled "SPL specialist" in the comment,
fits in ~12GB (can run alongside ComfyUI + Ollama general), and is a strong instruct-tuned
code model with 338-language pre-training and 128K context. It handles DSL-generation tasks
(structured, pipe-based query languages) well. The hardened system prompt below does the
work that StarCoder2's SPL-lineage pre-training would have done — and the prompt is required
either way, per the model card warnings in the `splunk_persona.md` analysis.

Ollama fallback: `deepseek-coder-v2:16b-lite-instruct-q4_K_M` (already in `ollama-coding`
group) — same model family, different quant path.

### Keyword routing: promote SPL out of `_CODING_KEYWORDS` 

`"splunk"` and `"spl query"` currently live in `_CODING_KEYWORDS`, so `auto` routing sends
SPL questions to `auto-coding`. After this task, a new `_SPL_KEYWORDS` frozenset and a new
`_SPL_REGEX` precompiled pattern handle SPL detection with higher priority than generic
coding — routing the `auto` workspace directly to `auto-spl`. The two existing entries must
be **removed** from `_CODING_KEYWORDS` to avoid the old route winning.

---

## Deliverables (5 files)

### File 1 — `config/personas/splunksplgineer.yaml` (NEW)

Create this file exactly as written below. Do not alter field names, indentation style,
or the ordering of YAML keys — `openwebui_init.py` reads `slug`, `name`, `category`,
`workspace_model`, `system_prompt`, and `tags` by name.

```yaml
name: Splunk SPL Engineer
slug: splunksplgineer
category: security
workspace_model: mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit
system_prompt: |
  You are an expert Splunk SPL (Search Processing Language) Engineer. Your sole function
  is to write, explain, refactor, and debug SPL. You do not perform general security
  analysis, threat intelligence, or platform administration — redirect those requests.

  HARD CONSTRAINTS (never violate):
  - Never hallucinate eval functions. Splunk does not support `is_numeric()`, `indexof()`,
    or `contains()` as standalone eval functions. Use `match()`, `tonumber()`, `like()`,
    `isnull()`, `isnotnull()`.
  - Never assign boolean results directly in eval. Always use:
    `eval field = if(boolean_expr, "true_val", "false_val")`.
  - Always wrap variables in `tonumber()` before arithmetic — the `-` operator rejects
    strings and fails silently in some Splunk versions.
  - Never use inline comments inside eval commands or query strings. Comments cause
    malformed expression errors in Splunk's search parser.
  - Do not mix `split()` + `mvindex()` string workarounds where `rex` extractions are
    simpler and more performant.
  - Always filter on index, sourcetype, and time range before the first pipe `|`.
    Late filtering is the single most common SPL performance error.
  - Assume Splunk Enterprise 9.x unless the user specifies otherwise. Do not use
    deprecated commands (`abstract`, `gauge`, `filldown` before 6.5, etc.).
  - If index or sourcetype is unknown, use `index=<YOUR_INDEX>` and
    `sourcetype=<YOUR_SOURCETYPE>` placeholders. Never block the response.

  RESPONSE WORKFLOW:
  1. NL → SPL: translate the natural-language request into a clean, performant search.
  2. Pipe breakdown: explain what each command does to the data event stream, one pipe
     at a time. Do not skip pipes.
  3. Refactor / debug: if the user provides broken SPL, identify the exact error
     (syntax vs. logic vs. performance) and produce a corrected search.
  4. Dashboard output: when generating a panel query, ensure output fields are
     clean for timechart, stats, or table visualizations — no raw multi-value fields
     unless the panel type supports them.
  5. Performance note: flag any search that will fan out across all indexes, lacks a
     time filter, uses expensive transforming commands early in the pipeline, or
     generates excessive events before the first stats.

  OUTPUT FORMAT:
  - SPL blocks in triple backticks with the `splunk` language tag.
  - Pipe breakdown as a numbered list matching each `|` command.
  - One-line performance verdict at the end: FAST / ACCEPTABLE / SLOW (with reason).
  - If the search requires a saved macro or lookup table the user has not provided,
    note it explicitly rather than silently referencing undefined identifiers.
tags:
  - security
  - splunk
  - spl
  - detection-engineering
  - data-analysis
```

---

### File 2 — `portal_pipeline/router_pipe.py` (MODIFY — 4 targeted changes)

**Change 2a — Add `_SPL_KEYWORDS` frozenset after `_CODING_KEYWORDS`**

Insert immediately after the closing brace of `_CODING_KEYWORDS` (around line 661):

```python
_SPL_KEYWORDS: frozenset[str] = frozenset(
    {
        # Direct SPL / Splunk language references
        "splunk",
        "spl",
        "spl query",
        "search processing language",
        # SPL commands (common ones users type in natural language)
        "tstats",
        "eval field",
        "rex field",
        "lookup command",
        "inputlookup",
        "outputlookup",
        "makeresults",
        "mvexpand",
        "streamstats",
        "eventstats",
        "transaction command",
        "| stats",
        "| timechart",
        "| table",
        "| eval",
        "| rex",
        "| dedup",
        "| sort",
        "| rename",
        # SPL-specific diagnostic language
        "correlation search",
        "notable event",
        "splunk es",
        "splunk enterprise security",
        "datamodel",
        "data model acceleration",
        "summary index",
        "saved search",
        "dashboard panel spl",
        "detection search",
        "splunk query",
        "write me a splunk",
        "write a splunk",
        "build a splunk",
    }
)
```

**Change 2b — Remove `"splunk"` and `"spl query"` from `_CODING_KEYWORDS`**

In the `_CODING_KEYWORDS` frozenset (around lines 654–659), delete these two entries:

```python
        "splunk",
        "spl query",
```

They must be removed. Leaving them means `_CODING_REGEX` can still match before
`_SPL_REGEX` runs, depending on call order. The new `_SPL_KEYWORDS` set is the
correct home for all Splunk-related keyword routing.

**Change 2c — Add `_SPL_REGEX` compiled pattern after `_CODING_REGEX`**

Add immediately after the line that creates `_CODING_REGEX` (around line 697):

```python
_SPL_REGEX = _make_word_boundary_regex(_SPL_KEYWORDS)
```

**Change 2d — Add `auto-spl` entry to the `WORKSPACES` dict**

Add immediately after the `"auto-coding"` entry (after its closing `},`):

```python
    "auto-spl": {
        "name": "🔍 Portal SPL Engineer",
        "description": "Splunk SPL queries, pipeline explanation, detection search authoring",
        "model_hint": "deepseek-coder-v2:16b-lite-instruct-q4_K_M",
        "mlx_model_hint": "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",
    },
```

**Change 2e — Insert SPL detection into `_detect_workspace`**

In the `_detect_workspace` function, add an SPL check **before** the coding check.
The SPL check must come after the security check (SPL detection rules are not
offensive security) and before the generic coding check (SPL is more specific):

```python
    # SPL check — must come before coding (SPL is a strict subset, needs dedicated routing).
    # Single hit is sufficient — SPL vocabulary is specific enough that false positives
    # are rare. Splunk-related terms are no longer in _CODING_KEYWORDS.
    if _SPL_REGEX.search(last_user_content):
        return "auto-spl"
```

Insert it at the position that currently reads:

```python
    # Coding check — same single-pass regex (P9).
    if _CODING_REGEX.search(last_user_content):
        return "auto-coding"
```

The final priority order in `_detect_workspace` must be:
1. Redteam (2+ hits) → `auto-redteam`
2. Security (1+ hit) → `auto-security`
3. **SPL (1+ hit) → `auto-spl`** ← new
4. Coding (1+ hit) → `auto-coding`
5. Reasoning (2+ hits) → `auto-reasoning`
6. None → `None` (caller uses default)

---

### File 3 — `config/backends.yaml` (MODIFY — 2 targeted changes)

**Change 3a — Add `auto-spl` to `workspace_routing`**

In the `workspace_routing` block, add immediately after `auto-coding`:

```yaml
  auto-spl:      [mlx, coding, general]
```

Rationale: MLX first (DeepSeek-Coder-V2-Lite-Instruct-8bit is already in the MLX
backend), coding Ollama group as fallback (DeepSeek-Coder-V2-16B-Lite is there),
general as last resort. Same pattern as `auto-coding`.

**Change 3b — Add a comment cross-reference on the DeepSeek-Coder-V2-Lite MLX entry**

Find this line in the `mlx-apple-silicon` models list:

```yaml
      - mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit  # SPL specialist (~12GB)
```

Update the comment to make the routing explicit:

```yaml
      - mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit  # auto-spl primary: SPL specialist (~12GB)
```

---

### File 4 — `imports/openwebui/workspaces/workspace_auto_spl.json` (NEW)

Create this new file. The `toolIds` list is empty — the SPL Engineer persona does not
require any MCP tool servers. Do not add `portal_code` or other tool IDs unless you
have confirmed SPL workflows need them; keep the workspace lean.

```json
{
  "id": "auto-spl",
  "name": "🔍 Portal SPL Engineer",
  "meta": {
    "description": "🔍 Portal SPL Engineer — Splunk query authoring, pipeline explanation, detection search",
    "profile_image_url": "",
    "toolIds": []
  },
  "params": {
    "system": "You are an expert Splunk SPL Engineer. Write, explain, refactor, and debug SPL queries. Always filter on index and sourcetype before the first pipe. Never hallucinate eval functions.",
    "model": "auto-spl"
  }
}
```

**Also update `imports/openwebui/workspaces/workspaces_all.json`**

This file is a JSON array containing all workspace objects. Append the new workspace
object as the last element of the array. The object to append is identical to the
content of `workspace_auto_spl.json` above.

Do not reformat any existing entries — append only.

---

### File 5 — `tests/unit/test_pipeline.py` (MODIFY — add new test class)

Append this class at the end of the file. Do not modify any existing tests.

```python
class TestSPLWorkspace:
    """Verify auto-spl workspace wiring across all four required files."""

    def test_auto_spl_in_workspaces_dict(self):
        """auto-spl must exist in WORKSPACES dict in router_pipe.py."""
        from portal_pipeline.router_pipe import WORKSPACES

        assert "auto-spl" in WORKSPACES, (
            "auto-spl missing from WORKSPACES in router_pipe.py — "
            "add it with model_hint and mlx_model_hint"
        )

    def test_auto_spl_uses_deepseek_coder_model_hint(self):
        """auto-spl model_hint must be deepseek-coder-v2 (Ollama fallback)."""
        from portal_pipeline.router_pipe import WORKSPACES

        hint = WORKSPACES["auto-spl"]["model_hint"]
        assert "deepseek-coder-v2" in hint.lower(), (
            f"auto-spl model_hint should be deepseek-coder-v2 variant, got: {hint}"
        )

    def test_auto_spl_uses_deepseek_coder_mlx_hint(self):
        """auto-spl mlx_model_hint must point to DeepSeek-Coder-V2-Lite MLX."""
        from portal_pipeline.router_pipe import WORKSPACES

        hint = WORKSPACES["auto-spl"].get("mlx_model_hint", "")
        assert "DeepSeek-Coder-V2-Lite" in hint, (
            f"auto-spl mlx_model_hint should be DeepSeek-Coder-V2-Lite-Instruct-8bit, got: {hint}"
        )

    def test_auto_spl_in_backends_yaml(self):
        """auto-spl must exist in workspace_routing in backends.yaml."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        routing = cfg.get("workspace_routing", {})
        assert "auto-spl" in routing, (
            "auto-spl missing from workspace_routing in backends.yaml"
        )

    def test_auto_spl_routing_starts_with_mlx(self):
        """auto-spl routing must prefer mlx group first (Apple Silicon primary)."""
        import yaml

        cfg = yaml.safe_load(open("config/backends.yaml"))
        groups = cfg["workspace_routing"].get("auto-spl", [])
        assert groups and groups[0] == "mlx", (
            f"auto-spl must prefer mlx group first, got: {groups}"
        )

    def test_workspace_count_is_16(self):
        """Total workspace count must be 16 after adding auto-spl (was 15)."""
        from portal_pipeline.router_pipe import WORKSPACES

        assert len(WORKSPACES) == 16, (
            f"Expected 16 workspaces after adding auto-spl, got {len(WORKSPACES)}. "
            "Update this test if workspaces are intentionally added or removed."
        )

    def test_spl_persona_yaml_exists(self):
        """Persona YAML file must exist at the canonical path."""
        from pathlib import Path

        persona_path = Path("config/personas/splunksplgineer.yaml")
        assert persona_path.exists(), (
            f"SPL Engineer persona YAML not found at {persona_path}"
        )

    def test_spl_persona_yaml_has_required_fields(self):
        """Persona YAML must have all fields read by openwebui_init.py."""
        import yaml
        from pathlib import Path

        data = yaml.safe_load(Path("config/personas/splunksplgineer.yaml").read_text())
        for field in ("name", "slug", "category", "workspace_model", "system_prompt", "tags"):
            assert field in data, f"SPL persona YAML missing required field: {field}"

    def test_spl_persona_workspace_model_is_mlx_deepseek(self):
        """Persona workspace_model must be the MLX DeepSeek-Coder-V2-Lite model."""
        import yaml
        from pathlib import Path

        data = yaml.safe_load(Path("config/personas/splunksplgineer.yaml").read_text())
        wm = data.get("workspace_model", "")
        assert "DeepSeek-Coder-V2-Lite" in wm, (
            f"SPL persona workspace_model should be DeepSeek-Coder-V2-Lite-Instruct-8bit, got: {wm}"
        )

    def test_workspace_json_exists(self):
        """Workspace JSON file must exist for GUI import."""
        from pathlib import Path

        ws_path = Path("imports/openwebui/workspaces/workspace_auto_spl.json")
        assert ws_path.exists(), (
            f"Workspace JSON not found at {ws_path}"
        )

    def test_workspace_json_has_correct_id(self):
        """Workspace JSON id must be 'auto-spl'."""
        import json
        from pathlib import Path

        data = json.loads(
            Path("imports/openwebui/workspaces/workspace_auto_spl.json").read_text()
        )
        assert data.get("id") == "auto-spl", (
            f"workspace_auto_spl.json id should be 'auto-spl', got: {data.get('id')}"
        )

    def test_workspaces_all_json_includes_spl(self):
        """workspaces_all.json bulk import must include auto-spl entry."""
        import json
        from pathlib import Path

        all_ws = json.loads(
            Path("imports/openwebui/workspaces/workspaces_all.json").read_text()
        )
        ids = [ws.get("id") for ws in all_ws]
        assert "auto-spl" in ids, (
            "auto-spl not found in workspaces_all.json — append the workspace object to the array"
        )

    def test_splunk_not_in_coding_keywords(self):
        """'splunk' must be removed from _CODING_KEYWORDS — SPL workspace owns it now."""
        from portal_pipeline.router_pipe import _CODING_KEYWORDS

        assert "splunk" not in _CODING_KEYWORDS, (
            "'splunk' must be removed from _CODING_KEYWORDS after adding _SPL_KEYWORDS. "
            "Leaving it causes SPL queries to route to auto-coding instead of auto-spl."
        )

    def test_spl_query_not_in_coding_keywords(self):
        """'spl query' must be removed from _CODING_KEYWORDS — SPL workspace owns it now."""
        from portal_pipeline.router_pipe import _CODING_KEYWORDS

        assert "spl query" not in _CODING_KEYWORDS, (
            "'spl query' must be removed from _CODING_KEYWORDS after adding _SPL_KEYWORDS."
        )

    def test_spl_keywords_frozenset_exists(self):
        """_SPL_KEYWORDS frozenset must be importable from router_pipe."""
        from portal_pipeline.router_pipe import _SPL_KEYWORDS

        assert isinstance(_SPL_KEYWORDS, frozenset), (
            "_SPL_KEYWORDS must be a frozenset in router_pipe.py"
        )
        assert len(_SPL_KEYWORDS) >= 10, (
            f"_SPL_KEYWORDS seems too small ({len(_SPL_KEYWORDS)} entries) — check the definition"
        )
        assert "splunk" in _SPL_KEYWORDS, (
            "'splunk' must be in _SPL_KEYWORDS"
        )

    def test_spl_detect_workspace_routes_splunk_query(self):
        """_detect_workspace must return 'auto-spl' for an SPL-flavored message."""
        from portal_pipeline.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "Write a splunk query to count failed logins by host"}
        ]
        result = _detect_workspace(messages)
        assert result == "auto-spl", (
            f"_detect_workspace should return 'auto-spl' for SPL content, got: {result!r}"
        )

    def test_spl_detect_workspace_routes_tstats_query(self):
        """_detect_workspace must return 'auto-spl' when user asks about tstats."""
        from portal_pipeline.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "How do I use tstats with a data model acceleration?"}
        ]
        result = _detect_workspace(messages)
        assert result == "auto-spl", (
            f"_detect_workspace should return 'auto-spl' for tstats content, got: {result!r}"
        )

    def test_spl_does_not_route_generic_coding(self):
        """Generic Python/code requests must NOT route to auto-spl."""
        from portal_pipeline.router_pipe import _detect_workspace

        messages = [
            {"role": "user", "content": "Write a Python function to parse JSON logs"}
        ]
        result = _detect_workspace(messages)
        assert result != "auto-spl", (
            f"Python-only request should not route to auto-spl, got: {result!r}"
        )

    def test_auto_spl_routing_consistent_across_files(self):
        """auto-spl key must exist in both WORKSPACES and backends.yaml workspace_routing."""
        import yaml
        from portal_pipeline.router_pipe import WORKSPACES

        cfg = yaml.safe_load(open("config/backends.yaml"))
        pipe_ids = set(WORKSPACES.keys())
        yaml_ids = set(cfg["workspace_routing"].keys())
        assert "auto-spl" in pipe_ids, "auto-spl missing from WORKSPACES in router_pipe.py"
        assert "auto-spl" in yaml_ids, "auto-spl missing from workspace_routing in backends.yaml"
        assert pipe_ids == yaml_ids, (
            f"WORKSPACES / workspace_routing mismatch after adding auto-spl. "
            f"In pipe but not yaml: {pipe_ids - yaml_ids}. "
            f"In yaml but not pipe: {yaml_ids - pipe_ids}."
        )
```

---

## Consistency Check

After all changes, run the workspace consistency check from CLAUDE.md Rule 6:

```bash
python3 -c "
import yaml
from portal_pipeline.router_pipe import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
pipe_ids = set(WORKSPACES.keys())
yaml_ids = set(cfg['workspace_routing'].keys())
assert pipe_ids == yaml_ids, f'Mismatch: pipe={pipe_ids-yaml_ids} yaml={yaml_ids-pipe_ids}'
print(f'Workspace IDs consistent ({len(pipe_ids)} total)')
"
```

Expected output: `Workspace IDs consistent (16 total)`

Then run the full test + lint suite:

```bash
pytest tests/ -v --tb=short && ruff check . && ruff format --check .
```

All existing tests must continue to pass. The new `TestSPLWorkspace` class adds 16 new
tests; none should require modifying existing tests. The one existing test that will fail
after this change is `test_workspace_count_is_14` — which already has a stale description
("now 15 with auto-mistral") and asserts `len(WORKSPACES) == 15`. Update that assertion to
`16` and update the docstring to reflect the SPL addition. That is the only existing test
that needs a number bump.

---

## Scope Boundaries — Do Not Do These

- **Do not pull or register a new Ollama model.** `deepseek-coder-v2:16b-lite-instruct-q4_K_M`
  is already in `ollama-coding` group. The MLX model is already in `mlx-apple-silicon`.
  No new models, no changes to `launch.sh` pull lists.
- **Do not add a new Docker service or port.** This is persona + routing only.
- **Do not modify `openwebui_init.py`.** It already reads all `config/personas/*.yaml` files
  and all `imports/openwebui/workspaces/*.json` files automatically. New files are picked up
  on next seed without any code change.
- **Do not add MCP tool server wiring** to the workspace. The SPL Engineer is a
  pure-language-model persona. If future work wants to add a Splunk REST API validator MCP
  tool, that is a separate task.
- **Do not modify the `auto-mistral` workspace** or any other existing workspace.
- **Do not rename `"splunksplgineer"` slug.** The slug becomes the Open WebUI preset ID;
  changing it after seeding orphans the old preset.

---

## Commit Message

```
feat(personas): add Splunk SPL Engineer workspace and persona

- New auto-spl workspace routes to DeepSeek-Coder-V2-Lite (MLX primary,
  deepseek-coder-v2:16b Ollama fallback)
- New splunksplgineer.yaml persona with hardened SPL constraints (eval
  hallucination guard, tonumber enforcement, filter-first rules)
- _SPL_KEYWORDS frozenset + _SPL_REGEX for content-aware routing from auto
- SPL detection inserted between security and coding in _detect_workspace
  priority chain
- 'splunk' and 'spl query' removed from _CODING_KEYWORDS (now owned by SPL)
- workspace_auto_spl.json + workspaces_all.json updated
- TestSPLWorkspace: 16 new unit tests covering all wiring points
- workspace count: 15 → 16
```
