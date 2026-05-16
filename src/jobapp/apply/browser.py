from __future__ import annotations

import platform
import subprocess
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from rich.console import Console

if TYPE_CHECKING:
    from jobapp.config import Config
    from jobapp.models import Job

console = Console()


_DEAD_LISTING_PATTERNS = (
    "job not found",
    "page not found",
    "not found",
    "no longer available",
    "no longer accepting",
    "this position has been filled",
    "this job has been filled",
    "this job is no longer",
    "this posting is no longer",
    "this opportunity is no longer",
    "this requisition is no longer",
    "position is no longer",
    "job has expired",
    "posting has expired",
    "job has been removed",
    "job has been closed",
    "404",
)


async def _looks_like_dead_listing(page) -> bool:
    """Heuristic: does this page look like a removed/expired job posting?

    Checks the document title and the first few visible headings. Avoids
    matching the full body text — generic words like "not found" might appear
    in unrelated job-description language.
    """
    try:
        title = (await page.title() or "").lower()
        if any(pat in title for pat in _DEAD_LISTING_PATTERNS):
            return True
    except Exception:
        pass

    for tag in ("h1", "h2"):
        try:
            count = await page.locator(tag).count()
            for i in range(min(count, 3)):
                text = (await page.locator(tag).nth(i).text_content(timeout=1000) or "").lower()
                if any(pat in text for pat in _DEAD_LISTING_PATTERNS):
                    return True
        except Exception:
            continue

    return False


async def _click_bypass_link(page, *, verbose: bool = True):
    """Look for an email-capture interstitial and click the bypass link.

    Adzuna shows a "Receive similar jobs by email" overlay with a green
    "No thanks, take me to the job" link that completes the redirect to the
    employer page. The bypass may open a new tab or navigate the same page.
    """
    bypass_selectors = [
        'a:has-text("No thanks, take me to the job")',
        'a:has-text("take me to the job")',
        'a:has-text("No thanks")',
        'button:has-text("No thanks, take me to the job")',
        'button:has-text("No thanks")',
    ]

    bypass_el = None
    for selector in bypass_selectors:
        try:
            el = page.locator(selector).first
            if await el.count() == 0:
                continue
            if await el.is_visible(timeout=3000):
                bypass_el = el
                break
        except Exception:
            continue

    if bypass_el is None:
        return None

    if verbose:
        console.print("  [dim]Dismissing email-capture overlay...[/dim]")
    initial_url = page.url
    new_page = None
    try:
        async with page.context.expect_page(timeout=8000) as new_page_info:
            await bypass_el.click()
        new_page = await new_page_info.value
    except Exception:
        pass

    if new_page is not None:
        try:
            await new_page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        if verbose:
            console.print(f"  [green]→ {new_page.url}[/green]")
        return new_page

    try:
        await page.wait_for_url(lambda u: u != initial_url, timeout=8000)
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
        if verbose:
            console.print(f"  [green]→ {page.url}[/green]")
        return page
    except Exception:
        return None


async def _dismiss_overlays(page) -> None:
    """Best-effort: close cookie banners and email-signup modals that block clicks.

    Adzuna sometimes shows an email-capture modal on page load ("Leave us your
    email address and we'll send you similar new jobs"). The close action is
    inconsistent across versions — a close icon, a "No thanks" link, or ESC.
    """
    # Adzuna's "No thanks, take me to the job" link sometimes also closes the
    # on-load email modal without navigating away. Try it first.
    text_dismissals = [
        'a:has-text("No thanks, take me to the job")',
        'a:has-text("No thanks")',
        'button:has-text("No thanks")',
        'button:has-text("Accept all")',
        'button:has-text("Accept")',
        'button:has-text("I agree")',
        'button:has-text("Got it")',
        'button:has-text("Close")',
        'a:has-text("Close")',
    ]
    icon_dismissals = [
        'button[aria-label*="close" i]',
        'button[aria-label*="dismiss" i]',
        'a[aria-label*="close" i]',
        '[role="button"][aria-label*="close" i]',
        # Adzuna's email modal close: a clickable element near "Receive similar jobs"
        '[class*="modal" i] [class*="close" i]',
        '[class*="popup" i] [class*="close" i]',
    ]
    for selector in text_dismissals + icon_dismissals:
        try:
            el = page.locator(selector).first
            if await el.count() > 0 and await el.is_visible(timeout=500):
                await el.click(timeout=2000)
                # one click is usually enough; give the modal a beat to close
                await page.wait_for_timeout(200)
        except Exception:
            continue

    # Last resort: ESC often closes modals that don't expose a close control.
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass


def _activate_app_macos() -> None:
    """Force the Chrome for Testing window to the macOS foreground.

    Playwright's bring_to_front() only affects tab order inside the browser;
    it doesn't activate the app at the OS level. AppleScript does.
    """
    if platform.system() != "Darwin":
        return
    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome for Testing" to activate'],
            check=False, timeout=2, capture_output=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        pass


