from __future__ import annotations

import json
import sys
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pypdf import PdfReader

from report_config import (
    DATA_DIR,
    END,
    OUTPUT_DIR,
    PERSONAL_REPORT_SNAPSHOT_FILE,
    REFRESH_MANIFEST_FILE,
    REPORT_TIMEZONE,
    REQUIRED_DATA_FILES,
    SINGLE_PAGE_PDF_FILE,
    START,
    WINDOW_END,
    WINDOW_START,
)

EXPECTED_OUTPUT_FILES = [
    "index.html",
    "summary.json",
    "personal-github-prs-created.html",
    "personal-github-prs-merged.html",
    "personal-linear-issues.html",
    "personal-datadog-evidence.html",
    SINGLE_PAGE_PDF_FILE.name,
]


class ReportHtmlParser(HTMLParser):
    """Collect the structural facts needed to verify generated report HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_count = 0
        self.main_count = 0
        self.ids: set[str] = set()
        self.duplicate_ids: set[str] = set()
        self.hrefs: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "title":
            self.title_count += 1
        if tag == "main":
            self.main_count += 1
        element_id = attributes.get("id")
        if element_id:
            if element_id in self.ids:
                self.duplicate_ids.add(element_id)
            self.ids.add(element_id)
        href = attributes.get("href")
        if href is not None:
            self.hrefs.append(href)

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)

    @property
    def text(self) -> str:
        return normalize_text(" ".join(self.text_parts))


def normalize_text(value: str) -> str:
    """Collapse whitespace so source strings can be compared with rendered text."""

    return " ".join(value.split())


def load_json_object(path: Path) -> tuple[dict, list[str]]:
    """Load a required JSON object and return readable validation errors."""

    if not path.exists():
        return {}, [f"Missing required file: {path}"]
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {}, [f"Invalid JSON in {path}: {exc}"]
    if not isinstance(value, dict):
        return {}, [f"Expected a JSON object in {path}"]
    return value, []


def validate_narrative(narrative: dict, window_start: str, window_end: str) -> list[str]:
    """Validate the narrative shape and its structured reporting window."""

    errors: list[str] = []
    window = narrative.get("window")
    if not isinstance(window, dict):
        errors.append("Narrative is missing its structured `window` object.")
    elif window.get("start") != window_start or window.get("end") != window_end:
        errors.append(
            "Narrative window does not match the selected report window: "
            f"expected {window_start} through {window_end}."
        )

    if not isinstance(narrative.get("lede"), str) or not narrative["lede"].strip():
        errors.append("Narrative requires a non-empty `lede` string.")

    discussion = narrative.get("discussion")
    if not isinstance(discussion, dict):
        errors.append("Narrative requires a `discussion` object.")
    else:
        for key in ["title", "body"]:
            if not isinstance(discussion.get(key), str) or not discussion[key].strip():
                errors.append(f"Narrative discussion requires a non-empty `{key}` string.")

    for collection_name in ["workstreams", "lowlights"]:
        collection = narrative.get(collection_name)
        if not isinstance(collection, list) or not collection:
            errors.append(f"Narrative requires at least one {collection_name} item.")
            continue
        for index, item in enumerate(collection, start=1):
            if not isinstance(item, dict):
                errors.append(f"Narrative {collection_name} item {index} must be an object.")
                continue
            for key in ["title", "body"]:
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"Narrative {collection_name} item {index} requires `{key}`.")

    methodology = narrative.get("methodology")
    if not isinstance(methodology, list) or not methodology:
        errors.append("Narrative requires methodology notes.")
    elif not all(isinstance(item, str) and item.strip() for item in methodology):
        errors.append("Every narrative methodology note must be a non-empty string.")

    return errors


def validate_refresh_manifest(
    manifest: dict,
    window_start: str,
    window_end: str,
    timezone_name: str,
) -> list[str]:
    """Validate the machine-readable receipt for every evidence refresh."""

    errors: list[str] = []
    expected_window = {
        "start": window_start,
        "end": window_end,
        "timezone": timezone_name,
    }
    if manifest.get("window") != expected_window:
        errors.append(
            "Refresh manifest window does not match the selected report window: "
            f"expected {window_start} through {window_end} in {timezone_name}."
        )

    refreshed_at = manifest.get("refreshed_at")
    if not isinstance(refreshed_at, str):
        errors.append("Refresh manifest requires an ISO `refreshed_at` timestamp.")
    else:
        try:
            datetime.fromisoformat(refreshed_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("Refresh manifest has an invalid `refreshed_at` timestamp.")

    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        return errors + ["Refresh manifest requires a `sources` object."]
    allowed_statuses = {"refreshed", "confirmed_current"}
    for source in ["github", "linear", "slack", "notion", "datadog"]:
        receipt = sources.get(source)
        if not isinstance(receipt, dict) or receipt.get("status") not in allowed_statuses:
            errors.append(f"Refresh manifest requires a current `{source}` receipt.")
    return errors


def parse_html_pages(output_dir: Path) -> tuple[dict[Path, ReportHtmlParser], list[str]]:
    """Parse every generated HTML page and validate its base semantics."""

    pages: dict[Path, ReportHtmlParser] = {}
    errors: list[str] = []
    for path in sorted(output_dir.glob("*.html")):
        parser = ReportHtmlParser()
        parser.feed(path.read_text())
        pages[path.resolve()] = parser
        if parser.title_count != 1:
            errors.append(f"{path.name} has {parser.title_count} title elements; expected 1.")
        if parser.main_count != 1:
            errors.append(f"{path.name} has {parser.main_count} main elements; expected 1.")
        if parser.duplicate_ids:
            duplicate_list = ", ".join(sorted(parser.duplicate_ids))
            errors.append(f"{path.name} has duplicate IDs: {duplicate_list}.")
    return pages, errors


def validate_local_links(output_dir: Path, pages: dict[Path, ReportHtmlParser]) -> list[str]:
    """Confirm that every generated local link and fragment resolves."""

    errors: list[str] = []
    output_root = output_dir.resolve()
    for source_path, parser in pages.items():
        for href in parser.hrefs:
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                continue
            relative_path = unquote(parsed.path)
            if relative_path.startswith("/"):
                target_path = output_root / relative_path.lstrip("/")
            elif relative_path:
                target_path = source_path.parent / relative_path
            else:
                target_path = source_path
            target_path = target_path.resolve()
            try:
                target_path.relative_to(output_root)
            except ValueError:
                errors.append(f"{source_path.name} links outside dist/: {href}")
                continue
            if target_path.is_dir():
                target_path = target_path / "index.html"
            if not target_path.exists():
                errors.append(f"{source_path.name} has a missing local link: {href}")
                continue
            if parsed.fragment and target_path.suffix == ".html":
                target_parser = pages.get(target_path)
                if target_parser is None or parsed.fragment not in target_parser.ids:
                    errors.append(f"{source_path.name} has a missing fragment link: {href}")
    return errors


def report_window_label(window_start: str, window_end: str) -> str:
    """Format the exact date label used by the HTML report."""

    start = date.fromisoformat(window_start)
    end = date.fromisoformat(window_end)
    return f"{start.strftime('%B')} {start.day} through {end.strftime('%B')} {end.day}, {end.year}"


def narrative_markers(narrative: dict) -> list[str]:
    """Return current narrative text that must appear in the generated home page."""

    markers = [narrative["lede"], narrative["discussion"]["title"]]
    markers.extend(item["title"] for item in narrative["workstreams"])
    markers.extend(item["title"] for item in narrative["lowlights"])
    markers.extend(narrative["methodology"])
    return markers


def validate_single_page_pdf(path: Path, expected_window_label: str) -> list[str]:
    """Confirm the report PDF is one readable page with current report text."""

    if not path.exists():
        return [f"Missing required single-page PDF: {path}"]
    errors: list[str] = []
    if path.stat().st_size < 20_000:
        errors.append(f"Single-page PDF is unexpectedly small: {path.stat().st_size} bytes.")
    try:
        reader = PdfReader(path)
    except Exception as exc:
        return errors + [f"Could not read single-page PDF: {exc}"]
    if len(reader.pages) != 1:
        errors.append(f"Report PDF has {len(reader.pages)} pages; expected exactly 1.")
        return errors

    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    if height <= width:
        errors.append("Single-page PDF should be taller than it is wide.")
    text = normalize_text(page.extract_text() or "")
    for marker in ["Chad's", expected_window_label]:
        if normalize_text(marker).lower() not in text.lower():
            errors.append(f"Single-page PDF is missing current report text: {marker}")
    return errors


def verify_report() -> list[str]:
    """Verify snapshot freshness, generated semantics, narrative, and local links."""

    errors = [
        f"Missing required snapshot: {DATA_DIR / name}"
        for name in REQUIRED_DATA_FILES
        if not (DATA_DIR / name).exists()
    ]
    errors.extend(
        f"Missing required report output: {OUTPUT_DIR / name}"
        for name in EXPECTED_OUTPUT_FILES
        if not (OUTPUT_DIR / name).exists()
    )
    if errors:
        return errors

    narrative, narrative_load_errors = load_json_object(PERSONAL_REPORT_SNAPSHOT_FILE)
    refresh_manifest, manifest_load_errors = load_json_object(REFRESH_MANIFEST_FILE)
    summary, summary_load_errors = load_json_object(OUTPUT_DIR / "summary.json")
    errors.extend(narrative_load_errors)
    errors.extend(manifest_load_errors)
    errors.extend(summary_load_errors)
    if errors:
        return errors

    narrative_errors = validate_narrative(narrative, WINDOW_START, WINDOW_END)
    errors.extend(narrative_errors)
    errors.extend(
        validate_refresh_manifest(
            refresh_manifest,
            WINDOW_START,
            WINDOW_END,
            REPORT_TIMEZONE.key,
        )
    )
    if summary.get("start") != START.isoformat():
        errors.append("Generated summary start does not match the selected report window.")
    if summary.get("end") != END.isoformat():
        errors.append("Generated summary end does not match the selected report window.")
    if summary.get("narrative") != narrative:
        errors.append("Generated summary narrative does not match personal_report.json.")
    if summary.get("refresh_manifest") != refresh_manifest:
        errors.append("Generated summary receipt does not match refresh_manifest.json.")

    pages, page_errors = parse_html_pages(OUTPUT_DIR)
    errors.extend(page_errors)
    errors.extend(validate_local_links(OUTPUT_DIR, pages))
    index_parser = pages.get((OUTPUT_DIR / "index.html").resolve())
    if index_parser is None:
        errors.append("Could not parse generated index.html.")
        return errors

    expected_label = normalize_text(report_window_label(WINDOW_START, WINDOW_END))
    if expected_label not in index_parser.text:
        errors.append(f"Generated index.html does not show the current window: {expected_label}.")
    if not narrative_errors:
        for marker in narrative_markers(narrative):
            normalized_marker = normalize_text(marker)
            if normalized_marker not in index_parser.text:
                errors.append(
                    "Generated index.html is missing current narrative text: "
                    f"{normalized_marker[:80]}"
                )
    errors.extend(validate_single_page_pdf(SINGLE_PAGE_PDF_FILE, expected_label))
    return errors


def main() -> None:
    """Run report verification and return a useful process exit status."""

    errors = verify_report()
    if errors:
        print("Report verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)
    print(
        "Report verification passed for "
        f"{WINDOW_START} through {WINDOW_END}: source receipts, narrative, "
        "HTML semantics, local links, and the one-page PDF are consistent."
    )


if __name__ == "__main__":
    main()
