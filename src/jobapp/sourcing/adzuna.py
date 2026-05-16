from __future__ import annotations

import httpx

from jobapp.models import Job
from jobapp.sourcing.base import JobSource, parse_query_phrases, title_matches_phrases

# Cap on skills used in the `what_or` broadening query. Too few = narrow;
# too many = noisy / can exceed query length limits.
_MAX_SKILLS_IN_QUERY = 10


class AdzunaSource(JobSource):
    """Adzuna job search API — requires app_id and app_key."""

    name = "adzuna"
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(
        self,
        app_id: str,
        app_key: str,
        country: str = "us",
        skills: list[str] | None = None,
    ):
        self.app_id = app_id
        self.app_key = app_key
        self.country = country
        self.skills = skills or []

    async def search(self, query: str, locations: list[str], max_results: int = 25, days_posted: int = 7) -> list[Job]:
        if not self.app_id or not self.app_key:
            return []

        role_phrases = parse_query_phrases(query)
        url = f"{self.BASE_URL}/{self.country}/search/1"
        results_per_page = min(max_results, 50)

        # Build the list of `where` values to query. "Remote" doesn't map to a
        # geographic `where` — we use None (nationwide) for it. Other locations
        # pass through as the city/state string.
        where_values: list[str | None] = []
        wants_remote = any(loc.strip().lower() == "remote" for loc in locations)
        for loc in locations:
            if loc and loc.strip().lower() != "remote":
                where_values.append(loc)
        if wants_remote:
            where_values.append(None)
        if not where_values:
            where_values = [None]

        base_params: dict[str, object] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": results_per_page,
            "max_days_old": days_posted,
            "sort_by": "date",
        }

        # Each request varies the what_* params (and optionally `where`).
        # One request per (role_phrase × where) using what_phrase for exact
        # title/description match. Plus one per where with what_or=skills to
        # broaden discovery using the resume's skills whitelist.
        request_specs: list[dict] = []
        for phrase in role_phrases:
            for where in where_values:
                spec = {"what_phrase": phrase}
                if where:
                    spec["where"] = where
                request_specs.append(spec)
        if self.skills:
            skills_query = " ".join(self.skills[:_MAX_SKILLS_IN_QUERY])
            for where in where_values:
                spec = {"what_or": skills_query}
                if where:
                    spec["where"] = where
                request_specs.append(spec)

        items: list[dict] = []
        seen_ids: set[str] = set()
        errors = 0
        async with httpx.AsyncClient(timeout=30) as client:
            for spec in request_specs:
                params = {**base_params, **spec}
                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except (httpx.HTTPStatusError, httpx.RequestError):
                    # Adzuna intermittently 503s on some queries; skip and continue
                    # so one bad request doesn't lose the whole batch.
                    errors += 1
                    continue
                for item in data.get("results", []):
                    item_id = str(item.get("id", "")) or item.get("redirect_url", "")
                    if item_id and item_id in seen_ids:
                        continue
                    if item_id:
                        seen_ids.add(item_id)
                    items.append(item)
        if errors and not items:
            # Surface the issue if every request failed.
            raise RuntimeError(f"all {errors} Adzuna requests failed")

        jobs: list[Job] = []
        for item in items:
            title = item.get("title", "")
            # Apply role-phrase title match so skills-broadened results don't
            # leak unrelated roles that happen to mention our skills.
            if not title_matches_phrases(title, role_phrases):
                continue

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

            if len(jobs) >= max_results:
                break

        return jobs
