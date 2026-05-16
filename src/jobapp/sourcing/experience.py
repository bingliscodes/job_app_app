from __future__ import annotations

import re

from jobapp.models import Job

# Title keywords that strongly imply more than 4 years of experience.
SENIOR_TITLE_PATTERNS = [
    re.compile(r"\bsenior\b", re.IGNORECASE),
    re.compile(r"\bsr\.?\b", re.IGNORECASE),
    re.compile(r"\bstaff\b", re.IGNORECASE),
    re.compile(r"\bprincipal\b", re.IGNORECASE),
    re.compile(r"\blead\b", re.IGNORECASE),
    re.compile(r"\bhead\s+of\b", re.IGNORECASE),
    re.compile(r"\bvp\b", re.IGNORECASE),
    re.compile(r"\bvice\s+president\b", re.IGNORECASE),
    re.compile(r"\bdirector\b", re.IGNORECASE),
    re.compile(r"\bchief\b", re.IGNORECASE),
    re.compile(r"\bmanager\b", re.IGNORECASE),
    re.compile(r"\barchitect\b", re.IGNORECASE),
    re.compile(r"\bsupervisor\b", re.IGNORECASE),
    # Roman numeral level suffixes (II, III, IV, V) at the end of a title or
    # as a standalone word, e.g. "Engineer III" or "Engineer II - Backend".
    re.compile(r"\b(II|III|IV|V)\b(?!\w)"),
]

# Matches "5 years", "5+ years", "5-7 years", "5 to 7 years"; captures the lower bound.
_YEARS_PATTERN = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:(?:to|[-–])\s*\d{1,2}\s*)?years?",
    re.IGNORECASE,
)

# Context words that indicate the years figure refers to required work experience.
_EXPERIENCE_CONTEXT = re.compile(
    r"\b(experience|exp\.?|professional|industry|working|background|hands[- ]on)\b",
    re.IGNORECASE,
)


def extract_min_required_years(text: str) -> int | None:
    """Find the smallest "X years experience" figure mentioned in text.

    Returns None if no years-of-experience reference is detected.
    """
    if not text:
        return None
    found: list[int] = []
    for match in _YEARS_PATTERN.finditer(text):
        start, end = match.span()
        window_start = max(0, start - 60)
        window_end = min(len(text), end + 60)
        if _EXPERIENCE_CONTEXT.search(text[window_start:window_end]):
            try:
                found.append(int(match.group(1)))
            except ValueError:
                continue
    return min(found) if found else None


def job_matches_experience(job: Job, min_years: int, max_years: int) -> bool:
    """Return True if a job plausibly fits the years-of-experience range.

    Lenient: if no signal is found in the title or description, the job is included.
    """
    title = job.title or ""

    # Reject senior-coded titles when the upper bound is below typical senior thresholds.
    if max_years < 5:
        for pattern in SENIOR_TITLE_PATTERNS:
            if pattern.search(title):
                return False

    min_required = extract_min_required_years(job.description or "")
    if min_required is not None and min_required > max_years:
        return False

    return True


def themuse_levels_for_range(min_years: int, max_years: int) -> list[str]:
    """Map a years range to The Muse `level` filter values."""
    levels: list[str] = []
    if min_years == 0 and max_years >= 0:
        levels.append("Entry Level")
    if max_years >= 2:
        levels.append("Mid Level")
    if max_years >= 5:
        levels.append("Senior Level")
    if max_years >= 8:
        levels.append("Management")
    return levels
