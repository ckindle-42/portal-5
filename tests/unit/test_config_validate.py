import textwrap

from portal.platform.inference.config_validate import validate_config


def _write(tmp_path, body):
    p = tmp_path / "portal.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_valid_minimal(tmp_path):
    p = _write(
        tmp_path,
        """
        workspaces:
          auto-daily:
            model_hint: some-model
        mcp_servers:
          - id: memory
            port: 8920
    """,
    )
    assert validate_config(p) == []


def test_empty_model_hint_flagged(tmp_path):
    p = _write(
        tmp_path,
        """
        workspaces:
          bad:
            model_hint: ""
    """,
    )
    assert any("model_hint" in e for e in validate_config(p))


def test_duplicate_port_flagged(tmp_path):
    p = _write(
        tmp_path,
        """
        workspaces:
          w:
            model_hint: m
        mcp_servers:
          - id: a
            port: 8920
          - id: b
            port: 8920
    """,
    )
    assert any("collides" in e for e in validate_config(p))


def test_bad_bool_flagged(tmp_path):
    p = _write(
        tmp_path,
        """
        workspaces:
          w:
            model_hint: m
            memory_writeback: "yes"
    """,
    )
    assert any("memory_writeback" in e for e in validate_config(p))
