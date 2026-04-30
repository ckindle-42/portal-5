# TASK_UAT_PHASE4_POSTMERGE_FIXES.md

**Owner:** Claude Code
**Source:** Post-merge audit of Phase 1/2/3 commits at HEAD `e3aae7c` (Phase 3), `d9e15ac` (Phase 2), `a9de56e` (Phase 1).
**Scope:** `tests/portal5_uat_driver.py` only.
**Dependencies:** Phase 1, 2, 3 must be merged.
**What this fixes:** Two narrow defects discovered while verifying Phase 2 in a fresh clone — a real bug in `word_boundary` keyword behavior that silently disables some Lives-system patterns, and an incorrect justification for one Phase 2 edit that should be documented.

---

## Why this phase

Phase 1, 2, and 3 all merged successfully. The unit tests pass (7/7), the dispatch sites are wired correctly for both streaming and non-streaming MLX paths, and the regex parsing in `_remove_rows_for_test_ids` handles all real test ID formats (including hyphen-rich bench IDs like `CC-01-llama33-70b`).

However, two issues surfaced during the post-merge audit:

### Issue 1 — `word_boundary` silently breaks keywords ending in non-word characters

The Phase 1 `_kw_in` helper uses regex `\b...\b` to anchor on word boundaries. The `\b` zero-width anchor only fires at `\w`↔`\W` transitions. This means **any keyword that begins or ends with a non-word character** has its trailing `\b` looking for a non-existent transition, which silently fails:

```python
# Phase 2 catalog: _CC01_ASSERTIONS Lives system has these keywords with word_boundary=True
_kw_in("lives--", "this.lives--;", word_boundary=True)   # False — should be True
_kw_in("lives++", "lives++;", word_boundary=True)        # False — should be True
```

**Trace:** `\blives--\b` → after `--` (non-word) the regex looks for word/non-word transition, but `;` is also non-word. No transition, no match.

**Catalog impact:** Of the 20 keywords in `_CC01_ASSERTIONS["Lives system"]`, 2 keywords (`"lives--"`, `"lives++"`) silently fail to match real JS code patterns. The bench tests still pass on most code-shipping models because other keywords match (`this.lives`, `lives`, `livesCount`), but this is fragile: a model that emits *only* `--`/`++` decrement style without a noun reference would falsely fail.

**Verified at HEAD:**

```
=== word_boundary=True (Phase 2 setting) ===
  False  kw='lives--'  in 'this.lives--;'        ← silent miss
  False  kw='lives++'  in 'lives++;'             ← silent miss
  False  kw='starting lives' in 'startingLives:' ← case difference, expected
  True   kw='player.lives' in 'if (player.lives <= 0)'
  True   kw='lose a life' in 'you lose a life today'
  True   kw='3 lives' in 'the player has 3 lives.'
```

### Issue 2 — CIP citation `word_boundary` flag was added to defend against a non-existent threat

The original review plan claimed `"r1"` would substring-match `"router 1.0"`, justifying `word_boundary: True` on the WS-16 / P-C01 CIP citation assertions. **This is wrong** — `"router 1"` has a space between `r` and `1`, so `"r1" in "router 1".lower()` returns False under legacy substring matching too.

**Verified at HEAD:**

```python
"r1" in "router 1.0 with cipher 1.2.6".lower()  # False (legacy)
```

The `word_boundary: True` on CIP citations is therefore **mostly cosmetic** — it doesn't change behavior on the canonical test response. There is one narrow case where it does help (`"SCIP-003-9"` would substring-match `"cip-003-9"` under legacy), so the flag isn't useless, but it can also produce a regression: `"R1.2.6"` (smashed-together citation) — `"1.2.6"` matches under legacy but fails under word_boundary because the leading `1` has no preceding word/non-word transition (preceded by `R`, which IS \w, so... let me verify in the audit).

Actually re-checking: `R` is `\w`, `1` is `\w`, so `\b` does NOT fire between them — the boundary requires a `\W`↔`\w` transition. So `"R1.2.6"` → `"1.2.6"` lookup with `\b1.2.6\b` fails. **Confirmed regression** for smashed-together citations.

**Disposition:** The CIP `word_boundary` is keeping a cosmetic protection at the cost of a real (if narrow) regression. Recommendation is to drop it for CIP citations, but this is judgment-call — see Edit 2 below.

---

## Pre-flight

```bash
cd $REPO_ROOT
git status --short                                # tree clean
git rev-parse --short HEAD                         # capture for rollback

# Confirm Phase 1+2+3 all landed
grep -n "_inject_mlx_options" portal_pipeline/router_pipe.py | head -1
# Expected: hit at line 1480-ish

grep -n "_kw_in\|word_boundary" tests/portal5_uat_driver.py | head -3
# Expected: 3+ hits

python3 -m pytest tests/unit/test_uat_grading.py -v
# Expected: 7 passed
```

