# jobapp

AI-powered CLI tool that finds software engineering jobs, tailors your resume for each one using Claude, and helps you apply.

## What it does

1. **Searches** multiple job board APIs (Arbeitnow, The Muse, Adzuna) for recent positions
2. **Tailors** your resume and generates a cover letter for each job using Claude AI
3. **Generates** professional PDF documents from HTML/CSS templates
4. **Pre-fills** application forms in a browser (optional, never auto-submits)

## Quick Start

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/) for resume tailoring
- macOS: `brew install pango` (required for PDF generation)

### Installation

```bash
git clone <repo-url> && cd job_app_app
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For browser automation (optional):
```bash
playwright install chromium
```

### Configuration

```bash
cp config.example.toml config.toml
```

Edit `config.toml` with your details:

```toml
[user]
name = "Your Name"
email = "you@example.com"
resume_path = "./my_resume.pdf"
github_url = "https://github.com/yourusername"      # rendered as a hyperlink
linkedin_url = "https://www.linkedin.com/in/you/"   # rendered as a hyperlink

[preferences]
roles = ["backend engineer", "software engineer"]
locations = ["Remote", "San Francisco, CA"]   # OR-style; mix Remote + cities
country = "us"                                # routes Adzuna + post-filters non-US jobs
days_posted = 7
min_years = 0      # filter out roles that require more than max_years experience
max_years = 4

[api_keys]
anthropic = "sk-ant-..."        # or set ANTHROPIC_API_KEY env var
adzuna_app_id = ""              # optional, from https://developer.adzuna.com
adzuna_app_key = ""
```

API keys can also be set via environment variables:
- `ANTHROPIC_API_KEY`
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`

## Usage

### Search for jobs

```bash
jobapp search
jobapp search --query "python backend" --location "Remote" --limit 20
jobapp search --min-years 0 --max-years 4   # target entry/mid-level only
jobapp search --no-skills                   # skip resume-skills broadening on Adzuna
```

On the first run, `search` parses your resume and caches the extracted skills to
`.jobapp_resume_cache.json` (gitignored). Adzuna uses those skills as a `what_or`
broadening query alongside `what_phrase` per role. Subsequent runs reuse the cache
unless the resume file changes.

Displays a table of recent jobs with short IDs.

#### Years-of-experience filter

Set `min_years` and `max_years` in `[preferences]` to filter postings by seniority.
Jobs are excluded when:

- The title contains senior-coded keywords (`Senior`, `Staff`, `Principal`, `Lead`,
  `Manager`, `Director`, `Architect`, `Supervisor`, etc.) or a Roman-numeral level suffix
  (`II`, `III`, `IV`, `V`), and `max_years < 5`
- The description requires more years than `max_years` (e.g. "5+ years experience")

Postings with no detectable signal are kept (lenient). Override per-call with
`--min-years` / `--max-years` on `search` and `pipeline`.

#### Login-walled company filter

Many large employers (Apple, Microsoft, Google, big banks, Workday-using Fortune 500)
require account creation before you can apply. These dead-end the browser pre-fill, so
jobs from those companies are dropped after sourcing. See
`src/jobapp/sourcing/account_required.py` for the default list. Extend in `config.toml`:

```toml
[preferences]
extra_account_required_companies = ["acme corp", "stripe"]
```

### Tailor your resume

```bash
jobapp tailor <job-id>
```

Uses Claude to analyze the job posting and your resume, then generates:
- A tailored resume PDF (US Letter, **one page**) with relevant experience highlighted
- A cover letter addressing the specific role and company
- A list of key matches and suggestions

The resume includes hyperlinked GitHub/LinkedIn URLs from `[user]` config in the contact
line, rendered as clickable links in the PDF.

Output is saved to `./output/<company>_<title>_<date>/`. Each directory contains:
- `resume.pdf` — tailored, one-page
- `cover_letter.pdf` — addressed to "Hiring Manager", dated today
- `job_details.json` — raw job data for your records

### Apply with browser automation

```bash
jobapp apply <job-id>
```

Opens a Chromium browser, navigates to the job posting, and attempts to pre-fill:
- Name, email, phone fields
- Resume file upload

If the job URL is on an aggregator (Adzuna, The Muse), the bot clicks through the
"Apply for this job" button — including Adzuna's "Receive similar jobs by email"
interstitial via the "No thanks, take me to the job" link — to land on the
employer's real application form before filling. On macOS, the browser is brought
to the foreground via AppleScript so it doesn't launch hidden.

The browser stays open for you to review and submit manually. Press Enter in the
terminal when you're done. **It never auto-submits.**

### Full pipeline

```bash
jobapp pipeline
jobapp pipeline --no-validate   # skip the live-listing check
```

Interactive flow that chains all steps:
1. **Search** with all configured filters
2. **Select** the jobs you want to apply to
3. **Validate** each is still an active listing (headless Playwright; skips dead pages so you don't spend tailoring tokens on them) — disable with `--no-validate`
4. **Tailor** resume + cover letter for each
5. **Apply** by opening the browser, optionally per job

## Job Sources

| Source | API Key Required | Notes |
|--------|-----------------|-------|
| [Arbeitnow](https://www.arbeitnow.com/api/job-board-api) | No | **Disabled by default** — EU-focused, returns mostly German postings. Re-enable in `src/jobapp/sourcing/__init__.py`. |
| [The Muse](https://www.themuse.com/developers/api/v2) | No (optional) | Free tier: 500 req/hr. Native `location=` and `level=` filters; client-side title match. |
| [Adzuna](https://developer.adzuna.com/) | Yes | Country-aware (`/us`, `/gb`, etc.). One request per role phrase using `what_phrase`; broadens via resume skills in `what_or`. |

## Supported Resume Formats

- PDF (`.pdf`)
- Word Document (`.docx`)
- Plain text (`.txt`, `.md`)

## Project Structure

```
src/jobapp/
  cli.py              — CLI commands (search, tailor, apply, pipeline)
  config.py           — TOML config loading + env var override
  models.py           — Data models (Job, ParsedResume, StructuredResume, TailoredMaterial)
  sourcing/
    base.py             — JobSource ABC + role-phrase title matcher
    arbeitnow.py        — EU-focused (disabled by default)
    themuse.py          — The Muse client with level/location filters
    adzuna.py           — Adzuna client (per-role what_phrase + skills what_or)
    experience.py       — Years-of-experience filter
    location_filter.py  — US/remote post-filter
    account_required.py — Login-walled company blocklist
  resume/parser.py    — PDF/DOCX/TXT extraction + structured-resume cache
  resume/templates/   — HTML/CSS templates for PDF output
  tailor/engine.py    — Claude tailoring + verification pass
  output/pdf.py       — WeasyPrint HTML→PDF rendering
  apply/browser.py    — Playwright pre-fill with aggregator click-through
```

### Local state files (gitignored)

- `.jobapp_cache.json` — last search results, looked up by short job ID for `tailor` / `apply`
- `.jobapp_resume_cache.json` — structured resume cached by file mtime; avoids re-parsing on every search
- `output/<slug>/` — tailored `resume.pdf`, `cover_letter.pdf`, and `job_details.json` per job

## License

MIT
