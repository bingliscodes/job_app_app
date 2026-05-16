# CLAUDE.md

## Project Overview
**jobapp** — Python CLI tool that searches job board APIs for recent positions, uses Claude AI to tailor resumes and cover letters, generates PDFs, and optionally pre-fills application forms via browser automation.

## Tech Stack
- Python 3.11+, installed as editable package (`pip install -e .`)
- CLI: Click + Rich
- Job sourcing: httpx (async) hitting Arbeitnow, The Muse, Adzuna APIs
- AI: Anthropic SDK (Claude) for resume tailoring
- PDF: WeasyPrint + Jinja2 HTML templates + markdown
- Resume parsing: pypdf (PDF), python-docx (DOCX), plain text
- Browser automation: Playwright (Chromium, non-headless, never auto-submits)

## Project Structure
```
src/jobapp/
  cli.py              — Click CLI entry point, all commands
  config.py           — TOML config loading + env var override
  models.py           — Dataclasses: Job, ParsedResume, TailoredMaterial
  sourcing/           — Job board API clients (base.py, arbeitnow.py, themuse.py, adzuna.py)
  resume/parser.py    — PDF/DOCX/TXT text extraction
  resume/templates/   — HTML/CSS templates for resume and cover letter PDFs
  tailor/engine.py    — Claude API integration, prompt engineering, JSON response parsing
  output/pdf.py       — WeasyPrint HTML→PDF rendering
  apply/browser.py    — Playwright form detection and pre-filling
```

## Key Commands
```bash
source .venv/bin/activate
jobapp search              # Search job boards
jobapp tailor <ID>         # Tailor resume + cover letter for a job
jobapp apply <ID>          # Open browser, pre-fill application
jobapp pipeline            # Interactive: search → select → tailor → apply
```

## Configuration
- `config.toml` (gitignored) — user details, API keys, preferences
- `config.example.toml` — template to copy from
- Env vars override config: ANTHROPIC_API_KEY, ADZUNA_APP_ID, ADZUNA_APP_KEY

## System Dependencies
- `brew install pango` (required for WeasyPrint PDF generation)
- `playwright install chromium` (required for browser automation)

## Development Notes
- Job search results are cached to `.jobapp_cache.json` (gitignored) so tailor/apply can reference jobs by ID
- The Arbeitnow API returns `created_at` as a Unix timestamp (int), not ISO string
- The Muse API has no keyword search param — filtering is done client-side on job title
- Adzuna requires app_id + app_key; source is skipped silently if keys aren't configured
- Claude's JSON response sometimes comes wrapped in ```json fences — the tailor engine strips these
- Browser automation detects common form fields by CSS selectors (name, email, phone, file upload)
