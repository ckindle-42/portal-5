# UAT Calibration Workflow

Before adding or updating `assert_contains` / `assert_any_of` entries in the UAT test catalog, run a calibration pass. Calibration captures real responses so signal choices are grounded in what models actually produce — not guesses.

---

## Step 1 — Capture responses

```bash
python3 tests/portal5_uat_driver.py --calibrate --calibrate-output calibration.json
```

This runs every test once (or a subset with `--section` / `--test`) and saves a JSON file with one record per test:

```json
{
  "test_id": "WS-01",
  "name": "Auto Router — Intent-Driven Routing",
  "section": "auto",
  "workspace": "auto",
  "prompt": "I need to deploy a containerized Python app...",
  "response_text": "Here are the Deployment and Service manifests...",
  "chat_url": "http://localhost:8080/c/abc123",
  "review_tag": "",
  "timestamp": "2026-04-25T14:30:00Z"
}
```

---

## Step 2 — Review and tag

Open `calibration.json` and set `review_tag` for each entry:

| Tag | Meaning |
|-----|---------|
| `"good"` | Response is correct and representative — use for signal extraction |
| `"bad"` | Response is wrong, incomplete, or refused — do not use |
| `"skip"` | Exclude from signal extraction (neutral / not enough content) |

Leave `review_tag` as `""` to skip an entry silently.

---

## Step 3 — Generate signals

```bash
python3 tests/portal5_uat_driver.py \
  --emit-signals-from calibration.json \
  --calibrate-output updated_signals.py
```

This writes `updated_signals.py` containing:

- `CALIBRATION_SIGNALS` dict — top-10 TF-IDF keywords per section
- Suggested `assert_contains` entries for the UAT test catalog

---

## Step 4 — Integrate

Review `updated_signals.py`, then:

1. Merge relevant entries into `tests/quality_signals.py` (`QUALITY_SIGNALS` dict)
2. Add suggested `assert_any_of` entries to matching tests in `portal5_uat_driver.py`
3. Commit both files with a message like:
   ```
   test(uat): update quality signals from calibration-YYYY-MM-DD
   ```

---

## Notes

- Re-run calibration whenever prompts change significantly.
- The IDF weighting reduces generic words (e.g. "response", "model") and surfaces domain-specific terms.
- Use `--section <name>` to calibrate a single section without running the full suite.
