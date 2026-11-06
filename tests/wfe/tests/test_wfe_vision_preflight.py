"""Vision preflight probes the image route the suite rows use.

A text-only probe of auto-vision is rerouted to auto-reasoning, which serves a
QAT tag through its oMLX alias. The image rows stay on ollama-vision. The probe
sends one inline image when the rows do, and a real model mismatch still REVIEWs.
"""

import base64
import json

from tests.wfe import campaign as camp

QAT = "gemma4:26b-a4b-it-qat-ctx8k"
ALIAS = "gemma-4-26b-a4b-it-QAT-4bit"
TEXT = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"


def _suite(tmp_path, name, task_id, images=None, turns=None):
    path = tmp_path / f"{name}.jsonl"
    task = {"id": task_id, "instruction": "ready", "checkers": []}
    if images is not None:
        task["images"] = images
    if turns is not None:
        task["turns"] = turns
    path.write_text(json.dumps(task) + "\n")
    return path


def _row(workspace, model, suite, task_id):
    return {
        "workspace": workspace,
        "model": model,
        "arm": model,
        "suite_path": str(suite),
        "task_id": task_id,
        "run_id": f"{workspace}|{model}|s|{task_id}|r0",
        "state": "PENDING",
    }


def _offline(monkeypatch, chat):
    monkeypatch.setattr(camp, "chat", chat)
    monkeypatch.setattr(
        camp,
        "observe_identity",
        lambda backend, model: ({"backend": backend, "model": model, "content": "c1"}, ""),
    )
    monkeypatch.setattr(camp, "deployed_build", lambda: "abc1234")
    monkeypatch.setattr(camp, "deployed_matches", lambda _build: True)
    monkeypatch.setattr(camp, "deployed_services", lambda: {})


def _image_part(content):
    assert isinstance(content, list)
    parts = [p for p in content if isinstance(p, dict) and p.get("type") == "image_url"]
    assert parts
    return parts[0]["image_url"]["url"]


def test_an_image_workload_freezes_the_image_route(tmp_path, monkeypatch):
    """The QAT tag's text route is the oMLX alias. The image probe freezes ollama-vision."""
    assert camp.seat_primary("auto-vision", QAT) == QAT
    assert camp._serving_seat("auto-reasoning", QAT) == ("omlx-general", ALIAS)
    suite = _suite(tmp_path, "vision", "vis-1", images=["tests/fixtures/vision/natural-00.png"])
    rows = [_row("auto-vision", QAT, suite, "vis-1")]
    seen = {}

    def chat(ws, msgs, tools=True, harness=None, **k):
        content = msgs[0]["content"]
        seen["content"] = content
        image = isinstance(content, list) and any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in content
        )
        model = QAT if image else ALIAS
        backend = "ollama-vision" if image else "omlx-general"
        return {"served": {"backend": backend, "model": model}}

    _offline(monkeypatch, chat)
    monkeypatch.setattr(camp, "ENGINE", "pipeline")
    d = tmp_path / "c"
    d.mkdir()
    manifest = {"rows": rows}
    camp.save_manifest(d, manifest)
    pf = camp._arm_preflight(d, manifest, rows, QAT, False)
    assert pf["verdict"] == "OK"
    url = _image_part(seen["content"])
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]).startswith(b"\x89PNG")
    frozen = camp.load_manifest(d)["identity_map"][f"auto-vision|{QAT}"]
    assert frozen == {"backend": "ollama-vision", "model": QAT, "content": "c1"}


def test_a_text_workload_probe_stays_text_only(tmp_path, monkeypatch):
    """No image part for a text suite, another model's image rows, or a bare probe."""
    text_suite = _suite(tmp_path, "text", "t-1")
    image_suite = _suite(tmp_path, "vision", "vis-1", images=["x.png"])
    turned = _suite(
        tmp_path,
        "realuse",
        "ru-1",
        images=["x.jpg"],
        turns=[{"user": "describe the file"}],
    )
    text_row = _row("auto-compliance", TEXT, text_suite, "t-1")
    other_model = _row("auto-vision", QAT, image_suite, "vis-1")
    turned_row = _row("auto-vision", QAT, turned, "ru-1")
    seen = []

    def chat(ws, msgs, tools=True, harness=None, **k):
        seen.append((ws, msgs[0]["content"]))
        model = (harness or {})["pipeline_model"]
        return {"served": {"backend": "stub", "model": camp.seat_primary(ws, model)}}

    _offline(monkeypatch, chat)
    rows = [text_row, other_model, turned_row]
    pf = camp.preflight_pipeline(["auto-compliance", "auto-vision"], TEXT, rows)
    assert pf["verdict"] == "OK"
    assert seen == [
        ("auto-compliance", "Reply with the word ready."),
        ("auto-vision", "Reply with the word ready."),
    ]
    seen.clear()
    camp.preflight_pipeline(["auto-compliance"], TEXT)
    assert seen == [("auto-compliance", "Reply with the word ready.")]
    seen.clear()
    # A scripted-turn task lists `images` for fixtures; the runner does not send them as parts.
    camp.preflight_pipeline(["auto-vision"], QAT, [turned_row])
    assert seen == [("auto-vision", "Reply with the word ready.")]
    frozen_model = pf["identities"][f"auto-compliance|{TEXT}"]["model"]
    assert frozen_model == "Qwen3.8-27B-oQ4e-mtp"


def test_an_image_route_mismatch_still_reviews(tmp_path, monkeypatch):
    """An alias served on the image probe is a mismatch. It is not accepted."""
    suite = _suite(tmp_path, "vision", "vis-1", images=["x.png"])
    rows = [_row("auto-vision", QAT, suite, "vis-1")]
    seen = {}

    def chat(ws, msgs, tools=True, harness=None, **k):
        seen["content"] = msgs[0]["content"]
        return {"served": {"backend": "omlx-general", "model": ALIAS}}

    _offline(monkeypatch, chat)
    pf = camp.preflight_pipeline(["auto-vision"], QAT, rows)
    assert _image_part(seen["content"])
    assert pf["verdict"] == "REVIEW"
    assert pf["findings"] == [
        f"auto-vision: pipeline served {ALIAS!r}, seat is {QAT!r} (arm {QAT!r})"
    ]