async def _try_fill_first_visible(page, selectors: list[str], value: str) -> bool:
    """Fill the first visible input matching any of the given selectors. Returns True if filled."""
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if await el.count() == 0:
                continue
            if not await el.is_visible(timeout=1000):
                continue
            await el.fill(value)
            return True
        except Exception:
            continue
    return False


async def _click_through_if_aggregator(page, *, verbose: bool = True):
    """If on Adzuna/The Muse, click Apply and follow to the employer site."""
    host = (urlparse(page.url).hostname or "").lower()
    aggregator_hosts = ("adzuna.com", "themuse.com")
    if not any(agg in host for agg in aggregator_hosts):
        return page

    if verbose:
        console.print(f"  [dim]On aggregator ({host}); looking for Apply button...[/dim]")

    await page.wait_for_timeout(1000)
    await _dismiss_overlays(page)

    # Selectors are tried in order; most specific first. The sticky "Apply Now"
    # button in The Muse's header often just scrolls the page rather than
    # navigating, so we prefer the more explicit "Apply on …" / "Apply for this
    # job" variants.
    apply_selectors = [
        'a:has-text("Apply on Company")',
        'button:has-text("Apply on Company")',
        'a:has-text("Apply on company site")',
        'button:has-text("Apply on company site")',
        'a:has-text("Apply on")',
        'button:has-text("Apply on")',
        'a:has-text("Apply Externally")',
        'a:has-text("Apply for this job")',
        'a:has-text("Apply Now")',
        'button:has-text("Apply Now")',
        'a:has-text("Apply")',
        'button:has-text("Apply")',
    ]

    initial_url = page.url

    # Try each selector. Click and see if it navigates (new tab or same page).
    # If it doesn't navigate (e.g. sticky "Apply Now" that only scrolls), try
    # the next selector instead of giving up.
    for selector in apply_selectors:
        try:
            el = page.locator(selector).first
            if await el.count() == 0:
                continue
            if not await el.is_visible(timeout=1000):
                continue
        except Exception:
            continue

        if verbose:
            try:
                label = (await el.text_content(timeout=500) or "").strip()[:40]
                console.print(f"  [dim]Trying: {selector!r} ({label!r})[/dim]")
            except Exception:
                console.print(f"  [dim]Trying: {selector!r}[/dim]")

        try:
            await el.click(timeout=5000)
        except Exception:
            continue

        bypass_target = await _click_bypass_link(page, verbose=verbose)
        if bypass_target is not None:
            return bypass_target

        new_page = None
        try:
            async with page.context.expect_page(timeout=3000) as new_page_info:
                pass
            new_page = await new_page_info.value
        except Exception:
            pass

        if new_page is not None:
            try:
                await new_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            if verbose:
                console.print(f"  [green]→ {new_page.url}[/green]")
            return new_page

        # Same-page navigation?
        try:
            await page.wait_for_url(lambda u: u != initial_url, timeout=3000)
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            if verbose:
                console.print(f"  [green]→ {page.url}[/green]")
            return page
        except Exception:
            if verbose:
                console.print("  [dim]No navigation — trying next selector...[/dim]")
            continue

    if verbose:
        console.print("[yellow]  Apply button found no working selector; staying on aggregator page.[/yellow]")
    return page


async def validate_job_url(url: str, *, timeout_ms: int = 30000) -> bool:
    """Return True if the job URL appears to be an active listing.

    Headless Playwright navigation: opens the URL, follows aggregator
    click-through, then runs the dead-listing heuristic on the final page.
    On any error (timeout, navigation failure), returns True (lenient —
    assume active rather than dropping legitimate jobs because of flaky network).
    """
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception:
                    return True  # network/timeout — assume active
                page = await _click_through_if_aggregator(page, verbose=False)
                try:
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                is_dead = await _looks_like_dead_listing(page)
                return not is_dead
            finally:
                await browser.close()
    except Exception:
        return True


async def validate_jobs(jobs: list, *, concurrency: int = 4) -> tuple[list, list]:
    """Validate a list of jobs in parallel. Returns (active, dead) lists.

    `concurrency` caps the number of headless Playwright pages running
    simultaneously to avoid hammering the network or local resources.
    """
    import asyncio

    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[object, bool]] = []

    async def _check(job):
        async with sem:
            console.print(f"  [dim]Checking {job.title[:50]} @ {job.company}...[/dim]")
            ok = await validate_job_url(job.url)
            return job, ok

    pairs = await asyncio.gather(*[_check(j) for j in jobs])
    active = [j for j, ok in pairs if ok]
    dead = [j for j, ok in pairs if not ok]
    return active, dead


