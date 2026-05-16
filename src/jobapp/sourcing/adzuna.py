from __future__ import annotations

import httpx

from jobapp.models import Job
from jobapp.sourcing.base import JobSource


class AdzunaSource(JobSource):
    """Adzuna job search API — requires app_id and app_key."""

    name = "adzuna"
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self, app_id: str, app_key: str, country: str = "us"):
        self.app_id = app_id
        self.app_key = app_key
        self.country = country

    async def search(self, query: str, locations: list[str], max_results: int = 25, days_posted: int = 7) -> list[Job]:
        if not self.app_id or not self.app_key:
            return []

        results_per_page = min(max_results, 50)
        url = f"{self.BASE_URL}/{self.country}/search/1"

        # Adzuna's `where` is a single string. To support multiple locations
        # (e.g. ["Remote", "Palo Alto, CA"]) we make one request per non-empty
        # where value, plus one nationwide request if "Remote" is among them
        # (so we don't miss remote-anywhere postings tagged with other cities).
        where_values: list[str | None] = []
        wants_remote = any(loc.strip().lower() == "remote" for loc in locations)
        for loc in locations:
            if loc and loc.strip().lower() != "remote":
                where_values.append(loc)
        if wants_remote:
            # None = no `where` filter; rely on description/title for remote signal,
            # or just include all country-wide jobs.
            where_values.append(None)
        if not where_values:
            where_values = [None]

        base_params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": results_per_page,
            "max_days_old": days_posted,
            "sort_by": "date",
        }
        if query:
            base_params["what"] = query

        items: list[dict] = []
        seen_ids: set[str] = set()
        async with httpx.AsyncClient(timeout=30) as client:
            for where in where_values:
                params = dict(base_params)
                if where:
                    params["where"] = where
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("results", []):
                    item_id = str(item.get("id", "")) or item.get("redirect_url", "")
                    if item_id and item_id in seen_ids:
                        continue
                    if item_id:
                        seen_ids.add(item_id)
                    items.append(item)

        jobs = []
        for item in items:
            title = item.get("title", "")
            company_data = item.get("company", {})
            company = company_data.get("display_name", "") if isinstance(company_data, dict) else str(company_data)

            location_data = item.get("location", {})
            if isinstance(location_data, dict):
                areas = location_data.get("area", [])
                loc = ", ".join(areas) if areas else location_data.get("display_name", "")
            else:
                loc = str(location_data)

            created = item.get("created", "")
            posted_date = created[:10] if created else ""

            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            salary_range = None
            if salary_min or salary_max:
                salary_range = f"${salary_min or '?'} - ${salary_max or '?'}"

            jobs.append(Job(
                source=self.name,
                title=title,
                company=company,
                location=loc,
                description=item.get("description", ""),
                url=item.get("redirect_url", ""),
                posted_date=posted_date,
                salary_range=salary_range,
                raw=item,
            ))

        return jobs
