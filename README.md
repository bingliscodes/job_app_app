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

### Tailor your resume

```bash
jobapp tailor <job-id>
```

Uses Claude to analyze the job posting and your resume, then generates:
- A tailored resume PDF with relevant experience highlighted
- A cover letter addressing the specific role and company
- A list of key matches and suggestions

Output is saved to `./output/<company>_<title>_<date>/`.

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
```

Interactive flow that chains all steps: search for jobs, select which ones to apply to, tailor materials for each, and optionally open the browser to apply.

## Job Sources

| Source | API Key Required | Notes |
|--------|-----------------|-------|
| [Arbeitnow](https://www.arbeitnow.com/api/job-board-api) | No | Free, no auth. Client-side keyword filtering. |
| [The Muse](https://www.themuse.com/developers/api/v2) | No (optional) | Free tier: 500 req/hr. Client-side keyword filtering. |
| [Adzuna](https://developer.adzuna.com/) | Yes | Best filtering (keyword, location, recency). Register for free keys. |

## Supported Resume Formats

- PDF (`.pdf`)
- Word Document (`.docx`)
- Plain text (`.txt`, `.md`)

## Project Structure

```
src/jobapp/
  cli.py              — CLI commands (search, tailor, apply, pipeline)
  config.py           — Configuration loading
  models.py           — Data models (Job, ParsedResume, TailoredMaterial)
  sourcing/           — Job board API clients
  resume/parser.py    — Resume text extraction
  resume/templates/   — HTML/CSS templates for PDF output
  tailor/engine.py    — Claude AI resume tailoring
  output/pdf.py       — PDF generation via WeasyPrint
  apply/browser.py    — Playwright browser automation
```

## License

MIT
