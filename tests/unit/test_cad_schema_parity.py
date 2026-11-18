from __future__ import annotations

import jsonschema

from portal.modules.cad.tools.scad_emitter import geometry_schema, validate_geometry


def test_schema_examples_validate_against_schema():
    # The auto-cad prompt (P4-A) no longer inlines a JSON example; the schema's own
    # `examples` are the canonical ones the model sees via the tool manifest.
    examples = geometry_schema()["examples"]
    assert examples
    for example in examples:
        jsonschema.validate(example, geometry_schema())
        assert validate_geometry(example) == []
