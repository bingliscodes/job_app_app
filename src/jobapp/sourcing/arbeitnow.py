from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from jobapp.models import Job
from jobapp.sourcing.base import JobSource, parse_query_phrases, title_matches_phrases


class ArbeitnowSource(JobSource):
    """Arbeitnow job board API — free, no API key required."""

    name = "arbeitnow"
    BASE_URL = "https://www.arbeitnow.com/api/job-board-api"

    async def search(self, query: str, location: str, max_results: int = 25, days_posted: int = 7) -> list[Job]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.BASE_URL)
            resp.raise_for_status()
            data = resp.json()

        raw_jobs = data if isinstance(data, list) else data.get("data", [])

        phrases = parse_query_phrases(query)
        location_lower = location.lower()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_posted)

        results = []
        for item in raw_jobs:
            title = item.get("title", "")
            desc = item.get("description", "")
            loc = item.get("location", "")
            company = item.get("company_name", "") or item.get("company", "")

            # Client-side keyword filtering: title must contain all tokens
            # of at least one role phrase. Description is not matched — it
            # leaks unrelated roles (e.g. marketing jobs that mention engineers).
            if not title_matches_phrases(title, phrases):
                continue

            # Client-side location filtering (skip if "remote" requested and job is remote)
            if location_lower and location_lower != "remote":
                if location_lower not in loc.lower():
                    continue
            elif location_lower == "remote":
                if not item.get("remote", False) and "remote" not in loc.lower():
                    continue

            # Parse date — can be ISO string or Unix timestamp
            created = item.get("created_at", "")
            posted_date = ""
            if created:
                try:
                    if isinstance(created, (int, float)):
                        dt = datetime.fromtimestamp(created, tz=timezone.utc)
                    else:
                        dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    if dt < cutoff:
                        continue
                    posted_date = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError, OSError):
                    posted_date = str(created)[:10]

            url = item.get("url", "") or item.get("slug", "")
            if url and not url.startswith("http"):
                url = f"https://www.arbeitnow.com/view/{url}"

            results.append(Job(
                source=self.name,
                title=title,
                company=company,
                location=loc,
                description=desc,
                url=url,
                posted_date=posted_date,
                raw=item,
            ))

            if len(results) >= max_results:
                break

        return results
