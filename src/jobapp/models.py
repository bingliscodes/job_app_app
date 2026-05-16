from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class Job:
    source: str
    title: str
    company: str
    location: str
    description: str
    url: str
    posted_date: str
    salary_range: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        """Short deterministic ID derived from the job URL."""
        return hashlib.sha256(self.url.encode()).hexdigest()[:12]

    @property
    def slug(self) -> str:
        """Filesystem-safe slug for output directories."""
        company = self.company.lower().replace(" ", "-")[:30]
        title = self.title.lower().replace(" ", "-")[:30]
        return f"{company}_{title}_{self.posted_date}"


@dataclass
class ParsedResume:
    raw_text: str
    source_format: str
    source_path: str


@dataclass
class TailoredMaterial:
    job: Job
    tailored_resume_md: str
    cover_letter_md: str
    key_matches: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
