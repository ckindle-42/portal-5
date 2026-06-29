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

TESTS: list[dict] = [
    # ── Workspace tests (auto-cad) ─────────────────────────────────────────
    {
        "id": "WS-CAD-01",
        "name": "CAD Workspace — Parametric Mounting Bracket",
        "section": "auto-cad",
        "model_slug": "auto-cad",
        "timeout": 300,
        "workspace_tier": "ollama",
        "prompt": (
            "Design a parametric mounting bracket in OpenSCAD. "
            "The bracket should have a 60×40mm base with two M4 mounting holes (3mm clearance), "
            "a 90° upright arm 30mm tall and 4mm thick, and a 2mm fillet on the inner corner. "
            "All dimensions must be named variables. Render it and show me the preview."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "OpenSCAD code block present",
                "keywords": [
                    "```openscad",
                    "```scad",
                    "module ",
                    "linear_extrude",
                    "translate(",
                    "cube(",
                    "cylinder(",
                ],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Named dimension variables declared",
                "keywords": [
                    "base_w",
                    "base_width",
                    "arm_height",
                    "wall",
                    "thickness",
                    "clearance",
                    "fillet",
                    "=",
                ],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "M4 / hole feature present",
                "keywords": ["m4", "hole", "3.0", "3mm", "cylinder", "translate"],
            },
            {
                "type": "any_of",
                "label": "render_openscad called — PNG or STL referenced in response",
                "keywords": [
                    "png_url",
                    "stl_path",
                    ".png",
                    ".stl",
                    "rendered",
                    "preview",
                    "/files/models3d/",
                ],
                "critical": False,
            },
            {
                "type": "not_contains",
                "label": "No CadQuery import attempted",
                "keywords": [
                    "import cadquery",
                    "import build123d",
                    "cq.Workplane",
                    "from cadquery",
                ],
            },
        ],
    },
    {
        "id": "WS-CAD-02",
        "name": "CAD Workspace — Hex Enclosure with Lid",
        "section": "auto-cad",
        "model_slug": "auto-cad",
        "timeout": 300,
        "workspace_tier": "ollama",
        "prompt": (
            "Create an OpenSCAD script for a simple electronics enclosure: "
            "80×50×30mm rectangular box, 2mm wall thickness, open top for a snap-fit lid. "
            "The lid should be a separate module that fits over the box with 0.2mm clearance. "
            "Use named variables throughout. Render the box and show me the preview."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "OpenSCAD code block present",
                "keywords": ["```openscad", "```scad", "module ", "difference(", "cube("],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Wall thickness variable declared",
                "keywords": ["wall", "wall_t", "thickness", "wall_thickness", "wall ="],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Clearance/tolerance variable declared",
                "keywords": ["clearance", "tolerance", "fit", "0.2"],
            },
            {
                "type": "any_of",
                "label": "Two modules (box + lid)",
                "keywords": [
                    "module lid",
                    "module box",
                    "module enclosure",
                    "module top",
                    "module cover",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Render called — artifact referenced",
                "keywords": [
                    "png_url",
                    ".png",
                    ".stl",
                    "rendered",
                    "preview",
                    "/files/models3d/",
                    "stl_path",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "WS-CAD-03",
        "name": "CAD Workspace — Convert STL to OBJ",
        "section": "auto-cad",
        "model_slug": "auto-cad",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "I have a file called smoke_box.stl in the workspace. "
            "Please convert it to OBJ format and tell me the output URL."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Convert tool called — OBJ output referenced",
                "keywords": [".obj", "output_url", "converted", "obj format", "/files/models3d/"],
                "critical": True,
            },
            {
                "type": "not_contains",
                "label": "No error reported",
                "keywords": [
                    "file not found",
                    "conversion failed",
                    "unable to convert",
                    "could not find",
                    "does not exist",
                ],
            },
        ],
    },
    # ── Persona tests ──────────────────────────────────────────────────────
    {
        "id": "P-CAD-01",
        "name": "CAD Designer Persona — Spur Gear",
        "section": "auto-cad",
        "model_slug": "cadquerydesigner",
        "timeout": 300,
        "workspace_tier": "ollama",
        "prompt": (
            "Design a spur gear with 20 teeth, module 2, 10mm face width, and a 6mm bore. "
            "All parameters must be named variables. Render and show me the preview."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "OpenSCAD or parametric geometry code present",
                "keywords": [
                    "```openscad",
                    "```scad",
                    "module gear",
                    "module spur",
                    "teeth",
                    "module =",
                    "modul =",
                ],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Named tooth/module variables",
                "keywords": [
                    "teeth",
                    "num_teeth",
                    "tooth_count",
                    "module",
                    "modul",
                    "face_width",
                    "bore",
                ],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Render called — PNG or STL referenced",
                "keywords": ["png_url", ".png", ".stl", "rendered", "preview", "/files/models3d/"],
                "critical": False,
            },
            {
                "type": "not_contains",
                "label": "No CadQuery import",
                "keywords": ["import cadquery", "import build123d", "cq.Workplane"],
            },
        ],
    },
    {
        "id": "P-CAD-02",
        "name": "Printability Engineer Persona — FDM Bracket Analysis",
        "section": "auto-cad",
        "model_slug": "printabilityengineer",
        "timeout": 300,
        "workspace_tier": "ollama",
        "prompt": (
            "I need a wall-mount bracket for a Raspberry Pi 4. "
            "Design it for FDM printing on a 0.4mm nozzle with PETG. "
            "The bracket must hold the Pi securely (58×49mm board, M2.5 holes at corners), "
            "with a 45° chamfer on any overhang. Declare nozzle_dia, wall_count, "
            "overhang_limit_deg, and clearance as named variables. Render the result."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "OpenSCAD code block present",
                "keywords": [
                    "```openscad",
                    "```scad",
                    "module ",
                    "linear_extrude",
                    "cube(",
                    "cylinder(",
                ],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "DfAM parameters declared",
                "keywords": [
                    "nozzle_dia",
                    "nozzle",
                    "wall_count",
                    "overhang",
                    "clearance",
                    "layer_height",
                ],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Chamfer or overhang mitigation referenced",
                "keywords": ["chamfer", "45", "overhang", "support", "angle"],
            },
            {
                "type": "any_of",
                "label": "M2.5 / mounting holes addressed",
                "keywords": ["m2.5", "2.5", "hole", "mount", "screw", "cylinder"],
            },
            {
                "type": "any_of",
                "label": "Render called — artifact referenced",
                "keywords": ["png_url", ".png", ".stl", "rendered", "preview", "/files/models3d/"],
                "critical": False,
            },
        ],
    },
]
