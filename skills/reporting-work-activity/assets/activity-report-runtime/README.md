# Activity Report

This runtime workspace holds the weekly Convergint activity report generator and
the small bit of shared local state around it. Private source snapshots live in
`data/` locally and generated HTML and JSON output lands in `dist/`. The
workspace keeps `data/.gitkeep` so the directory shape exists, but the private
snapshot files and generated output are not checked into git.

## What runs here

- `build_report.py` builds the HTML report and its required single-page PDF.
- `generate_report.py` builds `dist/index.html`, `dist/summary.json`, and the
  drill-down pages under `dist/`.
- `export_single_page_pdf.py` uses Chromium to write
  `dist/chad-weekly-activity-report-single-page.pdf`.
- `verify_report.py` checks windows, receipts, narrative, HTML, local links, and
  the one-page PDF contract.
- `bootstrap_tracked_sources.py` seeds `tracked_sources.json` from existing
  local snapshots or `dist/summary.json`.
- `populate_data.py` fetches the local GitHub and Linear snapshots that the
  report reads.
- `report_sources.py` loads the private tracked Slack channels and Notion pages
  from `tracked_sources.json` for connector-backed refreshes.
- `report_server.py` serves the local HTTP endpoint used by the Slack mute
  buttons.
- `data/` holds the private source snapshots used to build the current report.
- `muted_slack_channels.json` is tracked and shared.

## Prerequisites

We manage the Python runtime with `mise` and the environment with `uv`.

```bash
mise trust mise.toml
mise install
mise run setup
```

On a fresh clone, `mise` will ask you to trust the repo config once. After that,
the commands above install the pinned Python version from `mise.toml`, create
the local `.venv`, and sync the dev tools declared in `pyproject.toml`.

If you don't want to use `mise`, the direct `uv` path still works:

```bash
uv sync --dev
```

## Private data

The local fetch step uses `gh` for GitHub and `linctl` for Linear, so you'll
need both installed and authenticated before you run it.

```bash
gh auth status
linctl auth status
```

If either one isn't ready, use `gh auth login` or `linctl auth` first.

PDF export uses Playwright with a locally installed Chrome or Chromium. On
macOS it discovers Google Chrome automatically. Elsewhere, set
`REPORT_CHROME_PATH` or install Playwright's managed browser:

```bash
uv run playwright install chromium
```

This repo does not check in the GitHub and Linear snapshot files. Run the fetch
step to populate `data/` locally:

```bash
mise run fetch
```

That writes these report inputs:

- `github_issues_closed.json`
- `github_issues_created.json`
- `github_prs_created.json`
- `github_prs_merged.json`
- `github_repos.json`
- `linear_issues_updated.json`
- `linear_projects_month.json`
- `linear_teams.json`

The fetch step also refreshes `data/linear_team_dumps/` so we've got the
per-team Linear samples that feed the deduped issue export.

Slack, Notion, scoped Datadog evidence, and the current personal narrative are
refreshed separately through the Codex skill at
[reporting-work-activity](../../SKILL.md). If
`tracked_sources.json` is missing, first run:

```bash
mise run bootstrap-tracked-sources
```

That task tries to seed the config from `data/slack_channels.json`,
`data/notion_pages.json`, or an older `dist/summary.json`. Only if that fails
should you copy `tracked_sources.template.json` to `tracked_sources.json` and
fill in your private Slack channels and Notion pages manually. The skill loads
that private config through `report_sources.py`, writes
`data/slack_channels.json` and `data/notion_pages.json`, writes the current
`data/refresh_manifest.json` and `data/personal_report.json` after the evidence
pass, and then reruns the report. When the runtime requires
`data/datadog_activity.json`, keep that snapshot scoped to the selected report
mode. Personal reports should use Datadog as evidence for Chad's workstreams,
not as a broad org feed.

Treat `tracked_sources.json` as the starting point for a refresh, not as the
complete ceiling of what the report is allowed to include. The skill should
refresh those seeded channels and pages first, then run a bounded discovery pass
every time so the current week can add new Slack or Notion sources when they
matter.

On reruns, clear the generated cache by default unless the user explicitly asked
to keep or use cache:

```bash
mise run clear-cache
```

That clears generated JSON snapshots under `data/`, clears
`data/linear_team_dumps/`, and clears `dist/`. It preserves
`tracked_sources.json` and `muted_slack_channels.json`.

Those snapshot files are required for a real report build. If they are missing
or stale, use `$reporting-work-activity` before running `mise run report`.

The narrative snapshot includes a structured `window` object. The report build
fails when its start and end dates do not match the window selected in
`report_config.py`. A recently modified file is not accepted as proof that the
narrative is current.

