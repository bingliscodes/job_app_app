from __future__ import annotations

from abc import ABC, abstractmethod

from jobapp.models import Job


class JobSource(ABC):
    """Abstract base class for job board API clients."""

    name: str

    @abstractmethod
    async def search(self, query: str, location: str, max_results: int = 25, days_posted: int = 7) -> list[Job]:
        ...


def parse_query_phrases(query: str) -> list[str]:
    """Split a 'foo OR bar baz' query string into normalized role phrases.

    Returns lowercased phrases with whitespace trimmed. Used by sources that
    need to do their own client-side keyword filtering.
    """
    return [p.strip().lower() for p in query.split(" OR ") if p.strip()]


def title_matches_phrases(title: str, phrases: list[str]) -> bool:
    """Return True if any role phrase's tokens all appear in the title.

    For phrase "backend engineer", title must contain both "backend" and
    "engineer" (in any order, not necessarily contiguous). Avoids the
    short-substring false positives of the previous per-word OR match
    (e.g. 'OR' matching 'Property' / 'Support').
    """
    if not phrases:
        return True
    title_lower = title.lower()
    return any(
        all(token in title_lower for token in phrase.split())
        for phrase in phrases
    )
