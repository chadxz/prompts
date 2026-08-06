# Personal and org weekly reports

Use this reference when the user asks for a weekly activity report and the scope
could be either Chad's personal work or broader organization activity.

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

Ask a short clarification question when the prompt only says "weekly activity
report" and there is no prior scope in the thread. Do not reuse a previous run's
scope without checking the user's wording.

## Personal weekly report pattern

A personal report should make Chad's work legible. It should not read like a
workspace digest with Chad mentioned inside it.

Use these default filters:

- GitHub: PRs authored by `chadxz` first.
- Linear: issues assigned to Chad first.
- Slack: threads where Chad made a decision, answered a question, unblocked
  someone, coordinated work, or supplied evidence.
- Notion: pages or transcripts that explain work Chad shaped, discussed,
  planned, or turned into follow-up.
- Datadog: dashboards, incidents, logs, monitors, coverage, or observations that
  support Chad's workstreams.

Use non-Chad PRs or issues only when they explain a Chad workstream. For
example, an `it-monorepo` PR opened by another engineer can belong in a personal
report when Chad's Linear issue, Slack guidance, or support thread explains why
it mattered.

Structure the personal report around a small number of bodies of work, not
around tools. Derive those bodies of work from the current window each time. Do
not preserve last week's workstream names as a template. A useful current
workstream connects a concrete outcome or decision to two or more pieces of
evidence, regardless of which source supplied them.

For personal reports, avoid separate broad sections titled Slack, GitHub,
Notion, Linear, or Datadog unless the user asks for a ledger. Put evidence links
inside the relevant workstream cards instead.

The hero should make the scope obvious. Use copy like "Chad's week in platform
work" and include personal counts only after the story:

- PRs opened by Chad.
- Chad-assigned Linear issues moved to a completed state.
- Number of major bodies of work.
- Number of demo-worthy threads or discussion highlights.

## Org weekly report pattern

An org report can aggregate broader movement across teams, repos, channels, and
docs. It can use tool sections when they help the reader scan organizational
activity.

For org reports:

- Use broad GitHub and Linear snapshots instead of personal filters.
- Use Slack and Notion discovery to find team-level themes.
- Include lowlights, risks, and stuck work with enough detail for leadership or
  team leads to act.
- Do not write "Chad did" unless the evidence is about Chad.
- Do not make the report flattering toward Chad unless the user asked for a
  personal report.

## Demo-worthy and discussion highlights

When the user says a project is "worthy of demo" or should be discussed this
week, make it visually obvious. Good treatments:

- a corner badge on the workstream card
- a highlighted "Demo angle" line inside the card
- a top-level "Discuss this week" callout for meetings or transcripts

Keep the treatment consistent, but do not carry demo-worthy projects forward as
a standing source list. Choose demo and discussion highlights again from the
current evidence on every run.

## Visual redesigns

Personal and org reports can use different information architectures, but a
redesign request still needs a coherent visual system across the home page and
drill-down pages. Read `visual-design-contract.md` before changing markup, CSS,
JavaScript, or generated assets. Preserve scope and evidence contracts while
passing its four-of-five distinctness gate.

## Required single-page PDF export

Every report includes `dist/chad-weekly-activity-report-single-page.pdf`.
`mise run report` builds it after the HTML, and `mise run pdf` re-exports an
unchanged HTML report. The browser page and one-page PDF need different layout
rules. Browser CSS can use sticky navigation, clipped overflow, and scrollable
tables. A static PDF should not.

When exporting a full report as a single PDF page:

`export_single_page_pdf.py` owns the export-only CSS and these behaviors:

1. Expand all `details` elements so the PDF is complete.
2. Disable fixed or sticky positioning.
3. Preserve backgrounds with browser print-color adjustment.
4. Convert any overlapping ribbon treatment into a safe badge.
5. Remove shadows when the PDF viewer renders them as gray blocks.
6. Set evidence tables to fixed layout and wrap long cells.
7. Set the PDF height to the rendered document height so the output is exactly
   one page.

Update that script alongside any redesign. Do not make the interactive HTML
worse merely to accommodate print output.

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
  tmp/pdfs/single-page-check
```

Visually inspect the rendered PNG, not only the browser page. The PDF can have
viewer-specific artifacts that do not appear in Chromium's normal screen
rendering. This inspection is required on every report run.
