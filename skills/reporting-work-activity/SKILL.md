---
name: reporting-work-activity
description:
  Refreshes the bundled Convergint activity report runtime under
  `assets/activity-report-runtime` by running the local GitHub and
  Linear fetch, refreshing seed Slack and Notion sources through
  Codex connectors, running a bounded discovery pass every run, and
  regenerating the HTML report in `dist/`. Use when the user asks to
  refresh, rebuild, update, or regenerate the weekly activity report,
  especially when they want current Slack or Notion coverage in that
  report.
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
- [ ] Confirm the bundled runtime path and current local state
- [ ] Seed `tracked_sources.json` if it is missing
- [ ] Clear generated cache unless the user explicitly wants to keep it
- [ ] Run `mise run fetch`
- [ ] Refresh seed Slack and Notion sources
- [ ] Run the bounded discovery pass for Slack and Notion
- [ ] Write `data/slack_channels.json`
- [ ] Write `data/notion_pages.json`
- [ ] Run `mise run report`
- [ ] Ensure the local report server is serving the rebuilt report
- [ ] Open the served report in the in-app browser and verify it loads
- [ ] Run `mise run check` if code or docs changed
- [ ] Verify the generated report is using snapshot-backed Slack and
      Notion data
```

## Default workflow

1. Start in this skill directory and work directly in the bundled
   runtime at `assets/activity-report-runtime`. Do not search the wider
   home directory for the runtime unless the user explicitly points you
   at another clone.
2. Read `README.md`, `report_config.py`, and `report_sources.py`.
   Read
   `references/runtime-contract.md`
   only when you need the exact snapshot schema, tracked source
   contract, or verification rules.
3. If `tracked_sources.json` is missing, run
   `mise run bootstrap-tracked-sources` before doing anything else.
   That task can seed the config from local snapshots or
   `dist/summary.json`.
4. Only if the bootstrap task says there were no usable local
   artifacts should you stop and tell the user to copy
   `tracked_sources.template.json` to `tracked_sources.json`, then fill
   in their private Slack channels and Notion pages.
5. Unless the user explicitly asked to use cache or not clear it, run
   `mise run clear-cache` before the refresh.
6. Treat cache as the generated report state:
   - clear `data/*.json`
   - clear `data/linear_team_dumps/*.json`
   - clear `dist/*`
   - preserve `tracked_sources.json` and `muted_slack_channels.json`
7. Run `mise run fetch`. Fix that step before touching Slack or Notion
   if GitHub or Linear refresh fails.
8. Treat `tracked_sources.json` as a seed list, not a hard cap. Start
   with those Slack channels and Notion pages so the refresh has a
   reliable backbone.
9. Refresh Slack from the seeded channels first.
10. Refresh Notion from the seeded pages first.
11. Run the bounded discovery pass for both Slack and Notion on every
   refresh, even if the seeded sources looked healthy.
12. Use the prior `dist/summary.json` only as a schema/bootstrap aid.
   Do not let it anchor the actual weekly conclusions if the fresh
   connector reads say something different.
13. If the discovery pass surfaces a new channel or page that seems
   likely to matter again, append it to the local `tracked_sources.json`
   before you finish.
14. Run `mise run report`.
15. Ensure the local report server is serving the rebuilt report:
    - prefer reusing the existing server if port `8765` is already
      serving this runtime
    - otherwise run `mise run serve`
    - if another process is holding the port for a stale runtime, stop
      it and restart `mise run serve`
16. Tell the user the report is available at
    `http://127.0.0.1:8765/`.
17. Open `http://127.0.0.1:8765/` in the in-app browser and verify the
    rebuilt report actually loaded:
    - confirm the page title and summary load
    - confirm the Slack and Notion sections render
    - confirm there is no missing-snapshot or stale-fallback messaging
18. Run `mise run check` if you changed code, tests, or docs.
19. Verify the generated page built from current Slack and Notion
   snapshots. Slack and Notion snapshot files are required for the
   report to build.

## Discovery Pass

Run this on every refresh after the seeded source pull.

1. Build 6-12 search terms from the current week.
2. Always include:
   - the top GitHub repo names from this week's data, without the org
     prefix
   - the identifiers of the "interesting" Linear issues
   - 2-4 nouns or program names taken from the top Linear and GitHub
     titles
   - 1-2 focus phrases from the seeded Slack or Notion source list
3. Search Slack for the current report window using those terms. Start
   narrow, then widen only if the first pass is too thin.
4. Search Notion with the same term set plus any titles or doc names
   that surfaced in Slack.
5. Add a newly discovered Slack channel or Notion page to this run's
   snapshot when at least one of these is true:
   - it carries a distinct workstream the seeded sources missed
   - it is repeatedly referenced across multiple search hits
   - it is directly linked from an important Slack thread or Notion page
   - it clearly explains one of the week's top GitHub or Linear stories
6. Stop the discovery pass after two consecutive query rounds fail to
   add a meaningful new source.
7. If a newly discovered source looks durable, append it to the local
   `tracked_sources.json` before you finish the refresh.

## Working example

Typical request:

> Refresh the Convergint activity report and make sure Slack and Notion
> are current.

Default execution:

- Work directly in `assets/activity-report-runtime`.
- If needed, run `mise run bootstrap-tracked-sources`.
- Unless the user explicitly asked to keep cache, run
  `mise run clear-cache`.
- Run `mise run fetch`.
- Load the private tracked source config from `tracked_sources.json`.
- Refresh the seeded Slack channels and Notion pages first.
- Run the bounded discovery pass and include newly relevant Slack
  channels or Notion pages that it surfaces.
- Write
  `data/slack_channels.json`.
  `data/notion_pages.json`.
- Run `mise run report`.
- Make sure `mise run serve` is exposing the rebuilt report on
  `http://127.0.0.1:8765/`.
- Open `http://127.0.0.1:8765/` in the in-app browser and verify the
  rebuilt page is what the server is actually serving.
- If you updated any code or prose, run `mise run check`.
- Tell the user that Slack and Notion were refreshed from current
  connector pulls as part of the run.

## Gotchas

- `mise run fetch` only owns GitHub and Linear. It does not refresh
  Slack or Notion.
- `mise run bootstrap-tracked-sources` is the first recovery path when
  `tracked_sources.json` is missing. It can usually recover from local
  snapshots or an older `dist/summary.json`.
- `mise run clear-cache` is the default at the start of a rerun unless
  the user explicitly asked to keep or use cache.
- `tracked_sources.json` is private local config. `report_sources.py`
  validates and loads it, but the actual tracked entries are not
  checked in.
- The seeded source list is a starting point, not proof that only those
  channels or pages matter this week.
- The bounded discovery pass is required every run. Do not skip it just
  because the seeded refresh looked strong.
- `muted_slack_channels.json` is shared repo state. Do not clear or
  rewrite it during a refresh.
- The skill is not done after writing `dist/`. It should leave the
  local report reachable on `http://127.0.0.1:8765/`.
- The skill is also not done after starting the server. Open the served
  URL in the in-app browser and verify the page that actually renders.
- `data/slack_channels.json` and `data/notion_pages.json` are required
  local snapshots for a real report build. Do not run `mise run report`
  until both files were refreshed in the current run or explicitly
  confirmed current by the user.
- Do not describe Slack coverage as workspace-wide unless you actually
  performed broad workspace searches beyond the seeded channels.
- Do not reuse the old summary as content. It is only there to help
  recover the private source list and remind you of the expected JSON
  shape.

## Failure handling

- Say exactly which connector read failed or which tracked source was
  inaccessible.
- If the private tracked source config is missing or invalid, point the
  user to `mise run bootstrap-tracked-sources` first, then
  `tracked_sources.template.json` only if the bootstrap task had no
  usable local artifacts.
- If the seeded source list refreshed cleanly but the discovery pass was
  blocked, say that explicitly instead of implying the seeded list was
  exhaustive.
- Say explicitly when you preserved cache because the user asked for it.
- Keep summaries grounded in the retrieved Slack messages and Notion
  pages. Do not invent missing coverage.
- Preserve Chad's voice if you materially rewrite report copy.