---

## Edits

### Edit 1 — Remove broken keywords from `_CC01_ASSERTIONS` Lives system

`tests/portal5_uat_driver.py:1716-1746`

The two keywords that silently fail under `word_boundary: True` should be removed, since `this.lives` (which IS in the keyword list) already matches the same code patterns these were trying to catch.

**Before:**

```python
        "keywords": [
            "lives",
            "life",
            "lives_remaining",
            "numlives",  # case-insensitive matches numLives
            "playerlives",
            "player.lives",
            "this.lives",
            "this.life",
            "playerlife",
            "livescount",
            "livesleft",
            "lifecount",
            "remaininglives",
            "player_lives",
            "lives--",
            "lives++",
            "lose a life",
            "lost a life",
            "starting lives",
            "3 lives",
        ],
```

**After:**

```python
        "keywords": [
            "lives",
            "life",
            "lives_remaining",
            "numlives",  # case-insensitive matches numLives
            "playerlives",
            "player.lives",
            "this.lives",
            "this.life",
            "playerlife",
            "livescount",
            "livesleft",
            "lifecount",
            "remaininglives",
            "player_lives",
            # NOTE: "lives--" and "lives++" were here but were removed.
            # word_boundary=True can't anchor `\b` after non-word chars `--`/`++`,
            # so they silently never matched. The 'lives' or 'this.lives' keywords
            # already cover any code path containing these patterns.
            "lose a life",
            "lost a life",
            "starting lives",
            "3 lives",
        ],
```

**Why not just drop `word_boundary: True` instead of removing keywords?** `word_boundary: True` is doing real work for the `"lives"` keyword — without it, `"lives" in "olives".lower()` is True, which produces false positives on responses that mention olives in some unrelated context. The flag is doing its job; the broken keywords are vestigial.

### Edit 2 — Drop `word_boundary` from CIP citation assertions (recommended)

The CIP citations don't have a real false-positive risk under legacy substring matching (the original review plan's `"r1"` example was incorrect). The `word_boundary: True` flag introduces a regression on smashed-together citation forms (`"R1.2.6"`) without a meaningful upside.

**Before** (`tests/portal5_uat_driver.py:4459-4467`):

```python
            {
                "type": "contains",
                "label": "Standard cited precisely",
                "keywords": ["cip-003-9", "r1", "1.2.6"],
                "word_boundary": True,
            },
```

**After:**

```python
            {
                "type": "contains",
                "label": "Standard cited precisely",
                "keywords": ["cip-003-9", "r1", "1.2.6"],
                # word_boundary intentionally not set: the original review plan's
                # claim that 'r1' would substring-match 'router 1' was incorrect
                # (the space prevents that). And word_boundary regresses on
                # smashed forms like 'R1.2.6' (\b can't fire between word chars).
            },
```

**Before** (`tests/portal5_uat_driver.py:4530-4538`):

```python
            {
                "type": "contains",
                "label": "Precise citation",
                "keywords": ["cip-003-9", "1.2.6"],
                "word_boundary": True,
            },
```

**After:**

```python
            {
                "type": "contains",
                "label": "Precise citation",
                "keywords": ["cip-003-9", "1.2.6"],
                # word_boundary intentionally not set — see WS-16 above.
            },
```

> **Note:** find the exact lines first — the line numbers above are estimates from a fresh clone. Use `grep -n "Standard cited precisely\|Precise citation" tests/portal5_uat_driver.py` to locate them.

### Edit 3 — Add a regression test for the leading/trailing non-word edge case

`tests/unit/test_uat_grading.py` — append at end:

```python


def test_word_boundary_keyword_with_trailing_nonword():
    """Keywords ending in non-word chars (like 'lives--') CANNOT use word_boundary.

    Regression test for the silent-mismatch bug: \\b only fires at \\w<->\\W
    transitions. A keyword ending in '--' would need its closing \\b to find a
    \\w after the '--', but in real JS code (`this.lives--;`) the next char is
    ';' (non-word). No transition, no match.

    This test pins the BEHAVIOR (silent fail) rather than fixing it, because
    fixing would require either a different anchoring strategy or per-keyword
    logic. The catalog must avoid combining word_boundary=True with keywords
    that begin or end with non-word characters.
    """
    from portal5_uat_driver import _kw_in

    # The keyword's trailing -- is non-word, and ;/whitespace after is also
    # non-word, so \b doesn't fire. This is a known limitation of \b.
    assert _kw_in("lives--", "this.lives--;", word_boundary=True) is False
    assert _kw_in("lives--", "this.lives--;", word_boundary=False) is True

    # Same issue with leading non-word
    assert _kw_in("--lives", "score--lives;", word_boundary=True) is False
    assert _kw_in("--lives", "score--lives;", word_boundary=False) is True

    # Keywords with non-word INSIDE (not at edges) work fine
    assert _kw_in("player.lives", "if (player.lives <= 0)", word_boundary=True) is True


def test_word_boundary_word_to_word_transition_does_not_fire():
    """\\b only fires \\w<->\\W. Smashed keywords (R1.2.6) don't match '1.2.6'.

    This documents another foot-gun: if a keyword is preceded immediately by
    a word character (like 'R' before '1.2.6' in 'R1.2.6'), the leading \\b
    in the regex doesn't fire and the match silently fails.
    """
    from portal5_uat_driver import _kw_in

    # In 'R1.2.6', R is \w, 1 is \w, so no \b between them
    assert _kw_in("1.2.6", "Reference R1.2.6 applies", word_boundary=True) is False
    # But under legacy substring matching, it works
    assert _kw_in("1.2.6", "Reference R1.2.6 applies", word_boundary=False) is True
```

