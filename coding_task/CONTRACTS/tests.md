# Tests addendum

- Never touch a real store; use `tmp_path` for files and databases.
- Mock Telegram; set `PORTAL_ARM_TELEGRAM_DB` and override queue claim paths inside `tmp_path`.
