"""UAT catalog group: auto-cad (CAD / 3D-print workspace).

Tests drive real conversations through the auto-cad workspace and the two CAD
personas. They verify that the model:
  1. Emits complete, syntactically valid OpenSCAD code
  2. Calls render_openscad and references the resulting PNG/STL
  3. Declares parametric variables (not hardcoded magic numbers)
  4. Applies printability constraints when asked

Assertion strategy: we can't run the SCAD code in UAT, so we check for the
structural markers that indicate a real, complete response — named variable
declarations, the openscad fenced block, and evidence the render tool was
called (png_url, stl_path, or file path in the response).
"""

from __future__ import annotations

from portal.platform.data_loader import load_data

TESTS: list[dict] = load_data("tests/data", "uat_catalog_g_auto_cad")
