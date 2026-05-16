from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from jobapp.config import Config
    from jobapp.models import Job

console = Console()


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
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)

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

    async def _try_fill_fields(self, page, resume_pdf_path: str) -> int:
        """Attempt to fill common application form fields. Returns count of fields filled."""
        filled = 0
        cfg = self.cfg

        # Common field selectors for name, email, phone
        field_mappings = [
            # (value, list of selectors to try)
            (cfg.user.name, [
                'input[name*="name" i]',
                'input[placeholder*="name" i]',
                'input[id*="name" i]',
                'input[aria-label*="name" i]',
            ]),
            (cfg.user.email, [
                'input[type="email"]',
                'input[name*="email" i]',
                'input[placeholder*="email" i]',
                'input[id*="email" i]',
            ]),
            (cfg.user.phone, [
                'input[type="tel"]',
                'input[name*="phone" i]',
                'input[placeholder*="phone" i]',
                'input[id*="phone" i]',
            ]),
        ]

        for value, selectors in field_mappings:
            if not value:
                continue
            for selector in selectors:
                try:
                    el = page.locator(selector).first
                    if await el.is_visible(timeout=1000):
                        await el.fill(value)
                        filled += 1
                        break
                except Exception:
                    continue

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
