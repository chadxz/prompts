# Activity report runtime contract

Use this file only when you need the exact local file contract for the runtime
workspace bundled with this skill under `assets/activity-report-runtime`.

## Contents

- Repo files to read first
- Reporting window contract
- Snapshot files written during refresh
- Snapshot schemas
- Verification rules

## Repo files to read first

- `README.md`: local operator workflow
- `report_config.py`: reporting window, data paths, and output paths
- `report_sources.py`: loader and validator for the private tracked source
  config
- `generate_report.py`: snapshot loading and report rendering behavior
- `verify_report.py`: generated artifact and narrative freshness checks

## Reporting window contract

Look up the local date before the run:

```bash
date '+%Y-%m-%d %H:%M:%S %Z'
export REPORT_DATE="$(date +%F)"
export REPORT_TIMEZONE="America/Chicago"
```

The runtime uses a rolling seven-day window ending on `REPORT_DATE`. Keep the
same explicit date and timezone in the environment for `mise run fetch`,
`mise run report`, and `mise run verify-report`.

For the latest weekly activity report, use today's local date. Set `REPORT_DATE`
to a prior Sunday only when the user explicitly requests the previous calendar
week. State the derived inclusive start and end dates before fetching connector
data.

Timestamp queries use an inclusive local start and exclusive next-day end.
Slack's `after:` and `before:` search dates must express the same boundary.

## Tracked source config

Slack and Notion refreshes are driven by a private local config file:

- `tracked_sources.json`

That file is ignored. Copy the checked-in `tracked_sources.template.json` to
`tracked_sources.json` and fill in your private tracked sources before using the
skill only if the bootstrap task cannot seed it.

Important interpretation:

- `tracked_sources.json` is a seed list for the refresh
- it is not a guarantee that only those channels or pages matter this week
- the skill must run a bounded discovery pass every refresh
- the skill should widen beyond that seed list when the current week points to
  new relevant sources

Bootstrap path:

- run `mise run bootstrap-tracked-sources`
- it first checks `data/slack_channels.json` and `data/notion_pages.json`
- it falls back to `dist/summary.json` if the live snapshots are missing

Cache rule:

- on reruns, clear generated cache by default unless the user explicitly asked
  to keep or use cache
- cache means generated `data/*.json`, `data/linear_team_dumps/*.json`, and
  `dist/*`
- do not clear `tracked_sources.json` or `muted_slack_channels.json`

`tracked_sources.json` must be a JSON object with:

- `slack_channels`: list of tracked Slack channel objects
- `notion_pages`: list of tracked Notion page objects

Tracked Slack channel objects require:

- `channel`: channel name including `#`

Tracked Slack channel objects may also include:

- `url`: direct channel URL
- `focus`: short reminder about what to look for in the channel

Tracked Notion page objects require:

- `title`: page title
- `url`: page URL

Tracked Notion page objects may also include:

- `focus`: short reminder about what to look for in the page

Refresh rule:

- start with the seeded Slack channels and Notion pages
- always run the bounded discovery pass after the seeded refresh
- then do a bounded discovery pass and include newly important sources in the
  generated snapshots
- if a new source looks structurally useful for future runs, append it to
  `tracked_sources.json`

Discovery pass rule:

- derive search terms from the current week's top GitHub repos, interesting
  Linear issue identifiers, and notable nouns from current GitHub or Linear
  titles
- reuse titles and linked doc names surfaced during the Slack pass when
  searching Notion
- stop after two consecutive query rounds fail to add a meaningful new source

Example:

```json
{
  "slack_channels": [
    {
      "channel": "#example-channel",
      "url": "https://app.slack.com/client/T123/C456",
      "focus": "Replace with why the report should keep watching this."
    }
  ],
  "notion_pages": [
    {
      "title": "Example page",
      "url": "https://www.notion.so/example",
      "focus": "Replace with what the report should pull from this page."
    }
  ]
}
```

## Snapshot files written during refresh

GitHub and Linear come from `mise run fetch`:

- `data/github_issues_closed.json`
- `data/github_issues_created.json`
- `data/github_prs_created.json`
- `data/github_prs_merged.json`
- `data/github_repos.json`
- `data/linear_issues_updated.json`
- `data/linear_projects_month.json`
- `data/linear_teams.json`
- `data/linear_team_dumps/*.json`

Slack and Notion are connector-backed local snapshots:

- `data/slack_channels.json`
- `data/notion_pages.json`

Datadog activity is a local evidence snapshot:

- `data/datadog_activity.json`

The refresh receipt is a local evidence snapshot:

- `data/refresh_manifest.json`

The personal report narrative is a local evidence-backed snapshot:

- `data/personal_report.json`

Keep Datadog scoped to the report mode. For a personal report, use it as
evidence for Chad's workstreams. For an org report, it can cover broader
dashboards, incidents, monitors, or operational activity.

## Snapshot schemas

`data/slack_channels.json` is a JSON list of objects with:

- `channel`: Slack channel name including `#`
- `theme`: one-sentence topline
- `details`: list of one or two concrete supporting details
- `url`: optional Slack channel or message URL

Example:

