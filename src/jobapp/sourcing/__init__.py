from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console

from jobapp.models import Job
from jobapp.sourcing.arbeitnow import ArbeitnowSource
from jobapp.sourcing.themuse import TheMuseSource
from jobapp.sourcing.adzuna import AdzunaSource
from jobapp.sourcing.experience import job_matches_experience, themuse_levels_for_range

if TYPE_CHECKING:
    from jobapp.config import Config

console = Console()


async def search_all_sources(
    cfg: Config,
    query: str | None = None,
    location: str | None = None,
    limit: int | None = None,
    min_years: int | None = None,
    max_years: int | None = None,
) -> list[Job]:
    """Search all configured job sources in parallel and return deduplicated results."""
    search_query = query or " OR ".join(cfg.preferences.roles)
    search_location = location or (cfg.preferences.locations[0] if cfg.preferences.locations else "")
    max_results = limit or cfg.preferences.max_results_per_source
    days = cfg.preferences.days_posted
    min_yr = cfg.preferences.min_years if min_years is None else min_years
    max_yr = cfg.preferences.max_years if max_years is None else max_years

    themuse_levels = themuse_levels_for_range(min_yr, max_yr)

    sources = [
        ArbeitnowSource(),
        TheMuseSource(levels=themuse_levels),
    ]

    if cfg.api_keys.adzuna_app_id and cfg.api_keys.adzuna_app_key:
        sources.append(AdzunaSource(cfg.api_keys.adzuna_app_id, cfg.api_keys.adzuna_app_key))

    async def _search_one(source):
        try:
            console.print(f"  Searching [cyan]{source.name}[/cyan]...")
            results = await source.search(search_query, search_location, max_results, days)
            console.print(f"  [green]{source.name}: {len(results)} jobs[/green]")
            return results
        except Exception as e:
            console.print(f"  [red]{source.name}: error — {e}[/red]")
            return []

    all_results = await asyncio.gather(*[_search_one(s) for s in sources])

    # Flatten and deduplicate by URL
    seen_urls: set[str] = set()
    jobs: list[Job] = []
    for batch in all_results:
        for job in batch:
            if job.url and job.url not in seen_urls:
                seen_urls.add(job.url)
                jobs.append(job)

    # Apply years-of-experience filter (lenient: keep jobs where no signal detected)
    before = len(jobs)
    jobs = [j for j in jobs if job_matches_experience(j, min_yr, max_yr)]
    if before != len(jobs):
        console.print(
            f"  [dim]Experience filter ({min_yr}-{max_yr} yrs): "
            f"{before} → {len(jobs)} jobs[/dim]"
        )

    # Sort by posted date descending (most recent first)
    jobs.sort(key=lambda j: j.posted_date, reverse=True)

    return jobs
