"""Sample splitting in scripts/portal5-powermetrics.py (buffer leak regression)."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "portal5-powermetrics.py"
_spec = importlib.util.spec_from_file_location("portal5_powermetrics", _PATH)
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)


def _sample(cpu_mw: float) -> list[bytes]:
    # Shape of real `powermetrics -f plist` output: milliwatts as <real>,
    # combined_power = cpu + gpu + ane (must not be counted again).
    return [
        b'<?xml version="1.0" encoding="UTF-8"?>\n',
        b"<plist><dict><key>processor</key><dict>\n",
        f"<key>cpu_power</key><real>{cpu_mw}</real>\n".encode(),
        b"<key>gpu_power</key><real>26881.1</real>\n",
        b"<key>ane_power</key><real>0</real>\n",
        f"<key>combined_power</key><real>{cpu_mw + 26881.1}</real>\n".encode(),
        b"</dict></dict>\n",
        b"</plist>\n",
    ]


def test_nul_separated_samples_are_each_yielded():
    first = _sample(6553.71)
    second = _sample(2000.0)
    second[0] = b"\x00" + second[0]  # powermetrics puts a NUL between samples
    docs = list(pm.iter_plist_documents(first + second))
    assert len(docs) == 2
    assert pm.parse_plist_buffer(docs[1]) == {"cpu_w": 2.0, "gpu_w": 26.8811, "ane_w": 0.0}


def test_buffer_is_bounded_without_boundary(monkeypatch):
    monkeypatch.setattr(pm, "MAX_BUFFER_LINES", 10)
    lines = [b"<key>x</key>\n"] * 100 + _sample(500.0)
    docs = list(pm.iter_plist_documents(lines))
    assert len(docs) == 1
    assert len(docs[0].splitlines()) <= 10 + len(_sample(500.0))
