# Personal and org weekly reports

Use this reference when the user asks for a weekly activity report and
the scope could be either Chad's personal work or broader organization
activity.

## Scope decision

Choose a personal report when the prompt says:

- my activity
- me
- just me
- about me
- make me look good
- wrong report, I wanted just me

Choose an org report when the prompt asks for:

- Convergint-wide activity
- the whole organization
- a team or department digest
- workspace-wide highlights
- all GitHub, Linear, Slack, Notion, or Datadog activity

Ask a short clarification question when the prompt only says "weekly
activity report" and there is no prior scope in the thread. Do not
reuse a previous run's scope without checking the user's wording.

## Personal weekly report pattern

A personal report should make Chad's work legible. It should not read
like a workspace digest with Chad mentioned inside it.

Use these default filters:

- GitHub: PRs authored by `chadxz` first.
- Linear: issues assigned to Chad first.
- Slack: threads where Chad made a decision, answered a question,
  unblocked someone, coordinated work, or supplied evidence.
- Notion: pages or transcripts that explain work Chad shaped,
  discussed, planned, or turned into follow-up.
- Datadog: dashboards, incidents, logs, monitors, coverage, or
  observations that support Chad's workstreams.

Use non-Chad PRs or issues only when they explain a Chad workstream. For
example, an `it-monorepo` PR opened by another engineer can belong in a
personal report when Chad's Linear issue, Slack guidance, or support
thread explains why it mattered.

Structure the personal report around a small number of bodies of work,
not around tools. The user specifically preferred this pattern:

- CTC Financials as a platform-owned application path.
- Windows Server 2025 platform support for iQuote.
- IT and Infrastructure support, including Saviynt audit-log ingest and
  iCare private-link access.
- Platform runtime and agent tooling.
- Observability and data reliability.

For personal reports, avoid separate broad sections titled Slack,
GitHub, Notion, Linear, or Datadog unless the user asks for a ledger.
Put evidence links inside the relevant workstream cards instead.

The hero should make the scope obvious. Use copy like "Chad's week in
platform work" and include personal counts only after the story:

- PRs opened by Chad.
- Chad-assigned Linear issues moved to Done.
- Number of major bodies of work.
- Number of demo-worthy threads or discussion highlights.

## Org weekly report pattern

An org report can aggregate broader movement across teams, repos,
channels, and docs. It can use tool sections when they help the reader
scan organizational activity.

For org reports:

- Use broad GitHub and Linear snapshots instead of personal filters.
- Use Slack and Notion discovery to find team-level themes.
- Include lowlights, risks, and stuck work with enough detail for
  leadership or team leads to act.
- Do not write "Chad did" unless the evidence is about Chad.
- Do not make the report flattering toward Chad unless the user asked
  for a personal report.

## Demo-worthy and discussion highlights

When the user says a project is "worthy of demo" or should be discussed
this week, make it visually obvious. Good treatments:

- a corner badge on the workstream card
- a highlighted "Demo angle" line inside the card
- a top-level "Discuss this week" callout for meetings or transcripts

Keep the treatment consistent. During the June 12 through June 18, 2026
personal report, these were marked demo-worthy:

- CTC Financials
- Windows Server 2025 platform support
- Saviynt audit-log Datadog ingest

The Sergio Botero Temporal pairing transcript was marked as "Discuss
this week" because it was a cross-team adoption thread. It linked to
the Notion transcript and the Saviynt reference PR.

## Single-page PDF export

The browser page and one-page PDF need different layout rules. Browser
CSS can use sticky nav, rotated ribbons, clipped overflow, and
scrollable tables. A static PDF should not.

When exporting a full report as a single PDF page:

1. Open the served report with Playwright.
2. Expand all `details` elements before export so the PDF is complete.
3. Inject export-only CSS rather than changing the interactive HTML.
4. Disable sticky positioning for navigation.
5. Embed the hero background as an actual image layer, not only as a
   CSS background, so PDF viewers do not suppress it.
6. Convert rotated corner ribbons into non-rotated corner badges.
7. Remove card shadows if the PDF viewer renders them as gray blocks.
8. Stack evidence tables and set `table-layout: fixed`.
9. Wrap table cells with `overflow-wrap: anywhere`.
10. Set the PDF height to the rendered document height so the output is
    exactly one page.

After export, verify:

- the PDF has exactly one page
- the hero image is visible
- demo badges do not overlap card text or leave gray artifacts
- evidence tables are not clipped
- there is no page-level horizontal overflow

Useful validation commands:

```bash
uv run --with pypdf python - <<'PY'
from pathlib import Path
from pypdf import PdfReader

path = Path("dist/chad-weekly-activity-report-single-page.pdf")
reader = PdfReader(path)
print(f"pages={len(reader.pages)}")
PY
```

```bash
pdftoppm -png -singlefile -r 90 \
  dist/chad-weekly-activity-report-single-page.pdf \
  dist/pdf-debug/single-page-check
```

Visually inspect the rendered PNG, not only the browser page. The PDF
can have viewer-specific artifacts that do not appear in Chromium's
normal screen rendering.
