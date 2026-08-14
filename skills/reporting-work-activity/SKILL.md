---
name: reporting-work-activity
description:
  Builds, refreshes, or visually redesigns the bundled Convergint activity
  report runtime under `assets/activity-report-runtime`. Locks an explicit
  current reporting window, refreshes GitHub, Linear, Slack, Notion, and
  Datadog evidence, rebuilds the snapshot-backed narrative, verifies the
  generated HTML and required one-page PDF, and serves it locally. Use for
  weekly activity reports, personal or organization scope, stale report data,
  a new UI, a redesign, a retheme, a coat of paint, or requests for a
  distinctly different look.
---

# Activity Report Refresh

Refresh the bundled report runtime in `assets/activity-report-runtime`. Use the
local tools there for GitHub and Linear, then fill the Slack and Notion gaps
with Codex connectors and write the resulting snapshots under `data/`.

Do not request or run peer review for this workflow, including through the
`reviewing-complex-work` skill.

## Scope first

Decide the report scope before refreshing or rewriting conclusions.

- Personal report: use this when the user says "me", "my activity", "just me",
  "about me", "make me look good", or corrects an org-wide report as too broad.
  Read `references/personal-vs-org-reports.md` before changing content.
- Full org report: use this only when the user asks for Convergint,
  organization, team, workspace, department, or broad weekly activity.
- If the wording is ambiguous, ask a short scope question before doing connector
  work. Do not default from a prior run.

For personal reports, GitHub and Linear should be filtered to Chad's own
activity first. Slack, Notion, and Datadog should support the story instead of
becoming broad digest sections.

## Lock the reporting window

Resolve the window before clearing cache, fetching data, or reading connector
evidence.

1. Run `date '+%Y-%m-%d %H:%M:%S %Z'`. Do not infer today's date from model
   knowledge or from the previous report.
2. For "my weekly report," "last week's work activity," or another request for
   the latest report, default to the rolling seven days ending today in the
   user's local timezone. Use a previous Monday-through-Sunday week only when
   the user explicitly asks for the previous calendar week.
3. Set one explicit date and timezone for the entire run:

   ```bash
   export REPORT_DATE="$(date +%F)"
   export REPORT_TIMEZONE="America/Chicago"
   ```

4. State the exact inclusive window in a progress update before fetching. The
   runtime derives the start as six days before `REPORT_DATE`.
5. Use the same exported values for `mise run fetch`, `mise run report`, and
   `mise run verify-report`. Never silently repin the report to a prior Sunday.

For APIs with timestamp filters, translate the inclusive local-date window to
`start <= timestamp < day_after_end`. Slack searches should use the equivalent
exact `after:` and `before:` dates.

## Quick start

Copy this checklist and track progress:

```text
Activity report refresh progress:
- [ ] Confirm the bundled runtime path and current local state
- [ ] Decide and record scope: personal report or full org report
- [ ] Look up today's local date and state the exact report window
- [ ] Export one `REPORT_DATE` and `REPORT_TIMEZONE` for the whole run
- [ ] If redesigning, capture the baseline and write a named design brief
- [ ] Seed `tracked_sources.json` if it is missing
- [ ] Clear generated cache unless the user explicitly wants to keep it
- [ ] Run `mise run fetch`
- [ ] Refresh seed Slack and Notion sources
- [ ] Run the bounded discovery pass for Slack and Notion
- [ ] Write `data/slack_channels.json`
- [ ] Write `data/notion_pages.json`
- [ ] Confirm any required Datadog snapshot matches the selected scope
- [ ] Write `data/refresh_manifest.json` with a receipt for every source
- [ ] Write `data/personal_report.json` from the refreshed evidence
- [ ] Run `mise run report` to build HTML and the required one-page PDF
- [ ] Run `mise run verify-report`
- [ ] Ensure the local report server is serving the rebuilt report
- [ ] Inspect the served report at desktop and mobile sizes
- [ ] Render the PDF to PNG and inspect the complete single page
- [ ] Run `mise run check` if code or docs changed
- [ ] Verify the report uses current snapshot-backed evidence and narrative
```

