from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from report_config import OUTPUT_DIR, SINGLE_PAGE_PDF_FILE

CHROME_CANDIDATES = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
]

EXPORT_CSS = """
@page {
  margin: 0;
}

html {
  scroll-behavior: auto !important;
}

body,
body * {
  -webkit-print-color-adjust: exact !important;
  print-color-adjust: exact !important;
}

body::before {
  position: absolute !important;
}

.skip-link {
  display: none !important;
}

.shell {
  padding-left: 0 !important;
}

.sticky-nav {
  position: static !important;
  inset: auto !important;
  width: calc(100% - 96px) !important;
  height: auto !important;
  flex-direction: row !important;
  align-items: center !important;
  margin: 48px auto 0 !important;
  padding: 16px 22px !important;
  border: 1px solid var(--line) !important;
}

.rail-brand {
  min-width: 200px !important;
  margin: 0 30px 0 0 !important;
}

.rail-label,
.rail-status {
  display: none !important;
}

.sticky-nav a,
.sticky-nav a:last-of-type {
  padding: 14px 18px !important;
  border: 0 !important;
  border-left: 1px solid var(--line) !important;
}

.table-wrap {
  overflow: visible !important;
}

.metric-table {
  min-width: 0 !important;
  table-layout: fixed !important;
}

.metric-table th,
.metric-table td {
  overflow-wrap: anywhere !important;
}

.hero,
section,
.body-card,
.lowlight-card,
.discussion-card,
.table-wrap,
.method-list li {
  break-inside: avoid !important;
}

*,
*::before,
*::after {
  animation: none !important;
  transition: none !important;
}
"""


def browser_executable() -> Path | None:
    """Find a local Chromium browser before falling back to Playwright's copy."""

    configured_path = os.environ.get("REPORT_CHROME_PATH")
    if configured_path:
        path = Path(configured_path).expanduser()
        if not path.exists():
            raise SystemExit(f"REPORT_CHROME_PATH does not exist: {path}")
        return path
    return next((path for path in CHROME_CANDIDATES if path.exists()), None)


def export_single_page_pdf() -> Path:
    """Export the complete interactive report as one tall, searchable PDF page."""

    source_path = OUTPUT_DIR / "index.html"
    if not source_path.exists():
        raise SystemExit("Build dist/index.html before exporting the report PDF.")
    SINGLE_PAGE_PDF_FILE.unlink(missing_ok=True)

    with sync_playwright() as playwright:
        executable = browser_executable()
        launch_options = {"headless": True}
        if executable is not None:
            launch_options["executable_path"] = str(executable)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(source_path.resolve().as_uri(), wait_until="networkidle")
        page.locator("details").evaluate_all(
            "elements => elements.forEach(element => { element.open = true; })"
        )
        page.add_style_tag(content=EXPORT_CSS)
        page.emulate_media(media="screen", color_scheme="dark", reduced_motion="reduce")
        page.evaluate("document.fonts.ready")
        height_pixels = page.evaluate(
            "Math.ceil(Math.max(document.body.scrollHeight, "
            "document.documentElement.scrollHeight)) + 2"
        )
        page.pdf(
            path=str(SINGLE_PAGE_PDF_FILE),
            width="15in",
            height=f"{height_pixels / 96:.4f}in",
            print_background=True,
            display_header_footer=False,
            margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"},
        )
        browser.close()

    print(
        f"Wrote one-page report PDF to {SINGLE_PAGE_PDF_FILE} "
        f"at 1440 by {height_pixels} CSS pixels."
    )
    return SINGLE_PAGE_PDF_FILE


def main() -> None:
    """Export the current generated report to its stable PDF path."""

    export_single_page_pdf()


if __name__ == "__main__":
    main()