```json
[
  {
    "channel": "#example-channel",
    "theme": "This channel surfaced delivery work in Slack.",
    "details": [
      "The channel carried issue, PR, and deployment updates.",
      "A visible thread called out a concrete implementation detail."
    ],
    "url": "https://app.slack.com/client/T123/C456"
  }
]
```

`data/notion_pages.json` is a JSON list of objects with:

- `title`: page title
- `date`: short report-facing date label like `May 11`
- `kind`: short document type label
- `url`: page URL
- `summary`: short summary grounded in the current page contents

Example:

```json
[
  {
    "title": "Example page",
    "date": "May 11",
    "kind": "program hub",
    "url": "https://www.notion.so/example",
    "summary": "This is a working delivery page with current rollout state."
  }
]
```

`data/datadog_activity.json` is a JSON object. The current personal report
expects a curated object, not a raw array of org events. Keep it small and
evidence-oriented unless the org report explicitly needs a broader Datadog
digest.

`data/refresh_manifest.json` is a JSON object with:

- `window`: exact ISO `start`, `end`, and IANA `timezone` values
- `refreshed_at`: ISO timestamp for the completed evidence pass
- `sources`: receipts for `github`, `linear`, `slack`, `notion`, and `datadog`

Each receipt has a `status` of `refreshed`. Use `confirmed_current` only when
the user explicitly approved preserved cache. A short `detail` may describe the
query, source count, or discovery coverage.

Example:

```json
{
  "window": {
    "start": "2026-07-03",
    "end": "2026-07-09",
    "timezone": "America/Chicago"
  },
  "refreshed_at": "2026-07-09T18:15:11-05:00",
  "sources": {
    "github": { "status": "refreshed" },
    "linear": { "status": "refreshed" },
    "slack": { "status": "refreshed" },
    "notion": { "status": "refreshed" },
    "datadog": { "status": "refreshed" }
  }
}
```

`data/personal_report.json` is a JSON object with:

- `window`: object with exact ISO `start` and `end` dates
- `lede`: current window summary
- `discussion`: one decision or discussion callout with evidence links
- `workstreams`: current personal bodies of work with proof and evidence links
- `lowlights`: current risks or unfinished edges
- `methodology`: notes that state the window, scope, refresh, and discovery
  coverage

Write this snapshot after GitHub, Linear, Slack, Notion, and Datadog are
current. Do not copy the prior report narrative forward as a starting point.

Example window field:

```json
{
  "window": {
    "start": "2026-07-03",
    "end": "2026-07-09"
  }
}
```

The renderer rejects the narrative when those values do not equal `WINDOW_START`
and `WINDOW_END`. This prevents a stale narrative from becoming current merely
because its file was touched or the renderer was rerun.

## Verification rules

- Run `mise run bootstrap-tracked-sources` before giving up on a missing
  `tracked_sources.json`.
- Run `mise run clear-cache` before a rerun unless the user explicitly asked to
  keep or use cache.
- Run `mise run report` after updating any snapshot file.
- `mise run report` must create the home page, drill-down pages, summary JSON,
  and `dist/chad-weekly-activity-report-single-page.pdf`.
- Run `mise run verify-report` after every report build with the same
  `REPORT_DATE` and `REPORT_TIMEZONE` used for the fetch.
- Ensure the local report server is serving the rebuilt report on
  `http://127.0.0.1:8765/` after `mise run report`.
- Reuse the existing server when it already serves this runtime. Restart it only
  when the port is stale or pointed at the wrong runtime.
- Open `http://127.0.0.1:8765/` in the in-app browser after the server check and
  confirm the rebuilt report actually rendered.
- Run `mise run check` if you changed code, tests, or docs.
- `data/slack_channels.json` is required. If it is missing or invalid, the
  report must fail and tell the user to run `$reporting-work-activity`.
- `data/notion_pages.json` is required. If it is missing or invalid, the report
  must fail and tell the user to run `$reporting-work-activity`.
- `data/datadog_activity.json` is required when `report_config.py` lists it in
  `REQUIRED_DATA_FILES`. If it is missing or invalid, refresh or rebuild the
  scoped Datadog evidence before reporting the output as complete.
- `data/refresh_manifest.json` is required. Every source receipt and its exact
  window must pass before the renderer accepts the report.
- `data/personal_report.json` is required for personal reports. If it is missing
  or invalid, rebuild the conclusions from the current evidence instead of
  falling back to hard-coded prose.
- `verify-report` must confirm required inputs and outputs, exact summary and
  narrative windows, snapshot-to-summary narrative equality, current narrative
  text in `index.html`, one title and main landmark per page, unique IDs, and
  resolvable local links.
- `verify-report` must also confirm that the PDF is readable, contains current
  report text, and has exactly one page.
- Render the PDF to PNG with `pdftoppm` and inspect the complete page for
  clipping, overlap, gray blocks, missing backgrounds, and unreadable tables.
- A successful HTTP response proves only that the server is reachable. Confirm
  that it serves the newly built report, then inspect desktop and mobile output
  in the in-app browser.
- Leave `muted_slack_channels.json` untouched unless the user explicitly asks to
  change muted channels.