---

## Verification

```bash
cd $REPO_ROOT

# 1. Lint clean
ruff check tests/portal5_uat_driver.py tests/unit/test_uat_grading.py
ruff format --check tests/portal5_uat_driver.py tests/unit/test_uat_grading.py

# 2. Unit tests — should be 9 passing (7 from Phase 1 + 2 new)
python3 -m pytest tests/unit/test_uat_grading.py -v
# Expected: 9 passed

# 3. Spot-check the catalog: no remaining lives--/lives++ keywords
grep -n '"lives--"\|"lives++"' tests/portal5_uat_driver.py
# Expected: no output

# 4. Spot-check: CIP citations no longer use word_boundary
grep -B1 -A4 '"label": "Standard cited precisely"\|"label": "Precise citation"' tests/portal5_uat_driver.py
# Expected: no "word_boundary" line in either match

# 5. word_boundary still present on _CC01_ASSERTIONS Lives system
grep -B2 '"word_boundary": True' tests/portal5_uat_driver.py | grep "Lives system"
# Expected: hit
```

If all five succeed, this phase is complete.

---

## Out-of-scope

- **Re-running UAT.** This phase doesn't change observable test outcomes for any model that's already shipping `this.lives` or `livesCount` patterns. The fixes are defensive — they prevent **future** false negatives. Worth re-running only as part of a normal Phase 3 verification cycle.
- **Generalizing `word_boundary` to handle non-word-edge keywords.** Possible solutions exist (separate `\b?` anchors, manual character-class checks) but add complexity. For now the rule is: **when using `word_boundary: True`, ensure all keywords start and end with word characters.** Document this in a future helper-doc commit.
- **Row renumbering after `--rerun`.** When `--rerun` removes rows and re-adds them, row numbers in the markdown can be non-monotonic (e.g., `1, 3, 5, 1, 2`). Functional but cosmetic. Defer.
- **Cleaning up the orphaned `update_summary` function.** Phase 1 left it defined but no longer called; harmless dead code.

---

## Rollback

```bash
cd $REPO_ROOT
git restore tests/portal5_uat_driver.py tests/unit/test_uat_grading.py
python3 -m pytest tests/unit/test_uat_grading.py -v
```

---

## Commit

```bash
git add tests/portal5_uat_driver.py tests/unit/test_uat_grading.py
git diff --cached --stat
git commit -m "test(uat): phase 4 post-merge fixes

Two defects discovered during post-merge audit of Phase 2:

1. word_boundary regex \\b doesn't fire at non-word-char keyword edges.
   Silently breaks 'lives--' and 'lives++' (CC-01 Lives system) — the
   trailing -- is \\W and the next char in real JS code (e.g. 'this.lives--;')
   is also \\W, so the closing \\b finds no transition.

   Removed the two broken keywords; 'lives' and 'this.lives' (already in
   the list) cover the same code patterns. Added regression unit tests
   pinning the \\b limitation so future maintainers know the rule:
   word_boundary=True is incompatible with keywords that start or end
   with non-word characters.

2. word_boundary on CIP citations was defending against a non-existent
   threat (the original 'r1 in router 1' example was wrong — the space
   prevents the substring match). Meanwhile the flag introduces a real
   regression on smashed citation forms ('R1.2.6'). Net negative; flag
   removed from WS-16 'Standard cited precisely' and P-C01 'Precise
   citation'.

Refs: post-Phase-2 audit"
```

---

## Acceptance criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | `lives--` and `lives++` removed from `_CC01_ASSERTIONS` | `grep -n '"lives--"\|"lives++"'` finds nothing |
| 2 | `word_boundary` no longer set on CIP citations | `grep -B1 -A4 'Standard cited precisely\|Precise citation'` shows no word_boundary line |
| 3 | `word_boundary: True` still in place on Lives system block | grep finds it |
| 4 | 2 new unit tests pin the `\b` limitation | `pytest tests/unit/test_uat_grading.py -v` shows 9 PASS |
| 5 | Lint clean | ruff check + format check |
