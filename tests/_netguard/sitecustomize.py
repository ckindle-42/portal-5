"""Puts Python subprocesses of unit tests inside the offline boundary."""

import os

if os.environ.get("PORTAL_NETGUARD") == "1":
    import importlib.util
    import pathlib

    _p = pathlib.Path(__file__).with_name("netguard.py")
    _spec = importlib.util.spec_from_file_location("_portal_netguard", _p)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _mod.install()
