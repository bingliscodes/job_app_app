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
  models.py           — Dataclasses: Job, ParsedResume, StructuredResume, TailoredMaterial
  sourcing/           — Job board API clients (base.py, arbeitnow.py, themuse.py, adzuna.py),
                        experience.py (years-of-experience filter),
                        location_filter.py (US/remote post-filter), and
                        account_required.py (login-wall company filter)
  resume/parser.py    — PDF/DOCX/TXT text extraction + Claude-powered structured extraction
  resume/templates/   — HTML/CSS templates for resume and cover letter PDFs
  tailor/engine.py    — Claude API integration, constrained tailoring + verification pass
  output/pdf.py       — WeasyPrint HTML→PDF rendering
  apply/browser.py    — Playwright form detection and pre-filling
```

## Key Commands
```bash
source .venv/bin/activate
jobapp search              # Search job boards
jobapp search --min-years 0 --max-years 4   # Filter by years of experience
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

## Anti-Hallucination Safeguards
The tailoring pipeline has three layers to prevent fabricated content:

1. **Structured extraction** (`resume/parser.py:structure_resume`) — Claude parses raw resume
   text into typed JSON: `StructuredResume` with `ExperienceEntry`, `EducationEntry`,
   `ProjectEntry`, skills list, etc. This becomes the single source of truth.
2. **Skills whitelist + constrained prompt** (`tailor/engine.py:_tailor_pass`) — The tailoring
   prompt receives structured JSON and an explicit skills whitelist (extracted from the resume).
   Hard constraints: only whitelisted skills, only existing experience bullets (rephrased, not
   invented), no fabricated metrics/numbers.
3. **Verification pass** (`tailor/engine.py:_verify_pass`) — A second Claude call compares the
   tailored output against the original structured resume. Checks for fabricated skills,
   experience, metrics, credentials. If violations are found, the engine re-tailors with
   explicit feedback about what to remove.

Data flow: `raw text → parse_resume() → structure_resume() → tailor() → verify → output`

The tailoring uses 3-4 Claude API calls per job: 1 for structuring, 1 for tailoring, 1 for
verification, and optionally 1 more for re-tailoring if violations are found.

## Experience-Level Filtering
Jobs are filtered by years of experience after sourcing. Configured via `min_years` /
`max_years` in `[preferences]`, or overridden per-call with `--min-years` / `--max-years`
on `search` and `pipeline`. Two heuristic signals (`sourcing/experience.py`):

1. **Title keywords** — when `max_years < 5`, jobs with `Senior`, `Sr.`, `Staff`, `Principal`,
   `Lead`, `Head of`, `VP`, `Director`, `Chief`, `Manager`, `Architect`, `Supervisor`, or a
   Roman-numeral level suffix (`II`, `III`, `IV`, `V`) in the title are dropped.
2. **Description regex** — `(\d+)\+? years?` matches within ±60 chars of an experience
   context word (`experience`, `professional`, `industry`, `hands-on`, etc.) take the
   minimum N; if N > `max_years` the job is dropped.

Lenient by design: jobs with no detectable experience signal are kept. The Muse's native
`level=` filter is also passed (`Entry Level`, `Mid Level`, etc.) via `themuse_levels_for_range()`.

## Skills-Aware Search (Adzuna)
Adzuna issues one request per (role_phrase × where) using `what_phrase` (exact match),
plus one request per `where` using `what_or = top resume skills` to broaden discovery.
The role-phrase title matcher is applied to results so skills-broadened jobs don't leak
non-engineer roles. Resume skills come from a local cache (`.jobapp_resume_cache.json`)
keyed by file mtime — the first search builds it via one Claude call, subsequent
searches reuse it. Use `--no-skills` on `search` / `pipeline` to skip resume parsing.
Adzuna per-request errors (intermittent 503s) are swallowed so one bad request doesn't
sink the batch.

## Login-Walled Company Filter
`sourcing/account_required.py:DEFAULT_ACCOUNT_REQUIRED` is a curated set of company-name
patterns whose career sites consistently require account creation (Apple, Microsoft,
Google, big banks, Workday-using Fortune 500, etc.). After all other filters, jobs whose
`company` matches a pattern are dropped — these dead-end on a login wall during `apply`.
Matching: word-boundary substring, case-insensitive. Extend via
`[preferences].extra_account_required_companies` in config.toml as you discover more.
No URL resolution is attempted (Adzuna rate-limits the `/land/ad/` redirect URL too
aggressively for that to be practical).

## Location & Country Filtering
- `[preferences].country` (ISO 3166-1 alpha-2) routes Adzuna to the matching country endpoint (`/us`, `/gb`, `/au`, etc.).
- `[preferences].locations` is a list; sources OR the values. The Muse accepts repeated `location=` query params. Adzuna's `where` is single-valued, so AdzunaSource issues one request per non-remote location plus a nationwide request when "Remote" is among the locations.
- When `country == "us"`, a post-source filter (`sourcing/location_filter.py`) drops jobs whose only specific locations are foreign (e.g. "Flexible / Remote, Bangalore, India"). Jobs with any US-state tag, "United States", "USA", or remote-with-no-foreign-country pass.
- Arbeitnow is disabled by default in `sourcing/__init__.py` (EU-focused). Re-enable by adding `ArbeitnowSource()` to the `sources` list.

## Browser Automation (apply)
- Launches Chromium non-headless with `--start-maximized` and `no_viewport=True`. On macOS, calls `osascript` to activate "Google Chrome for Testing" so the window comes to the foreground.
- If the apply URL is on an aggregator (`adzuna.com`, `themuse.com`), `_click_through_if_aggregator()` finds and clicks the Apply button, then handles Adzuna's email-capture interstitial by clicking "No thanks, take me to the job". Click may open a new tab (target=_blank) or navigate the same page — both paths are raced.
- After landing on the employer page, fills name/email/phone via CSS selector heuristics (`name`, `placeholder`, `id`, `aria-label`, `type=email|tel`) and uploads the resume PDF if a file input is present.
- Never auto-submits. Waits on `sys.stdin.readline()` so the browser stays open until the user presses Enter in the terminal.

## Development Notes
- Job search results are cached to `.jobapp_cache.json` (gitignored) so tailor/apply can reference jobs by ID
- The Arbeitnow API returns `created_at` as a Unix timestamp (int), not ISO string
- The Muse API has no keyword search param — filtering is done client-side on job title
- The Muse API accepts repeated `level=` and `location=` query params for OR filtering
- Adzuna requires app_id + app_key; source is skipped silently if keys aren't configured
- Sources receive `locations: list[str]`; each decides how to use it
- Claude's JSON response sometimes comes wrapped in ```json fences — the tailor engine strips these
- Browser automation detects common form fields by CSS selectors (name, email, phone, file upload)
