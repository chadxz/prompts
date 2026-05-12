---
name: reporting-work-activity
description:
  Refreshes the bundled Convergint activity report runtime under
  `assets/activity-report-runtime` by running the local GitHub and
  Linear fetch, updating tracked Slack and Notion snapshots through
  Codex connectors, and regenerating the HTML report in `dist/`. Use
  when the user asks to refresh, rebuild, update, or regenerate the
  weekly activity report, especially when they want current Slack or
  Notion coverage in that report.
---

# Activity Report Refresh

Refresh the bundled report runtime in `assets/activity-report-runtime`.
Use the local tools there for GitHub and Linear, then fill the Slack
and Notion gaps with Codex connectors and write the resulting snapshots
under `data/`.

## Quick start

Copy this checklist and track progress:

```text
Activity report refresh progress:
- [ ] Confirm runtime path, current window, local source config, and local state
- [ ] Run `mise run fetch`
- [ ] Refresh `data/slack_channels.json`
- [ ] Refresh `data/notion_pages.json`
- [ ] Run `mise run report`
- [ ] Run `mise run check` if code or docs changed
- [ ] Verify the generated report is using snapshot-backed Slack and
      Notion data
```

## Default workflow

1. Work in the bundled runtime at `assets/activity-report-runtime`
   unless the user points you at another clone.
2. Read `README.md`, `report_config.py`, and `report_sources.py`.
   Read
   `references/runtime-contract.md`
   only when you need the exact snapshot schema, tracked source
   contract, or verification rules.
3. If `tracked_sources.json` is missing, stop before connector pulls
   and tell the user to copy `tracked_sources.template.json` to
   `tracked_sources.json`, then fill in their private Slack channels
   and Notion pages.
4. Run `mise run fetch`. Fix that step before touching Slack or Notion
   if GitHub or Linear refresh fails.
5. Refresh Slack from the tracked channels in the local
   `tracked_sources.json` loaded by `report_sources.py`. Default to
   tracked channel reads, not broad workspace search.
6. Refresh Notion from the tracked pages in the local
   `tracked_sources.json` loaded by `report_sources.py`.
7. Run `mise run report`.
8. Run `mise run check` if you changed code, tests, or docs.
9. Verify the generated page built from current Slack and Notion
   snapshots. Slack and Notion snapshot files are required for the
   report to build.

## Working example

Typical request:

> Refresh the Convergint activity report and make sure Slack and Notion
> are current.

Default execution:

- Run `mise run fetch`.
- Load the private tracked source config from `tracked_sources.json`.
- Refresh the tracked Slack channels and write
  `data/slack_channels.json`.
- Refresh the tracked Notion pages and write
  `data/notion_pages.json`.
- Run `mise run report`.
- If you updated any code or prose, run `mise run check`.
- Tell the user that Slack and Notion were refreshed from current
  connector pulls as part of the run.

## Gotchas

- `mise run fetch` only owns GitHub and Linear. It does not refresh
  Slack or Notion.
- `tracked_sources.json` is private local config. `report_sources.py`
  validates and loads it, but the actual tracked entries are not
  checked in.
- `muted_slack_channels.json` is shared repo state. Do not clear or
  rewrite it during a refresh.
- `data/slack_channels.json` and `data/notion_pages.json` are required
  local snapshots for a real report build. Do not run `mise run report`
  until both files were refreshed in the current run or explicitly
  confirmed current by the user.
- Do not describe Slack coverage as workspace-wide unless you actually
  performed broad workspace searches beyond the tracked channels.

## Failure handling

- Say exactly which connector read failed or which tracked source was
  inaccessible.
- If the private tracked source config is missing or invalid, point the
  user to `tracked_sources.template.json`.
- Keep summaries grounded in the retrieved Slack messages and Notion
  pages. Do not invent missing coverage.
- Preserve Chad's voice if you materially rewrite report copy.
