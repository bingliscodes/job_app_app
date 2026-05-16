from __future__ import annotations

from pathlib import Path

from jobapp.models import ParsedResume


def parse_resume(path: str) -> ParsedResume:
    """Extract text from a resume file. Supports PDF, DOCX, and plain text."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Resume not found: {p.resolve()}")

    suffix = p.suffix.lower()

    if suffix == ".pdf":
        text = _parse_pdf(p)
    elif suffix == ".docx":
        text = _parse_docx(p)
    elif suffix in (".txt", ".md"):
        text = p.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported resume format: {suffix}. Use .pdf, .docx, .txt, or .md")

    if not text.strip():
        raise ValueError(f"No text could be extracted from {p.name}")

    return ParsedResume(raw_text=text, source_format=suffix.lstrip("."), source_path=str(p))


def _parse_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _parse_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n\n".join(para.text for para in doc.paragraphs if para.text.strip())
