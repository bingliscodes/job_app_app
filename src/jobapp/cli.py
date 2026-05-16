from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from jobapp.config import load_config

console = Console()

# Shared state: jobs found in the current session, keyed by short ID
_job_cache_path = Path(".jobapp_cache.json")


def _load_job_cache() -> dict:
    if _job_cache_path.exists():
        return json.loads(_job_cache_path.read_text())
    return {}


def _save_job_cache(jobs: list[dict]) -> None:
    cache = {j["id"]: j for j in jobs}
    _job_cache_path.write_text(json.dumps(cache, indent=2))


@click.group()
@click.option("--config", "config_path", default="config.toml", help="Path to config file")
@click.pass_context
def cli(ctx: click.Context, config_path: str) -> None:
    """JobApp — AI-powered job application automation."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)


@cli.command()
@click.option("--query", "-q", help="Override search query (default: uses config roles)")
@click.option("--location", "-l", help="Override location (default: uses config locations)")
@click.option("--limit", "-n", default=25, help="Max results per source")
@click.option("--min-years", type=int, default=None, help="Minimum years of experience (overrides config)")
@click.option("--max-years", type=int, default=None, help="Maximum years of experience (overrides config)")
@click.option("--no-skills", is_flag=True, help="Skip resume-skills broadening on Adzuna")
@click.pass_context
def search(
    ctx: click.Context,
    query: str | None,
    location: str | None,
    limit: int,
    min_years: int | None,
    max_years: int | None,
    no_skills: bool,
) -> None:
    """Search job boards for recent positions."""
    from jobapp.sourcing import search_all_sources

    cfg = ctx.obj["config"]
    jobs = asyncio.run(search_all_sources(
        cfg,
        query=query,
        location=location,
        limit=limit,
        min_years=min_years,
        max_years=max_years,
        use_skills=not no_skills,
    ))

    if not jobs:
        console.print("[yellow]No jobs found. Try broadening your search.[/yellow]")
        return

    # Cache results for tailor/apply commands
    _save_job_cache([_job_to_dict(j) for j in jobs])

    table = Table(title=f"Found {len(jobs)} jobs")
    table.add_column("ID", style="cyan", width=12)
    table.add_column("Title", style="bold")
    table.add_column("Company")
    table.add_column("Location")
    table.add_column("Posted")
    table.add_column("Source", style="dim")

    for job in jobs:
        table.add_row(job.id, job.title, job.company, job.location, job.posted_date, job.source)

    console.print(table)
    console.print(f"\n[dim]Use [bold]jobapp tailor <ID>[/bold] to tailor your resume for a job.[/dim]")


@cli.command()
@click.argument("job_id")
@click.pass_context
def tailor(ctx: click.Context, job_id: str) -> None:
    """Tailor resume and cover letter for a specific job."""
    from jobapp.models import Job
    from jobapp.resume.parser import parse_resume
    from jobapp.tailor.engine import TailoringEngine
    from jobapp.output.pdf import render_resume_pdf, render_cover_letter_pdf

    cfg = ctx.obj["config"]
    cache = _load_job_cache()

    # Find the job by ID prefix
    matches = {k: v for k, v in cache.items() if k.startswith(job_id)}
    if not matches:
        console.print(f"[red]Job ID '{job_id}' not found. Run 'jobapp search' first.[/red]")
        return
    if len(matches) > 1:
        console.print(f"[red]Ambiguous ID '{job_id}'. Be more specific.[/red]")
        return

    job_data = next(iter(matches.values()))
    job = Job(**{k: v for k, v in job_data.items() if k != "id"})

    # Parse and structure resume
    resume_path = cfg.user.resume_path
    if not cfg.api_keys.anthropic:
        console.print("[red]Error: Anthropic API key not set. Set ANTHROPIC_API_KEY or add to config.toml.[/red]")
        return

    console.print(f"Parsing resume from [cyan]{resume_path}[/cyan]...")
    parsed = parse_resume(resume_path)

    console.print("Extracting structured resume sections...")
    from jobapp.resume.parser import structure_resume
    structured = structure_resume(parsed, api_key=cfg.api_keys.anthropic, model=cfg.ai.model)
    console.print(f"  Found [cyan]{len(structured.skills)}[/cyan] skills, "
                  f"[cyan]{len(structured.experience)}[/cyan] experience entries")

    console.print(f"Tailoring for [bold]{job.title}[/bold] at [bold]{job.company}[/bold] (with verification)...")
    engine = TailoringEngine(api_key=cfg.api_keys.anthropic, model=cfg.ai.model)
    contact_links = _build_contact_links(cfg)
    material = engine.tailor(structured, job, contact_links=contact_links)

    # Show matches and suggestions
    if material.key_matches:
        console.print("\n[green]Key matches:[/green]")
        for m in material.key_matches:
            console.print(f"  - {m}")
    if material.suggestions:
        console.print("\n[yellow]Suggestions:[/yellow]")
        for s in material.suggestions:
            console.print(f"  - {s}")

    # Generate PDFs
    output_dir = Path(cfg.output.directory) / job.slug
    output_dir.mkdir(parents=True, exist_ok=True)

    resume_pdf = render_resume_pdf(material, str(output_dir))
    cover_pdf = render_cover_letter_pdf(material, str(output_dir))

    # Save job details
    (output_dir / "job_details.json").write_text(json.dumps(job_data, indent=2))

    console.print(f"\n[green]Output saved to {output_dir}/[/green]")
    console.print(f"  Resume:       [cyan]{resume_pdf}[/cyan]")
    console.print(f"  Cover letter: [cyan]{cover_pdf}[/cyan]")


@cli.command()
@click.argument("job_id")
@click.pass_context
def apply(ctx: click.Context, job_id: str) -> None:
    """Open browser and pre-fill application form for a job."""
    from jobapp.models import Job
    from jobapp.apply.browser import ApplicationBot

    cfg = ctx.obj["config"]
    cache = _load_job_cache()

    matches = {k: v for k, v in cache.items() if k.startswith(job_id)}
    if not matches:
        console.print(f"[red]Job ID '{job_id}' not found. Run 'jobapp search' first.[/red]")
        return
    if len(matches) > 1:
        console.print(f"[red]Ambiguous ID '{job_id}'. Be more specific.[/red]")
        return

    job_data = next(iter(matches.values()))
    job = Job(**{k: v for k, v in job_data.items() if k != "id"})

    # Check for generated materials
    output_dir = Path(cfg.output.directory) / job.slug
    resume_pdf = output_dir / "resume.pdf"
    if not resume_pdf.exists():
        console.print("[yellow]No tailored resume found. Run 'jobapp tailor' first.[/yellow]")
        return

    console.print(f"Opening application for [bold]{job.title}[/bold] at [bold]{job.company}[/bold]...")
    bot = ApplicationBot(cfg)
    asyncio.run(bot.fill_application(job, str(resume_pdf)))


@cli.command()
@click.option("--min-years", type=int, default=None, help="Minimum years of experience (overrides config)")
@click.option("--max-years", type=int, default=None, help="Maximum years of experience (overrides config)")
@click.option("--no-skills", is_flag=True, help="Skip resume-skills broadening on Adzuna")
@click.option("--no-validate", is_flag=True, help="Skip the live-listing check before tailoring")
@click.pass_context
def pipeline(
    ctx: click.Context,
    min_years: int | None,
    max_years: int | None,
    no_skills: bool,
    no_validate: bool,
) -> None:
    """Interactive pipeline: search → select → tailor → apply."""
    from jobapp.models import Job
    from jobapp.resume.parser import parse_resume
    from jobapp.sourcing import search_all_sources
    from jobapp.tailor.engine import TailoringEngine
    from jobapp.output.pdf import render_resume_pdf, render_cover_letter_pdf
    from jobapp.apply.browser import ApplicationBot

    cfg = ctx.obj["config"]

    # Step 1: Search
    console.print("[bold]Step 1: Searching for jobs...[/bold]")
    jobs = asyncio.run(search_all_sources(
        cfg, min_years=min_years, max_years=max_years, use_skills=not no_skills,
    ))

    if not jobs:
        console.print("[yellow]No jobs found.[/yellow]")
        return

    # Display results
    for i, job in enumerate(jobs, 1):
        console.print(f"  [cyan]{i:3}[/cyan]. {job.title} @ {job.company} ({job.location}) [{job.source}]")

    # Step 2: Select
    console.print(f"\n[bold]Step 2: Select jobs to apply to[/bold]")
    selection = click.prompt("Enter job numbers (comma-separated, or 'all')", default="1")

    if selection.strip().lower() == "all":
        selected = jobs
    else:
        indices = [int(x.strip()) - 1 for x in selection.split(",") if x.strip().isdigit()]
        selected = [jobs[i] for i in indices if 0 <= i < len(jobs)]

    if not selected:
        console.print("[red]No valid jobs selected.[/red]")
        return

    # Step 2.5: Validate that each selected job is still active. Aggregator
    # feeds (especially The Muse) don't prune removed listings; checking now
    # avoids spending Claude tokens tailoring jobs that 404 at apply time.
    if not no_validate:
        from jobapp.apply.browser import validate_jobs
        console.print(f"\n[bold]Checking {len(selected)} listing(s) are still active...[/bold]")
        active, dead = asyncio.run(validate_jobs(selected))
        for j in dead:
            console.print(f"  [red]✗ Removed/expired:[/red] {j.title} @ {j.company}")
        if not active:
            console.print("[yellow]All selected listings appear to be dead. Re-run `jobapp search` and pick others.[/yellow]")
            return
        if dead:
            console.print(f"  [green]{len(active)} of {len(selected)} active — proceeding with those.[/green]")
        selected = active

    # Step 3: Parse and structure resume
    if not cfg.api_keys.anthropic:
        console.print("[red]Error: Anthropic API key not set.[/red]")
        return

    console.print(f"\n[bold]Step 3: Parsing and structuring resume...[/bold]")
    parsed = parse_resume(cfg.user.resume_path)

    from jobapp.resume.parser import structure_resume
    structured = structure_resume(parsed, api_key=cfg.api_keys.anthropic, model=cfg.ai.model)
    console.print(f"  Found [cyan]{len(structured.skills)}[/cyan] skills, "
                  f"[cyan]{len(structured.experience)}[/cyan] experience entries")

    # Step 4: Tailor (with verification)
    engine = TailoringEngine(api_key=cfg.api_keys.anthropic, model=cfg.ai.model)
    contact_links = _build_contact_links(cfg)

    for job in selected:
        console.print(f"\n[bold]Tailoring for {job.title} @ {job.company} (with verification)...[/bold]")
        material = engine.tailor(structured, job, contact_links=contact_links)

        output_dir = Path(cfg.output.directory) / job.slug
        output_dir.mkdir(parents=True, exist_ok=True)

        render_resume_pdf(material, str(output_dir))
        render_cover_letter_pdf(material, str(output_dir))
        console.print(f"  [green]Saved to {output_dir}/[/green]")

        # Step 5: Optionally apply
        if click.confirm(f"  Open browser to apply?", default=False):
            bot = ApplicationBot(cfg)
            asyncio.run(bot.fill_application(job, str(output_dir / "resume.pdf")))

    console.print("\n[green bold]Done![/green bold]")


def _build_contact_links(cfg) -> dict[str, str]:
    """Collect non-empty contact URLs from config to surface as hyperlinks in the resume."""
    links: dict[str, str] = {}
    if cfg.user.github_url:
        links["GitHub"] = cfg.user.github_url
    if cfg.user.linkedin_url:
        links["LinkedIn"] = cfg.user.linkedin_url
    return links


def _job_to_dict(job) -> dict:
    return {
        "id": job.id,
        "source": job.source,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "url": job.url,
        "posted_date": job.posted_date,
        "salary_range": job.salary_range,
        "raw": job.raw,
    }
