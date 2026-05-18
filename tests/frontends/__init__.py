"""Frontend-specific UAT driver helpers.

Two execution paths exist:
- Open WebUI (default): helpers live in tests/portal5_uat_driver.py as owui_* /
  _login / _send_and_wait. They are NOT relocated here — back-compat takes
  priority over symmetry.
- LibreChat: pure Playwright helpers in tests/frontends/librechat.py.

Dispatch is decided in portal5_uat_driver.py via `_fe_*` shim functions that
branch on the module-level `FRONTEND_MODE`.
"""
