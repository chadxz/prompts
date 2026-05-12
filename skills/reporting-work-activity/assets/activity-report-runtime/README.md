# Activity Report

This runtime workspace holds the weekly Convergint activity report
generator and the small bit of shared local state around it. Private
source snapshots live in `data/` locally and generated HTML and JSON
output lands in `dist/`. The workspace keeps `data/.gitkeep` so the
directory shape exists, but the private snapshot files and generated
output are not checked into git.

## What runs here

- `generate_report.py` builds `dist/index.html`, `dist/summary.json`, and the
  drill-down pages under `dist/`.
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

On a fresh clone, `mise` will ask you to trust the repo config once. After
that, the commands above install the pinned Python version from `mise.toml`,
create the local `.venv`, and sync the dev tools declared in
`pyproject.toml`.

If you don't want to use `mise`, the direct `uv` path still works:

```bash
uv sync --dev
```

## Private data

The local fetch step uses `gh` for GitHub and `linctl` for Linear, so
you'll need both installed and authenticated before you run it.

```bash
gh auth status
linctl auth status
```

If either one isn't ready, use `gh auth login` or `linctl auth` first.

This repo does not check in the GitHub and Linear snapshot files. Run the
fetch step to populate `data/` locally:

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

Slack and Notion are refreshed separately through the Codex skill at
[reporting-work-activity](../../SKILL.md).
Copy `tracked_sources.template.json` to `tracked_sources.json` and fill in your
private Slack channels and Notion pages before you use that skill. The skill
loads that private config through `report_sources.py`, writes
`data/slack_channels.json` and `data/notion_pages.json`, and then reruns the
report.

Those two snapshot files are required for a real report build. If they are
missing or stale, use `$reporting-work-activity` before running
`mise run report`.

## Common workflow

Refresh the local snapshots:

```bash
mise run fetch
```

Refresh Slack and Notion from Codex connectors:

- Use `$reporting-work-activity` from Codex when you want the full report
  refresh, not just the GitHub and Linear snapshot pull.

Regenerate the report:

```bash
mise run report
```

Start the local controls server for the mute buttons:

```bash
mise run serve
```

If port `8765` is already in use, stop the existing report server first and
then rerun `mise run serve`.

Open
[`dist/index.html`](dist/index.html)
in the browser after a run. The shared mute list lives in
`muted_slack_channels.json`.

## Code quality

Run the normal formatting, linting, and test passes with `mise`:

```bash
mise run format
mise run lint
mise run test
mise run check
```

`check` is the quick gate. It runs formatting checks, Ruff linting, and the
smoke tests together.

If you want the raw `uv` commands instead:

```bash
uv run python populate_data.py
uv run ruff format .
uv run ruff check .
uv run pytest
```

## Notes

- `data/.gitkeep` is tracked, but the private files under `data/` are ignored.
- The generated HTML and JSON artifacts live in `dist/` and are ignored.
- `tracked_sources.template.json` is checked in, but `tracked_sources.json` is
  private local config and is ignored.
- `pyproject.toml` keeps the Python tooling config in one place.
- `mise.toml` pins the Python version and gives us stable task names for the
  common flows.
- `data/slack_channels.json` and `data/notion_pages.json` are required local
  snapshots written by the Codex skill, not by `mise run fetch`.