## Default workflow

1. Start in this skill directory and work directly in the bundled runtime at
   `assets/activity-report-runtime`. Do not search the wider home directory for
   the runtime unless the user explicitly points you at another clone.
2. Read `README.md`, `report_config.py`, and `report_sources.py`. Read
   `references/personal-vs-org-reports.md` when the request asks for a personal
   report, when the user contrasts personal and org coverage, or when you need
   to export a single-page PDF. Read `references/visual-design-contract.md`
   whenever the user asks for a new UI, redesign, retheme, coat of paint, or a
   distinctly different look. Read `references/runtime-contract.md` when you
   need the exact date, snapshot, tracked source, or verification contract.
3. Decide whether this run is personal or org-wide before refreshing data.
4. Lock and announce the exact reporting window as described above. Keep the
   same `REPORT_DATE` and `REPORT_TIMEZONE` in the environment for every task.
5. If this is a redesign, complete the baseline audit and design brief before
   changing markup, CSS, or assets. The evidence refresh still happens in the
   same run unless the user explicitly asks for a visual-only prototype.
6. If `tracked_sources.json` is missing, run
   `mise run bootstrap-tracked-sources` before doing anything else. That task
   can seed the config from local snapshots or `dist/summary.json`.
7. Only if the bootstrap task says there were no usable local artifacts should
   you stop and tell the user to copy `tracked_sources.template.json` to
   `tracked_sources.json`, then fill in their private Slack channels and Notion
   pages.
8. Unless the user explicitly asked to use cache or not clear it, run
   `mise run clear-cache` before the refresh.
9. Treat cache as the generated report state:
   - clear `data/*.json`
   - clear `data/linear_team_dumps/*.json`
   - clear `dist/*`
   - preserve `tracked_sources.json` and `muted_slack_channels.json`
10. Run `mise run fetch`. Fix that step before touching Slack or Notion if
    GitHub or Linear refresh fails.
11. Treat `tracked_sources.json` as a seed list, not a hard cap. Start with
    those Slack channels and Notion pages so the refresh has a reliable
    backbone.
12. Refresh seeded Slack and Notion sources with exact window filters. A file's
    modification time is not proof that its contents match the window.
13. Run the bounded discovery pass for both Slack and Notion on every refresh,
    even if the seeded sources looked healthy.
14. Refresh scoped Datadog evidence with the same timestamp bounds.
15. Use the prior `dist/summary.json` only as a schema/bootstrap aid. Do not let
    it anchor the weekly conclusions or copy its prose into the new report.
16. If discovery finds a durable source, append it to the local
    `tracked_sources.json` before finishing.
17. Write `data/refresh_manifest.json` after every evidence pass. Its exact
    window, timezone, refresh timestamp, and GitHub, Linear, Slack, Notion, and
    Datadog receipts are required. Use `confirmed_current` only when the user
    explicitly approved preserved cache.
18. For a personal report, write `data/personal_report.json` only after every
    evidence pass is complete. Rebuild the lede, discussion, workstreams,
    lowlights, and methodology from the current window.
19. Run `mise run report`. That task must generate the HTML, drill-downs, and
    `dist/chad-weekly-activity-report-single-page.pdf`. Then run
    `mise run verify-report`. Fix every verifier failure before serving or
    describing the report as current.
20. Ensure the local report server is serving the rebuilt report:
    - prefer reusing the existing server if port `8765` is already serving this
      runtime
    - otherwise run `mise run serve`
    - if another process is holding the port for a stale runtime, stop it and
      restart `mise run serve`
21. Open `http://127.0.0.1:8765/` in the in-app browser and verify the rebuilt
    report actually loaded at desktop and mobile sizes:
    - confirm the page title and summary load
    - confirm the selected personal or org layout renders
    - confirm there is no missing-snapshot or stale-fallback messaging
    - for redesigns, compare it with the baseline against the distinctness gate
      in `references/visual-design-contract.md`
22. Render the PDF with `pdftoppm`, inspect the resulting PNG, and confirm with
    `pdfinfo` or `pypdf` that it has exactly one page. Check for clipping,
    overlap, gray blocks, missing backgrounds, and unreadable tables.
