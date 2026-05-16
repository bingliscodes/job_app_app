from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console

from jobapp.models import Job
from jobapp.sourcing.themuse import TheMuseSource
from jobapp.sourcing.adzuna import AdzunaSource
from jobapp.sourcing.experience import job_matches_experience, themuse_levels_for_range
from jobapp.sourcing.location_filter import location_is_us_or_remote

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
    search_locations = [location] if location else list(cfg.preferences.locations)
    max_results = limit or cfg.preferences.max_results_per_source
    days = cfg.preferences.days_posted
    min_yr = cfg.preferences.min_years if min_years is None else min_years
    max_yr = cfg.preferences.max_years if max_years is None else max_years

    themuse_levels = themuse_levels_for_range(min_yr, max_yr)

    # Arbeitnow disabled — EU-focused, returns mostly German postings. Re-enable
    # by adding ArbeitnowSource() to this list.
    sources = [
        TheMuseSource(levels=themuse_levels),
    ]

    if cfg.api_keys.adzuna_app_id and cfg.api_keys.adzuna_app_key:
        sources.append(AdzunaSource(
            cfg.api_keys.adzuna_app_id,
            cfg.api_keys.adzuna_app_key,
            country=cfg.preferences.country,
        ))

    async def _search_one(source):
        try:
            console.print(f"  Searching [cyan]{source.name}[/cyan]...")
            results = await source.search(search_query, search_locations, max_results, days)
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

    # Apply US-or-remote location filter (when country=us). Drops jobs whose
    # only specific locations are foreign even if also tagged Remote.
    if cfg.preferences.country.lower() == "us":
        before = len(jobs)
        jobs = [j for j in jobs if location_is_us_or_remote(j.location)]
        if before != len(jobs):
            console.print(
                f"  [dim]Location filter (US/remote): "
                f"{before} → {len(jobs)} jobs[/dim]"
            )

    # Sort by posted date descending (most recent first)
    jobs.sort(key=lambda j: j.posted_date, reverse=True)

    return jobs
