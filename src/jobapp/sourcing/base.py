from __future__ import annotations

from abc import ABC, abstractmethod

from jobapp.models import Job


class JobSource(ABC):
    """Abstract base class for job board API clients."""

    name: str

    @abstractmethod
    async def search(self, query: str, location: str, max_results: int = 25, days_posted: int = 7) -> list[Job]:
        ...
