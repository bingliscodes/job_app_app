from __future__ import annotations

import httpx

from jobapp.models import Job
from jobapp.sourcing.base import JobSource


class AdzunaSource(JobSource):
    """Adzuna job search API — requires app_id and app_key."""

    name = "adzuna"
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self, app_id: str, app_key: str, country: str = "au"):
        self.app_id = app_id
        self.app_key = app_key
        self.country = country

    async def search(self, query: str, location: str, max_results: int = 25, days_posted: int = 7) -> list[Job]:
        if not self.app_id or not self.app_key:
            return []

        results_per_page = min(max_results, 50)
        url = f"{self.BASE_URL}/{self.country}/search/1"

        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": results_per_page,
            "max_days_old": days_posted,
            "sort_by": "date",
        }
        if query:
            params["what"] = query
        if location:
            params["where"] = location

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        jobs = []
        for item in data.get("results", []):
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
