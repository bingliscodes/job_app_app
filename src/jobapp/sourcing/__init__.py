from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console

from jobapp.models import Job
from jobapp.sourcing.themuse import TheMuseSource
from jobapp.sourcing.adzuna import AdzunaSource
from jobapp.sourcing.experience import job_matches_experience, themuse_levels_for_range
from jobapp.sourcing.location_filter import location_is_us_or_remote
from jobapp.sourcing.account_required import (
    DEFAULT_ACCOUNT_REQUIRED,
    company_requires_account,
)

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
    use_skills: bool = True,
) -> list[Job]:
    """Search all configured job sources in parallel and return deduplicated results."""
    search_query = query or " OR ".join(cfg.preferences.roles)
    search_locations = [location] if location else list(cfg.preferences.locations)
    max_results = limit or cfg.preferences.max_results_per_source
    days = cfg.preferences.days_posted
    min_yr = cfg.preferences.min_years if min_years is None else min_years
    max_yr = cfg.preferences.max_years if max_years is None else max_years

    themuse_levels = themuse_levels_for_range(min_yr, max_yr)

    # Load skills from the cached structured resume (or build the cache on
    # first run). Used by Adzuna's what_or to broaden discovery. Skipped if
    # use_skills=False or anthropic key isn't set.
    skills: list[str] = []
    if use_skills and cfg.api_keys.anthropic:
        try:
            from jobapp.resume.parser import get_cached_structured_resume
            console.print("  [dim]Loading resume skills...[/dim]")
            structured = get_cached_structured_resume(
                cfg.user.resume_path,
                api_key=cfg.api_keys.anthropic,
                model=cfg.ai.model,
            )
            skills = structured.skills
            console.print(f"  [dim]Skills available for search: {len(skills)}[/dim]")
        except Exception as e:
            console.print(f"  [yellow]Skills cache unavailable: {e}[/yellow]")

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
            skills=skills,
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

    # Drop jobs at companies known to require account creation to apply
    # (Apple, Microsoft, Google, Big Banks, etc.). Extend via
    # [preferences].extra_account_required_companies in config.toml.
    extra = {c.lower() for c in cfg.preferences.extra_account_required_companies}
    blocklist = frozenset(DEFAULT_ACCOUNT_REQUIRED | extra)
    before = len(jobs)
    jobs = [j for j in jobs if not company_requires_account(j.company, blocklist)]
    if before != len(jobs):
        console.print(
            f"  [dim]Login-wall filter (account required): "
            f"{before} → {len(jobs)} jobs[/dim]"
        )

    # Sort by posted date descending (most recent first)
    jobs.sort(key=lambda j: j.posted_date, reverse=True)

    return jobs
