from __future__ import annotations

import json
from pathlib import Path

from jobapp.models import (
    EducationEntry,
    ExperienceEntry,
    ParsedResume,
    ProjectEntry,
    StructuredResume,
)

STRUCTURE_PROMPT = """\
You are a resume parser. Extract the resume text into structured JSON.

Rules:
- Extract ONLY what is explicitly written in the resume. Do not infer, add, or embellish.
- If a section is missing from the resume, return an empty list for that field.
- For skills, extract every technology, tool, language, framework, and methodology mentioned \
anywhere in the resume (in skills sections, experience bullets, project descriptions, etc.)
- Keep bullet points exactly as written — do not rephrase them.

Return valid JSON in this exact format:
{
  "name": "Candidate's full name",
  "contact": "Email, phone, location, LinkedIn — whatever is listed",
  "summary": "Professional summary/objective if present, otherwise empty string",
  "skills": ["skill1", "skill2", ...],
  "experience": [
    {
      "company": "Company Name",
      "title": "Job Title",
      "dates": "Start - End",
      "bullets": ["Achievement or responsibility 1", ...]
    }
  ],
  "education": [
    {
      "institution": "School Name",
      "degree": "Degree and field",
      "dates": "Years",
      "details": ["GPA, honors, relevant coursework, etc."]
    }
  ],
  "projects": [
    {
      "name": "Project Name",
      "description": "What it does",
      "technologies": ["tech1", "tech2"]
    }
  ],
  "certifications": ["Cert name and issuer"]
}
"""


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


def structure_resume(parsed: ParsedResume, api_key: str, model: str = "claude-sonnet-4-20250514") -> StructuredResume:
    """Use Claude to extract structured sections from raw resume text."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=STRUCTURE_PROMPT,
        messages=[{"role": "user", "content": parsed.raw_text}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]

    data = json.loads(text)

    return StructuredResume(
        name=data.get("name", ""),
        contact=data.get("contact", ""),
        summary=data.get("summary", ""),
        skills=data.get("skills", []),
        experience=[
            ExperienceEntry(
                company=e.get("company", ""),
                title=e.get("title", ""),
                dates=e.get("dates", ""),
                bullets=e.get("bullets", []),
            )
            for e in data.get("experience", [])
        ],
        education=[
            EducationEntry(
                institution=ed.get("institution", ""),
                degree=ed.get("degree", ""),
                dates=ed.get("dates", ""),
                details=ed.get("details", []),
            )
            for ed in data.get("education", [])
        ],
        projects=[
            ProjectEntry(
                name=p.get("name", ""),
                description=p.get("description", ""),
                technologies=p.get("technologies", []),
            )
            for p in data.get("projects", [])
        ],
        certifications=data.get("certifications", []),
        raw_text=parsed.raw_text,
        source_path=parsed.source_path,
    )


def _parse_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _parse_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n\n".join(para.text for para in doc.paragraphs if para.text.strip())