23. Run `mise run check` if you changed code, tests, or docs.
24. Tell the user the exact window, scope, verification result, local URL, PDF
    path, and whether visual inspection was completed. If browser inspection was
    not available, name that gap instead of claiming visual QA.

## Freshness and synthesis gate

The report is current only when all of these are true:

- The same explicit window drove every local fetch, connector query, summary,
  and verification command.
- GitHub and Linear records are filtered by record timestamps, not snapshot
  modification times.
- Slack search terms use the exact window. Retrieved messages outside it may
  explain background but cannot be presented as current activity.
- Notion's page body, last-edited time, and any "as of" date are checked. Older
  pages may provide context but cannot anchor a current-week conclusion.
- Datadog queries use the same bounds and selected personal or org scope.
- Every statement in the hero, discussion callout, workstreams, lowlights, and
  methodology was synthesized after the fresh evidence pass.
- `mise run verify-report` passes against the selected window.
- The refresh manifest records a current receipt for every evidence source.

Do not treat a recent snapshot file timestamp, successful renderer exit, or HTTP
200 response as proof that the research itself is current.

## Redesign mode

When the user asks for a new UI, redesign, retheme, coat of paint, or says they
are bored with the look, read `references/visual-design-contract.md` and apply
its full workflow.

The non-negotiable rules are:

- Capture the existing visual fingerprint before editing.
- Choose a named visual concept and record how it changes palette, typography,
  spatial structure, component silhouette, and texture or motion.
- Make the new report materially different in at least four of those five
  dimensions. A color swap or added gradient does not pass.
- Replace obsolete markup and CSS. Do not append a second redesign stylesheet
  that relies on overriding the old interface.
- Use one shared design system across the main report and every drill-down.
- Update export-only CSS so the one-page PDF carries the same new system.
- Preserve evidence links, mute controls, accessible semantics, focus states,
  reduced-motion behavior, and responsive tables.
- Generate bitmap artwork only when it supports the named concept. Remove unused
  generated assets and the code that creates them.
- Inspect both desktop and mobile renders. Static checks are a fallback, not a
  substitute for visual inspection.

## Discovery Pass

Run this on every refresh after the seeded source pull.

1. Build 6-12 search terms from the current week.
2. Always include:
   - the top GitHub repo names from this week's data, without the org prefix
   - the identifiers of the "interesting" Linear issues
   - 2-4 nouns or program names taken from the top Linear and GitHub titles
   - 1-2 focus phrases from the seeded Slack or Notion source list
3. Search Slack for the current report window using those terms. Start narrow,
   then widen only if the first pass is too thin.
4. Search Notion with the same term set plus any titles or doc names that
   surfaced in Slack.
5. Add a newly discovered Slack channel or Notion page to this run's snapshot
   when at least one of these is true:
   - it carries a distinct workstream the seeded sources missed
   - it is repeatedly referenced across multiple search hits
   - it is directly linked from an important Slack thread or Notion page
   - it clearly explains one of the week's top GitHub or Linear stories
6. Stop the discovery pass after two consecutive query rounds fail to add a
   meaningful new source.
7. If a newly discovered source looks durable, append it to the local
   `tracked_sources.json` before you finish the refresh.

## Working example

Typical request:

> Refresh the Convergint activity report and make sure Slack and Notion are
> current.

Default execution:

- Work directly in `assets/activity-report-runtime`.
- If needed, run `mise run bootstrap-tracked-sources`.
- Unless the user explicitly asked to keep cache, run `mise run clear-cache`.
- Run `mise run fetch`.
- Load the private tracked source config from `tracked_sources.json`.
- Refresh the seeded Slack channels and Notion pages first.
- Run the bounded discovery pass and include newly relevant Slack channels or
  Notion pages that it surfaces.
- Write `data/slack_channels.json`. `data/notion_pages.json`.
- Write `data/refresh_manifest.json` with every source receipt.
- Write `data/personal_report.json` after all evidence is current.
- Run `mise run report` to build HTML and the required one-page PDF.
- Run `mise run verify-report` with the same date environment.
- Make sure `mise run serve` is exposing the rebuilt report on
  `http://127.0.0.1:8765/`.
