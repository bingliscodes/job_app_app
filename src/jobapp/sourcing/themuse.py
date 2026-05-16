from __future__ import annotations

import httpx

from jobapp.models import Job
from jobapp.sourcing.base import JobSource, parse_query_phrases, title_matches_phrases


class TheMuseSource(JobSource):
    """The Muse job API — free tier, 500 req/hr without key."""

    name = "themuse"
    BASE_URL = "https://www.themuse.com/api/public/jobs"

    def __init__(self, levels: list[str] | None = None):
        self.levels = levels or []

    async def search(self, query: str, location: str, max_results: int = 25, days_posted: int = 7) -> list[Job]:
        results: list[Job] = []
        page = 0
        phrases = parse_query_phrases(query)

        async with httpx.AsyncClient(timeout=30) as client:
            while len(results) < max_results:
                # httpx serializes list values as repeated query params, which is what
                # The Muse expects for level= filters.
                params: list[tuple[str, str]] = [("page", str(page))]
                if location:
                    params.append(("location", location))
                for level in self.levels:
                    params.append(("level", level))

                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

                page_results = data.get("results", [])
                if not page_results:
                    break

                for item in page_results:
                    title = item.get("name", "")

                    # Client-side keyword filtering: title must contain all tokens
                    # of at least one role phrase.
                    if not title_matches_phrases(title, phrases):
                        continue

                    company = item.get("company", {})
                    company_name = company.get("name", "") if isinstance(company, dict) else str(company)

                    locations = item.get("locations", [])
                    loc_str = ", ".join(
                        loc.get("name", "") if isinstance(loc, dict) else str(loc)
                        for loc in locations
                    ) if locations else ""

                    # The Muse provides a refs.landing_page or we construct from ID
                    refs = item.get("refs", {})
                    url = refs.get("landing_page", "") if isinstance(refs, dict) else ""
                    if not url:
                        job_id = item.get("id", "")
                        url = f"https://www.themuse.com/jobs/{job_id}" if job_id else ""

                    publication_date = item.get("publication_date", "")
                    posted_date = publication_date[:10] if publication_date else ""

                    # Build description from contents
                    contents = item.get("contents", "")

                    results.append(Job(
                        source=self.name,
                        title=title,
                        company=company_name,
                        location=loc_str,
                        description=contents,
                        url=url,
                        posted_date=posted_date,
                        raw=item,
                    ))

                    if len(results) >= max_results:
                        break

                page += 1
                if page >= data.get("page_count", 1):
                    break

        return results