The refresh manifest includes the same window, a refresh timestamp, and a
receipt for GitHub, Linear, Slack, Notion, and Datadog. The renderer rejects a
missing receipt. `confirmed_current` is reserved for a run where the user
explicitly approved preserved cache.

## Common workflow

Refresh the local snapshots:

```bash
date '+%Y-%m-%d %H:%M:%S %Z'
export REPORT_DATE="$(date +%F)"
export REPORT_TIMEZONE="America/Chicago"
mise run bootstrap-tracked-sources
mise run clear-cache
mise run fetch
```

Refresh Slack, Notion, and the current narrative through Codex:

- Use `$reporting-work-activity` from Codex when you want the full report
  refresh, not just the GitHub and Linear snapshot pull. The refresh writes
  `data/refresh_manifest.json` and `data/personal_report.json` after the
  evidence pass so the report cannot reuse an older source receipt or
  narrative.

Regenerate the HTML report and required single-page PDF, then verify both:

```bash
mise run report
mise run verify-report
```

Keep the same `REPORT_DATE` and `REPORT_TIMEZONE` exported for fetching,
rendering, and verification. The default is the rolling seven days ending on
`REPORT_DATE`; use a prior Sunday only when a previous calendar week was
explicitly requested.

Start the local controls server for the mute buttons:

```bash
mise run serve
```

If port `8765` is already in use, stop the existing report server first and then
rerun `mise run serve`. The skill should leave the rebuilt report reachable at
`http://127.0.0.1:8765/`, not just write files into `dist/`. It should also open
that URL in the in-app browser and verify the page that actually renders.

Open [`dist/index.html`](dist/index.html) in the browser after a run. The shared
mute list lives in `muted_slack_channels.json`.

The stable PDF output is the [required single-page report][report-pdf].
`mise run report` always writes it. Use `mise run pdf` only when re-exporting an
unchanged HTML report.

Render and inspect the PDF after every run:

```bash
mkdir -p tmp/pdfs
pdftoppm -png -singlefile -r 90 \
  dist/chad-weekly-activity-report-single-page.pdf \
  tmp/pdfs/chad-weekly-activity-report
pdfinfo dist/chad-weekly-activity-report-single-page.pdf
```

Delete `tmp/pdfs/` after inspection. The report is not complete until the PDF
has exactly one page and the rendered PNG has no clipping, overlap, gray blocks,
missing backgrounds, or unreadable tables.

## UI redesigns

When the request includes a new UI, retheme, coat of paint, or a distinctly new
look, follow the
[visual design contract](../../references/visual-design-contract.md). Capture
the baseline, choose a named concept, materially change at least four of five
visual dimensions, and inspect desktop and mobile output. Replace superseded
markup and CSS instead of appending an override stylesheet. Remove any asset
generation that the final report no longer uses.

## Code quality

Run the normal formatting, linting, and test passes with `mise`:

```bash
mise run format
mise run lint
mise run test
mise run check
```

`check` is the quick gate. It runs formatting checks, Ruff linting, and the
smoke tests together. `verify-report` is the separate generated-artifact gate;
it needs the private snapshots plus built HTML and PDF artifacts, so it is
intentionally not part of `check`.

If you want the raw `uv` commands instead:

```bash
uv run python clear_runtime_cache.py
uv run python populate_data.py
uv run python build_report.py
uv run python verify_report.py
uv run ruff format .
uv run ruff check .
uv run pytest
```

## Notes

- `data/.gitkeep` is tracked, but the private files under `data/` are ignored.
- The generated HTML and JSON artifacts live in `dist/` and are ignored.
- `tracked_sources.template.json` is checked in, but `tracked_sources.json` is
  private local config and is ignored.
- `dist/summary.json` is the last-resort bootstrap source for
  `tracked_sources.json` when current Slack and Notion snapshots are missing.
- `pyproject.toml` keeps the Python tooling config in one place.
- `mise.toml` pins the Python version and gives us stable task names for the
  common flows.
- `data/slack_channels.json`, `data/notion_pages.json`, and any required
  `data/datadog_activity.json` file are local snapshots written or curated by
  the Codex skill, not by `mise run fetch`.
- `data/refresh_manifest.json` is the required machine-readable receipt for
  every evidence source and the selected window.
- `data/personal_report.json` is the required current narrative snapshot. The
  report fails instead of falling back to hard-coded conclusions when it is
  missing or when its structured window does not match the selected window.
- `verify_report.py` confirms required snapshots and outputs, exact summary and
  narrative windows, source receipts, current narrative text, HTML semantics,
  local links, and the single-page PDF contract.

[report-pdf]: dist/chad-weekly-activity-report-single-page.pdf
