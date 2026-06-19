# Activity report runtime contract

Use this file only when you need the exact local file contract for the
runtime workspace bundled with this skill under
`assets/activity-report-runtime`.

## Contents

- Repo files to read first
- Snapshot files written during refresh
- Snapshot schemas
- Verification rules

## Repo files to read first

- `README.md`: local operator workflow
- `report_config.py`: reporting window, data paths, and output paths
- `report_sources.py`: loader and validator for the private tracked
  source config
- `generate_report.py`: snapshot loading and report rendering behavior

## Tracked source config

Slack and Notion refreshes are driven by a private local config file:

- `tracked_sources.json`

That file is ignored. Copy the checked-in
`tracked_sources.template.json`
to `tracked_sources.json` and fill in your private tracked sources
before using the skill only if the bootstrap task cannot seed it.

Important interpretation:

- `tracked_sources.json` is a seed list for the refresh
- it is not a guarantee that only those channels or pages matter this
  week
- the skill must run a bounded discovery pass every refresh
- the skill should widen beyond that seed list when the current week
  points to new relevant sources

Bootstrap path:

- run `mise run bootstrap-tracked-sources`
- it first checks `data/slack_channels.json` and
  `data/notion_pages.json`
- it falls back to `dist/summary.json` if the live snapshots are
  missing

Cache rule:

- on reruns, clear generated cache by default unless the user
  explicitly asked to keep or use cache
- cache means generated `data/*.json`,
  `data/linear_team_dumps/*.json`, and `dist/*`
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
- then do a bounded discovery pass and include newly important sources
  in the generated snapshots
- if a new source looks structurally useful for future runs, append it
  to `tracked_sources.json`

Discovery pass rule:

- derive search terms from the current week's top GitHub repos,
  interesting Linear issue identifiers, and notable nouns from current
  GitHub or Linear titles
- reuse titles and linked doc names surfaced during the Slack pass when
  searching Notion
- stop after two consecutive query rounds fail to add a meaningful new
  source

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

Keep Datadog scoped to the report mode. For a personal report, use it
as evidence for Chad's workstreams. For an org report, it can cover
broader dashboards, incidents, monitors, or operational activity.

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

`data/datadog_activity.json` is a JSON object. The current personal
report expects a curated object, not a raw array of org events. Keep it
small and evidence-oriented unless the org report explicitly needs a
broader Datadog digest.

## Verification rules

- Run `mise run bootstrap-tracked-sources` before giving up on a missing
  `tracked_sources.json`.
- Run `mise run clear-cache` before a rerun unless the user explicitly
  asked to keep or use cache.
- Run `mise run report` after updating any snapshot file.
- Ensure the local report server is serving the rebuilt report on
  `http://127.0.0.1:8765/` after `mise run report`.
- Reuse the existing server when it already serves this runtime. Restart
  it only when the port is stale or pointed at the wrong runtime.
- Open `http://127.0.0.1:8765/` in the in-app browser after the server
  check and confirm the rebuilt report actually rendered.
- Run `mise run check` if you changed code, tests, or docs.
- `data/slack_channels.json` is required. If it is missing or invalid,
  the report must fail and tell the user to run
  `$reporting-work-activity`.
- `data/notion_pages.json` is required. If it is missing or invalid,
  the report must fail and tell the user to run
  `$reporting-work-activity`.
- `data/datadog_activity.json` is required when `report_config.py`
  lists it in `REQUIRED_DATA_FILES`. If it is missing or invalid,
  refresh or rebuild the scoped Datadog evidence before reporting the
  output as complete.
- Leave `muted_slack_channels.json` untouched unless the user explicitly
  asks to change muted channels.