class ApplicationBot:
    """Playwright-based browser automation for pre-filling job application forms.

    IMPORTANT: This never auto-submits. It opens a visible browser, fills what it can,
    and hands control to the user.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg

    async def fill_application(self, job: Job, resume_pdf_path: str) -> None:
        from playwright.async_api import async_playwright

        console.print(f"Opening [cyan]{job.url}[/cyan] in browser...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            context = await browser.new_context(no_viewport=True)
            page = await context.new_page()

            await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            await page.bring_to_front()
            _activate_app_macos()

            # If we landed on an aggregator (Adzuna, The Muse), click Apply to
            # reach the real employer application page before filling.
            page = await self._click_through_if_aggregator(page)
            await page.bring_to_front()
            _activate_app_macos()

            # Check whether the listing has been removed. Aggregators (especially
            # The Muse) don't prune their feed, so we can land on a stale page
            # whose body says "Job Not Found".
            if await _looks_like_dead_listing(page):
                console.print(
                    "[red]This listing appears to be removed or expired "
                    "(the destination page says the job is no longer available).[/red]"
                )
                console.print("[yellow]Skipping form pre-fill — nothing to fill on a 404 page.[/yellow]")
                console.print("[bold]Browser is open — review and close manually.[/bold]")
                console.print("[dim]Press Enter in this terminal when done...[/dim]")
                import sys
                sys.stdin.readline()
                await browser.close()
                return

            # Try to detect and fill common form fields
            filled = await self._try_fill_fields(page, resume_pdf_path)

            if filled:
                console.print(f"[green]Pre-filled {filled} field(s).[/green]")
            else:
                console.print("[yellow]Could not detect application form fields automatically.[/yellow]")

            console.print("[bold]Browser is open — review and submit the application manually.[/bold]")
            console.print("[dim]Press Enter in this terminal when done...[/dim]")

            # Wait for the user to finish
            import sys
            sys.stdin.readline()

            await browser.close()

    async def _click_through_if_aggregator(self, page):
        return await _click_through_if_aggregator(page, verbose=True)

    async def _try_fill_fields(self, page, resume_pdf_path: str) -> int:
        """Attempt to fill common application form fields. Returns count of fields filled."""
        filled = 0
        cfg = self.cfg

        # Split the name for forms that have separate first/last fields
        # (Greenhouse, Lever, Ashby, Workable all do this).
        name_parts = cfg.user.name.strip().split(None, 1) if cfg.user.name else []
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Try split-name fields first. If found, also skip the full-name pass.
        split_name_filled = False
        if first_name:
            first_selectors = [
                'input[autocomplete="given-name"]',
                'input[name="first_name"]',
                'input[id="first_name"]',
                'input[name*="first" i][name*="name" i]',
                'input[id*="first" i][id*="name" i]',
                'input[placeholder*="First name" i]',
                'input[aria-label*="First name" i]',
            ]
            if await _try_fill_first_visible(page, first_selectors, first_name):
                filled += 1
                split_name_filled = True

        if last_name:
            last_selectors = [
                'input[autocomplete="family-name"]',
                'input[name="last_name"]',
                'input[id="last_name"]',
                'input[name*="last" i][name*="name" i]',
                'input[id*="last" i][id*="name" i]',
                'input[placeholder*="Last name" i]',
                'input[aria-label*="Last name" i]',
            ]
            if await _try_fill_first_visible(page, last_selectors, last_name):
                filled += 1
                split_name_filled = True

        # Fall back to "full name" field if no split fields were found.
        if not split_name_filled and cfg.user.name:
            full_name_selectors = [
                'input[autocomplete="name"]',
                'input[name="name"]',
                'input[id="name"]',
                'input[name*="name" i]',
                'input[placeholder*="name" i]',
                'input[id*="name" i]',
                'input[aria-label*="name" i]',
            ]
            if await _try_fill_first_visible(page, full_name_selectors, cfg.user.name):
                filled += 1

        # Email
        if cfg.user.email:
            email_selectors = [
                'input[type="email"]',
                'input[autocomplete="email"]',
                'input[name*="email" i]',
                'input[id*="email" i]',
                'input[placeholder*="email" i]',
            ]
            if await _try_fill_first_visible(page, email_selectors, cfg.user.email):
                filled += 1

        # Phone
        if cfg.user.phone:
            phone_selectors = [
                'input[type="tel"]',
                'input[autocomplete="tel"]',
                'input[name*="phone" i]',
                'input[id*="phone" i]',
                'input[placeholder*="phone" i]',
            ]
            if await _try_fill_first_visible(page, phone_selectors, cfg.user.phone):
                filled += 1

        # LinkedIn URL — Greenhouse, Lever, and most ATSs have an explicit field.
        if cfg.user.linkedin_url:
            linkedin_selectors = [
                'input[name*="linkedin" i]',
                'input[id*="linkedin" i]',
                'input[placeholder*="LinkedIn" i]',
                'input[aria-label*="LinkedIn" i]',
            ]
            if await _try_fill_first_visible(page, linkedin_selectors, cfg.user.linkedin_url):
                filled += 1

        # Try to upload resume
        try:
            file_input = page.locator('input[type="file"]').first
            if await file_input.count() > 0:
                await file_input.set_input_files(resume_pdf_path)
                filled += 1
                console.print(f"  [green]Uploaded resume PDF[/green]")
        except Exception:
            pass

        return filled