- Open `http://127.0.0.1:8765/` in the in-app browser and verify the rebuilt
  page is what the server is actually serving.
- Render the PDF to PNG, visually inspect it, and confirm it has one page.
- If you updated any code or prose, run `mise run check`.
- Tell the user that Slack and Notion were refreshed from current connector
  pulls as part of the run.

## Gotchas

- "My weekly report" means personal by default. Do not answer that with
  workspace-wide counts or org-level digest sections.
- Personal reports should tell the story of Chad's major bodies of work. Use raw
  counts as evidence, not as the main structure.
- Personal reports may cite PRs not authored by Chad only when they explain
  Chad's workstream, support, or decision-making.
- If a project is demo-worthy or should be discussed this week, make it visually
  visible in the report and link the direct evidence.
- `mise run fetch` only owns GitHub and Linear. It does not refresh Slack or
  Notion.
- `mise run bootstrap-tracked-sources` is the first recovery path when
  `tracked_sources.json` is missing. It can usually recover from local snapshots
  or an older `dist/summary.json`.
- `mise run clear-cache` is the default at the start of a rerun unless the user
  explicitly asked to keep or use cache.
- `tracked_sources.json` is private local config. `report_sources.py` validates
  and loads it, but the actual tracked entries are not checked in.
- The seeded source list is a starting point, not proof that only those channels
  or pages matter this week.
- The bounded discovery pass is required every run. Do not skip it just because
  the seeded refresh looked strong.
- `muted_slack_channels.json` is shared repo state. Do not clear or rewrite it
  during a refresh.
- The skill is not done after writing `dist/`. It should leave the local report
  reachable on `http://127.0.0.1:8765/`.
- The skill is also not done after starting the server. Open the served URL in
  the in-app browser and verify the page that actually renders. For a redesign,
  inspect desktop and mobile layouts against the saved design brief.
- `data/slack_channels.json` and `data/notion_pages.json` are required local
  snapshots for a real report build. Do not run `mise run report` until both
  files were refreshed in the current run or explicitly confirmed current by the
  user.
- If the runtime requires `data/datadog_activity.json`, keep that snapshot
  scoped to the selected report mode. For a personal report, Datadog should be
  evidence for Chad's work, not a feed of all org events.
- `data/personal_report.json` is required for personal reports. The renderer
  should fail when it is missing, since a stale narrative is worse than a
  missing report.
- `data/refresh_manifest.json` is required. The renderer and verifier reject a
  missing source receipt or a window that differs from the selected report.
- `mise run verify-report` is the artifact gate. Run it after every report build
  using the same `REPORT_DATE` and `REPORT_TIMEZONE` as the fetch.
- Every report includes `dist/chad-weekly-activity-report-single-page.pdf`. Do
  not treat the run as complete until the PDF is exactly one page and its
  rendered PNG is clean.
- A new stylesheet appended after the old stylesheet is not a redesign. Remove
  superseded rules and assets so the generator has one intentional UI.
- Single-page PDF export needs export-specific browser CSS. Read
  `references/personal-vs-org-reports.md` before generating or fixing a one-page
  PDF.
- Do not describe Slack coverage as workspace-wide unless you actually performed
  broad workspace searches beyond the seeded channels.
- Do not reuse the old summary as content. It is only there to help recover the
  private source list and remind you of the expected JSON shape.

## Failure handling

- Say exactly which connector read failed or which tracked source was
  inaccessible.
- If the private tracked source config is missing or invalid, point the user to
  `mise run bootstrap-tracked-sources` first, then
  `tracked_sources.template.json` only if the bootstrap task had no usable local
  artifacts.
- If the seeded source list refreshed cleanly but the discovery pass was
  blocked, say that explicitly instead of implying the seeded list was
  exhaustive.
- Say explicitly when you preserved cache because the user asked for it.
- Keep summaries grounded in the retrieved Slack messages and Notion pages. Do
  not invent missing coverage.
- Preserve Chad's voice if you materially rewrite report copy.
