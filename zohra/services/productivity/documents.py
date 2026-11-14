"""Create-only document exports with bridge-bound approval and verified downloads."""
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import stat
import time
from datetime import datetime, timezone
from uuid import uuid4
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zohra.services.tool_execution.state import CapabilityStore


TOOL_ID = "documents.create"
ACTION = "export_document"
MAX_OUTPUT_BYTES = 20_000_000
DEPENDENCIES = {"pdf": ("reportlab", "pypdf"), "docx": ("docx",), "xlsx": ("openpyxl",)}
MEDIA_TYPES = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class DocumentError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class DocumentInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    format: str = Field(pattern=r"^(pdf|docx|xlsx)$")
    filename: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=180)
    content: str = Field(min_length=1, max_length=100000)

    @model_validator(mode="after")
    def safe_content(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]*\.(pdf|docx|xlsx)", self.filename) or not self.filename.lower().endswith("." + self.format):
            raise ValueError("Use a plain filename with the matching .pdf, .docx or .xlsx extension")
        if re.match(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", self.filename, re.I):
            raise ValueError("Reserved Windows filenames are not allowed")
        if len(self.content.encode("utf-8")) > 100000 or not self.content.strip():
            raise ValueError("Document content must be non-empty and under 100 KB")
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", self.title + self.content):
            raise ValueError("Unsupported control characters in document text")
        return self


class Approval(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9-]{1,128}$")
    session: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")


class PdfInspectionInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    filename: str = Field(min_length=1, max_length=120)
    query: str = Field(default="", max_length=120)
    page: int | None = Field(default=None, ge=1, le=120)

    @model_validator(mode="after")
    def validate_request(self):
        DocumentInput(format="pdf", filename=self.filename, content="path validation")
        self.query = self.query.strip()
        if self.query and self.page is not None:
            raise ValueError("Search the entire PDF or read one page, not both at once")
        if re.search(r"[\x00-\x1f\x7f]", self.query):
            raise ValueError("Search text contains unsupported control characters")
        return self


def require_dependencies(format):
    missing = [name for name in DEPENDENCIES[format] if importlib.util.find_spec(name) is None]
    if missing:
        raise DocumentError("DEPENDENCY_MISSING", "Document export needs: " + ", ".join(missing))


def workbook_rows(content):
    try:
        rows = json.loads(content) if content.lstrip().startswith(("[", "{")) else list(csv.reader(io.StringIO(content), strict=True))
    except (ValueError, csv.Error) as error:
        raise DocumentError("INVALID_TABLE", f"Invalid CSV or JSON row array: {error}") from error
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000 or any(not isinstance(row, list) for row in rows):
        raise DocumentError("INVALID_TABLE", "Supply 1 to 1000 rows as CSV or a JSON array of row arrays")
    width = len(rows[0])
    if not 1 <= width <= 50 or len(rows) * width > 20000 or any(len(row) != width for row in rows):
        raise DocumentError("INVALID_TABLE", "Rows must have the same 1 to 50 columns, with at most 20000 cells")
    for row in rows:
        for cell in row:
            if not (cell is None or type(cell) in (str, bool, int, float)):
                raise DocumentError("INVALID_TABLE", "Cells must contain text, numbers, booleans or null, not objects")
            if isinstance(cell, str) and (len(cell) > 32767 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", cell)):
                raise DocumentError("INVALID_TABLE", "Cell text is too long or contains unsupported control characters")
            if type(cell) in (int, float) and (abs(cell) > 2**53 or not math.isfinite(cell)):
                raise DocumentError("INVALID_TABLE", "Numbers must be finite and within Excel's safe integer range")
    return rows


def checked_path(store, filename):
    root = store.root.absolute()
    target = root / "files" / "documents" / filename
    for candidate in (target, *target.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise DocumentError("UNSAFE_PATH", "Document storage cannot use links or junctions")
        if candidate.exists() and candidate.is_file() and candidate.stat().st_nlink > 1:
            raise DocumentError("UNSAFE_PATH", "Document storage cannot use hard links")
    return target


def prepare_document(raw_args, store=None):
    args = DocumentInput.model_validate(raw_args)
    store = store or CapabilityStore()
    if not store.enabled(TOOL_ID):
        raise DocumentError("TOOL_DISABLED", "Document creation was revoked")
    require_dependencies(args.format)
    target = checked_path(store, args.filename)
    if target.exists():
        raise DocumentError("FILE_EXISTS", "That document already exists. Choose another filename; it will not be overwritten")
    rows = workbook_rows(args.content) if args.format == "xlsx" else None
    if args.format == "pdf":
        try:
            (args.title + args.content).encode("cp1252")
        except UnicodeEncodeError as error:
            raise DocumentError("UNSUPPORTED_TEXT", "PDF export currently supports Western text. Use Word for Hindi or other complex scripts; PDF shaping is not integrated") from error
    summary = f"{len(rows)} rows and {len(rows[0])} columns" if rows else f"{len(args.content.encode('utf-8'))} bytes of supplied text"
    return {"args": args.model_dump(), "description": f"Create {args.format.upper()} document files/documents/{args.filename} from {summary}.",
            "consequence": "Creates one new local file only after confirmation. No overwrite, cloud upload, email or trading action. Spreadsheet strings remain literal, not executable formulas."}


def claim_document(approval, args, store):
    if approval is None:
        raise DocumentError("CONFIRMATION_REQUIRED", "A separate confirmed document action is required")
    approved = Approval.model_validate(approval)
    with store.session() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='confirmations'").fetchone():
            raise DocumentError("STALE_CONFIRMATION", "No document approval exists")
        row = db.execute("SELECT * FROM confirmations WHERE id=? AND session=?", (approved.id, approved.session)).fetchone()
        enabled = db.execute("SELECT enabled FROM tool_controls WHERE tool_id=?", (TOOL_ID,)).fetchone()
        if enabled is not None and not enabled["enabled"]:
            raise DocumentError("TOOL_DISABLED", "Document creation was revoked")
        if not row or row["status"] != "executing" or row["action"] != ACTION or row["expires"] < time.time() * 1000 or json.loads(row["args"]) != args:
            raise DocumentError("STALE_CONFIRMATION", "Document export lacks an exact current bridge approval")
        db.execute("CREATE TABLE IF NOT EXISTS document_claims(confirmation_id TEXT PRIMARY KEY)")
        if db.execute("SELECT 1 FROM document_claims WHERE confirmation_id=?", (approved.id,)).fetchone():
            raise DocumentError("STALE_CONFIRMATION", "Document approval already consumed")
        db.execute("INSERT INTO document_claims VALUES(?)", (approved.id,))
    return approved


def build_pdf(args):
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("DocumentBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=11,
                          leading=16, spaceAfter=7, alignment=TA_LEFT, splitLongWords=True)
    blocks = []
    if args.title:
        blocks.append(Paragraph(escape(args.title), styles["Title"]))
        blocks.append(Spacer(1, 12))
    for line in args.content.splitlines():
        blocks.append(Paragraph(escape(line).replace("\t", "    "), body) if line else Spacer(1, 8))
    document = SimpleDocTemplate(stream, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50,
                                 title=args.title or args.filename, author="Zohra")
    document.build(blocks)
    return stream.getvalue()


def build_docx(args):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    document = Document()
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.7)
    section.left_margin = section.right_margin = Inches(0.8)
    for name in ("Normal", "Title"):
        document.styles[name].font.name = "Calibri"
        document.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    document.styles["Normal"].font.size = Pt(11)
    document.styles["Normal"].paragraph_format.space_after = Pt(7)
    document.core_properties.author = "Zohra"
    document.core_properties.title = args.title or args.filename
    if args.title:
        document.add_paragraph(args.title, style="Title")
    for line in args.content.splitlines():
        document.add_paragraph(line)
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def build_xlsx(args):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    rows = workbook_rows(args.content)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    workbook.properties.creator = "Zohra"
    workbook.properties.title = args.title or args.filename
    for row_number, values in enumerate(rows, 1):
        for column, value in enumerate(values, 1):
            cell = sheet.cell(row_number, column, value)
            if isinstance(value, str):
                cell.data_type = "s"
            cell.font = Font(name="Calibri", size=11, bold=row_number == 1, color="FFFFFF" if row_number == 1 else "202428")
            if row_number == 1:
                cell.fill = PatternFill("solid", fgColor="17645B")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        longest = max((len(str(value or "")) for value in values), default=0)
        sheet.row_dimensions[row_number].height = min(120, 20 + (longest // 38) * 15)
    for column in range(1, len(rows[0]) + 1):
        width = max(len(str(row[column - 1] or "")) for row in rows)
        sheet.column_dimensions[get_column_letter(column)].width = min(42, max(16, width + 3))
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def verify_document(data, args):
    if not data or len(data) > MAX_OUTPUT_BYTES:
        raise DocumentError("VERIFICATION_FAILED", "Document output is empty or exceeds 20 MB")
    stream = io.BytesIO(data)
    if args.format == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(stream, strict=True)
        actual = "".join(page.extract_text() or "" for page in reader.pages)
        expected = args.title + args.content
        normalize = lambda value: re.sub(r"\s+", "", value)
        if not reader.pages or normalize(actual) != normalize(expected):
            raise DocumentError("VERIFICATION_FAILED", "PDF text differs from the approved content")
        return {"pages": len(reader.pages)}
    if args.format == "docx":
        from docx import Document
        document = Document(stream)
        expected = ([args.title] if args.title else []) + args.content.splitlines()
        if [paragraph.text for paragraph in document.paragraphs] != expected:
            raise DocumentError("VERIFICATION_FAILED", "Word text differs from the approved content")
        return {"paragraphs": len(expected)}
    from openpyxl import load_workbook
    workbook = load_workbook(stream, data_only=False, read_only=True, keep_links=False)
    try:
        rows = workbook_rows(args.content)
        expected = [[None if value == "" else value for value in row] for row in rows]
        sheet = workbook["Data"]
        actual = [list(row) for row in sheet.iter_rows(min_row=1, max_row=len(rows), max_col=len(rows[0]), values_only=True)]
        if actual != expected or any(cell.data_type == "f" for row in sheet.iter_rows() for cell in row):
            raise DocumentError("VERIFICATION_FAILED", "Workbook cells differ or contain unapproved formulas")
        return {"rows": len(rows), "columns": len(rows[0]), "formulas": 0}
    finally:
        workbook.close()


def artifact_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS document_artifacts(id TEXT PRIMARY KEY, session TEXT NOT NULL,
        filename TEXT NOT NULL, format TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
        details TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)""")


def execute_document(raw_args, approval, store=None):
    store = store or CapabilityStore()
    args = DocumentInput.model_validate(raw_args)
    approved = claim_document(approval, args.model_dump(), store)
    prepare_document(args.model_dump(), store)
    data = {"pdf": build_pdf, "docx": build_docx, "xlsx": build_xlsx}[args.format](args)
    details = verify_document(data, args)
    target = checked_path(store, args.filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    checked_path(store, args.filename)
    # Exclusive creation preserves originals even when two sessions choose the same name.
    with target.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    saved = target.read_bytes()
    if saved != data:
        raise DocumentError("VERIFICATION_FAILED", "Saved document differs from the generated output")
    details = verify_document(saved, args)
    artifact_id = str(uuid4())
    digest = hashlib.sha256(saved).hexdigest()
    with store.session() as db:
        artifact_schema(db)
        db.execute("INSERT INTO document_artifacts(id,session,filename,format,sha256,bytes,details) VALUES(?,?,?,?,?,?,?)",
                   (artifact_id, approved.session, args.filename, args.format, digest, len(saved), json.dumps(details)))
    return {"artifact_id": artifact_id, "filename": args.filename, "format": args.format,
            "path": "files/documents/" + args.filename, "bytes": len(saved), "sha256": digest,
            "details": details, "verified": True,
            "response": f"TASK: Created and verified {args.filename} in assistant_workspace/files/documents. No existing file was overwritten."}


def list_documents(session, store=None):
    store = store or CapabilityStore()
    with store.session() as db:
        artifact_schema(db)
        return [dict(row) for row in db.execute("SELECT id AS artifact_id,filename,format,bytes,created FROM document_artifacts WHERE session=? ORDER BY rowid DESC LIMIT 100", (session,))]


def read_document(session, artifact_id, store=None):
    store = store or CapabilityStore()
    with store.session() as db:
        artifact_schema(db)
        row = db.execute("SELECT * FROM document_artifacts WHERE id=? AND session=?", (artifact_id, session)).fetchone()
    if row is None:
        raise DocumentError("NOT_FOUND", "No document belongs to this conversation")
    DocumentInput(format=row["format"], filename=row["filename"], content="path validation")
    target = checked_path(store, row["filename"])
    with target.open("rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_OUTPUT_BYTES:
            raise DocumentError("UNSAFE_PATH", "Document is not a regular bounded file")
        data = source.read(MAX_OUTPUT_BYTES + 1)
    if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise DocumentError("VERIFICATION_FAILED", "Document changed since creation; download blocked")
    return data, row["filename"], MEDIA_TYPES[row["format"]]


def inspect_pdf(session_id, filename, query="", page=None, store=None):
    request = PdfInspectionInput(session_id=session_id, filename=filename, query=query, page=page)
    store = store or CapabilityStore()
    if not store.enabled("document.pdf"):
        raise DocumentError("TOOL_DISABLED", "PDF inspection was revoked")
    with store.session() as db:
        artifact_schema(db)
        row = db.execute("SELECT id FROM document_artifacts WHERE session=? AND filename=? AND format='pdf'",
                         (request.session_id, request.filename)).fetchone()
    if row is None:
        raise DocumentError("NOT_FOUND", "No verified PDF with that name belongs to this conversation")
    data, _, media_type = read_document(request.session_id, row["id"], store)
    if media_type != MEDIA_TYPES["pdf"]:
        raise DocumentError("INVALID_FORMAT", "Only PDF documents can be inspected here")
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data), strict=True)
    count = len(reader.pages)
    if not 1 <= count <= 120:
        raise DocumentError("UNSUPPORTED_DOCUMENT", "PDF must have 1 to 120 pages")
    if request.page is not None and request.page > count:
        raise DocumentError("INVALID_PAGE", f"PDF has {count} pages; requested page {request.page} does not exist")
    base = {"source": "verified local assistant PDF", "observed_at": datetime.now(timezone.utc).isoformat(),
            "filename": request.filename, "page_count": count, "query": request.query,
            "limitations": "Text extraction only; scanned image pages need OCR, which is not integrated. No cloud upload."}
    if request.query:
        matches = []
        total = 0
        has_text = False
        pattern = re.compile(re.escape(request.query), re.IGNORECASE)
        for number, pdf_page in enumerate(reader.pages, 1):
            text = pdf_page.extract_text() or ""
            has_text = has_text or bool(text.strip())
            for found in pattern.finditer(text):
                total += 1
                if len(matches) < 10:
                    snippet = re.sub(r"\s+", " ", text[max(0, found.start()-70):min(len(text), found.end()+70)]).strip()
                    matches.append({"page": number, "snippet": snippet})
        return {**base, "matches": matches, "match_count": total, "matches_truncated": total > len(matches),
                "pages": [], "displayed_pages": 0, "text_available": has_text}
    selected = [request.page] if request.page is not None else list(range(1, min(count, 3) + 1))
    pages = []
    for number in selected:
        text = reader.pages[number - 1].extract_text() or ""
        pages.append({"page": number, "text": text[:4000], "characters": len(text), "truncated": len(text) > 4000})
    return {**base, "pages": pages, "displayed_pages": len(pages), "matches": [], "match_count": 0,
            "matches_truncated": False, "text_available": any(item["characters"] for item in pages)}
