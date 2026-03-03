"""
Document Tools MCP Server
Exposes Word, PowerPoint, and Excel document creation as MCP tools.
Generated files are saved to OUTPUT_DIR with unique IDs.

Requires: pip install python-docx python-pptx openpyxl
Start with: python -m mcp.documents.document_mcp
"""

import logging
import os
import uuid
from pathlib import Path

from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

port = int(os.getenv("DOCUMENTS_MCP_PORT", "8913"))
mcp = FastMCP("document-tools", port=port)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "documents-mcp"})


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "create_word_document",
        "description": "Create a Word document",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Document content (markdown supported)"},
                "title": {"type": "string", "description": "Document title"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "create_powerpoint",
        "description": "Create a PowerPoint presentation",
        "parameters": {
            "type": "object",
            "properties": {
                "slides": {"type": "array", "description": "List of slide content"},
                "title": {"type": "string", "description": "Presentation title"},
            },
            "required": ["slides"],
        },
    },
    {
        "name": "create_excel",
        "description": "Create an Excel spreadsheet",
        "parameters": {
            "type": "object",
            "properties": {
                "data": {"type": "array", "description": "Array of rows"},
                "sheet_name": {"type": "string", "description": "Sheet name"},
            },
            "required": ["data"],
        },
    },
    {
        "name": "convert_document",
        "description": "Convert between document formats using pandoc",
        "parameters": {
            "type": "object",
            "properties": {
                "input_file": {"type": "string", "description": "Input file path"},
                "output_format": {"type": "string", "description": "Output format (docx, pdf, html, etc.)"},
            },
            "required": ["input_file", "output_format"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("GENERATED_FILES_DIR", "data/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _unique_path(name: str, ext: str) -> Path:
    """Return a unique output path."""
    uid = uuid.uuid4().hex[:8]
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name[:40]).strip("_")
    return OUTPUT_DIR / f"{safe}_{uid}.{ext}"


@mcp.tool()
def create_word_document(
    title: str,
    content: str,
    author: str = "Portal AI",
) -> dict:
    """
    Create a Word (.docx) document from a title and markdown-style content.

    Content supports:
    - '# Heading' → H1 heading
    - '## Heading' → H2 heading
    - '### Heading' → H3 heading
    - '- item' → bullet list item
    - Regular text → body paragraph

    Args:
        title: Document title (also used as filename base)
        content: Document body; supports basic markdown headings and bullets
        author: Author name for document metadata (default "Portal AI")

    Returns:
        dict with success, path (server path), and filename
    """
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError:
        return {
            "success": False,
            "error": "python-docx not installed. Run: pip install python-docx",
        }

    try:
        doc = Document()
        doc.core_properties.author = author
        doc.core_properties.title = title

        # Title heading
        heading = doc.add_heading(title, level=0)
        heading.runs[0].font.size = Pt(24)

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("### "):
                doc.add_heading(stripped[4:], level=3)
            elif stripped.startswith("## "):
                doc.add_heading(stripped[3:], level=2)
            elif stripped.startswith("# "):
                doc.add_heading(stripped[2:], level=1)
            elif stripped.startswith("- ") or stripped.startswith("* "):
                para = doc.add_paragraph(stripped[2:], style="List Bullet")
                para.paragraph_format.space_before = Pt(0)
            else:
                doc.add_paragraph(stripped)

        output_path = _unique_path(title, "docx")
        doc.save(str(output_path))
        return {"success": True, "path": str(output_path), "filename": output_path.name}
    except Exception as e:
        logger.exception("Word document creation failed")
        return {"success": False, "error": str(e)}


@mcp.tool()
def create_presentation(
    title: str,
    slides: list[dict],
    author: str = "Portal AI",
) -> dict:
    """
    Create a PowerPoint (.pptx) presentation.

    Each slide dict should have:
    - 'title': slide title (str)
    - 'content': slide body text or bullet points (str, newline-separated)
    - 'notes': speaker notes (str, optional)

    Args:
        title: Presentation title (used as filename base)
        slides: List of slide dicts with 'title', 'content', and optional 'notes'
        author: Author name for metadata (default "Portal AI")

    Returns:
        dict with success, path (server path), and filename
    """
    try:
        from pptx import Presentation
    except ImportError:
        return {
            "success": False,
            "error": "python-pptx not installed. Run: pip install python-pptx",
        }

    try:
        prs = Presentation()
        prs.core_properties.author = author
        prs.core_properties.title = title

        # Title slide
        title_layout = prs.slide_layouts[0]
        title_slide = prs.slides.add_slide(title_layout)
        title_slide.shapes.title.text = title

        # Content slides
        content_layout = prs.slide_layouts[1]
        for slide_data in slides:
            slide = prs.slides.add_slide(content_layout)
            slide.shapes.title.text = slide_data.get("title", "")
            body = slide.placeholders[1]
            tf = body.text_frame
            tf.clear()

            for i, line in enumerate(slide_data.get("content", "").splitlines()):
                stripped = line.strip()
                if not stripped:
                    continue
                if i == 0:
                    tf.text = stripped
                else:
                    tf.add_paragraph().text = stripped

            if "notes" in slide_data and slide_data["notes"]:
                notes_slide = slide.notes_slide
                notes_slide.notes_text_frame.text = slide_data["notes"]

        output_path = _unique_path(title, "pptx")
        prs.save(str(output_path))
        return {"success": True, "path": str(output_path), "filename": output_path.name}
    except Exception as e:
        logger.exception("Presentation creation failed")
        return {"success": False, "error": str(e)}


@mcp.tool()
def create_spreadsheet(
    title: str,
    sheets: list[dict],
) -> dict:
    """
    Create an Excel (.xlsx) spreadsheet.

    Each sheet dict should have:
    - 'name': worksheet tab name (str)
    - 'headers': column headers (list[str])
    - 'rows': data rows (list[list[any]])

    Args:
        title: Spreadsheet title (used as filename base and first sheet title)
        sheets: List of sheet dicts with 'name', 'headers', and 'rows'

    Returns:
        dict with success, path (server path), and filename
    """
    try:
        import openpyxl
        from openpyxl.styles import Font
    except ImportError:
        return {
            "success": False,
            "error": "openpyxl not installed. Run: pip install openpyxl",
        }

    try:
        wb = openpyxl.Workbook()
        wb.properties.title = title

        default_sheet = wb.active
        first = True

        for sheet_data in sheets:
            if first:
                ws = default_sheet
                ws.title = sheet_data.get("name", "Sheet1")
                first = False
            else:
                ws = wb.create_sheet(title=sheet_data.get("name", "Sheet"))

            headers = sheet_data.get("headers", [])
            if headers:
                ws.append(headers)
                # Bold headers
                for cell in ws[1]:
                    cell.font = Font(bold=True)

            for row in sheet_data.get("rows", []):
                ws.append(row)

        output_path = _unique_path(title, "xlsx")
        wb.save(str(output_path))
        return {"success": True, "path": str(output_path), "filename": output_path.name}
    except Exception as e:
        logger.exception("Spreadsheet creation failed")
        return {"success": False, "error": str(e)}


@mcp.tool()
def list_generated_files() -> list[dict]:
    """List recently generated documents in the output directory."""
    files = []
    for f in sorted(OUTPUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
        if f.is_file():
            files.append(
                {
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "type": f.suffix.lstrip("."),
                }
            )
    return files


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")
