---
name: briefing-engineering-leadership
description:
  Creates a manager-facing weekly engineering outcomes brief as a one-page PDF
  after a research-informed interview. Use when Chad asks for an outcomes
  brief, leadership brief, executive summary report, or update for his boss
  covering his personal impact, his team's outcomes, and engineering-wide
  signals. Do not use for weekly activity reports, activity digests,
  source-by-source summaries, organization-wide week-in-review reports, or
  requests to summarize supplied text without creating a report.
---

# Engineering leadership brief

Do not request or run peer review for this workflow, including through the
`reviewing-complex-work` skill.

Use the `writing-in-my-voice` skill for Chad's prose and the `pdf:pdf` skill for
PDF creation, rendering, and verification.

A request to build an executive summary report means producing the PDF, even
when it follows an activity report. Do not substitute an inline text summary.
Reuse relevant research already gathered for the same reporting window, then
fill gaps in team outcomes, attribution, and engineering-wide context.

1. Lock the requested reporting window.
2. Research relevant GitHub, Linear, Slack, Notion, and Datadog activity for
   that window. Identify evidence-backed candidates for:
   - what Chad personally accomplished and why it matters
   - what his team accomplished and why it matters
   - topics, trends, or highlights worth surfacing from across engineering
3. After the research, ask Chad up to six concise questions in one batch. Base
   every question on observed activity and use it to resolve a meaningful gap in
   attribution, impact, significance, or sensitivity. Do not ask for facts the
   research already established.
4. Stop and wait for Chad's answers. Do not draft, format, or render the report
   before he responds or explicitly declines to answer.
   - Treat his answers as authoritative context for his role, impact, and
     editorial priorities. Omit topics he rejects and resolved issues he says
     aren't worth surfacing. Don't carry stale risks into the final brief.
   - If he asks for replacement topics, research and propose specific
     alternatives. Ask only about meaningful remaining gaps; don't restart the
     interview or force an unrelated story into the brief.
5. Select and attribute the stories before writing:
   - Put each story in the single section where it best belongs. Do not repeat
     one outcome in both Chad's outcomes and an engineering signal.
   - Credit the project leader and implementers by name. Distinguish Chad's role
     precisely, such as leading a cutover, steering a design, sponsoring work,
     or contributing implementation.
   - Explain the consequence of technical steering: choosing supported upstream
     capabilities, investing in a maintainable deployment path, or avoiding a
     one-off workaround. Credit an accepted upstream contribution to its
     contributor and distinguish acceptance from adopting the eventual release.
   - Use evidence-backed status language. Say work is complete when it is
     complete, and do not soften it to "moved forward." Do not imply completion
     when material work remains.
   - Distinguish pre-release failures from disruption to application teams.
     Checks can correctly stop a release while the process still needs work to
     become easier to maintain. State verified impact without inventing an
     incident. Keep shipped checks separate from draft simplification work.
   - Separate this week's announcements from earlier implementation or adoption.
     Application feedback shaping a shared platform capability can be an
     engineering signal without claiming the earlier delivery happened now.
   - Organize around outcomes rather than tools or activity counts. State why
     each included item matters.
   - Do not add a "no decision needed" or similar filler callout. If there is no
     request for leadership, omit the callout entirely.
6. Write the brief in exactly three sections: My outcomes, Team outcomes, and
   Engineering signals. Do not prefix these headings with numbers such as 01,
   02, or 03.
   - Include a compact "By the numbers" strip above the three sections by
     default. Select three or four interesting, evidence-backed statistics for
     Chad and/or his team. Keep the stories organized around outcomes.
   - Label scope clearly: Chad-authored merged PRs, examples shipped, duplicate
     checks retired, or team contributions accepted upstream. Avoid presenting
     team totals as Chad's personal work or activity counts as measured impact.
   - Apply the reporting window's timezone boundaries and record a snapshot
     cutoff for a partial week. Note when merged PRs include work opened before
     the week. An issue's current completed state is not proof it completed
     during the window; require transition evidence for completion counts.
7. Link the strongest available context directly from each relevant story or
   headline:
   - Add visible inline hyperlinks throughout the body, not only on headings or
     in the footer. Link meaningful phrases to the specific implementation,
     examples, draft PRs, capability guides, contributions, or follow-up work
     they describe. Use a restrained link color and underline for
     discoverability.
   - Prefer durable, audience-accessible sources such as pull requests, current
     capability documentation, announcements, demos, live prototypes, and
     dashboards.
   - Link a Slack or Teams conversation when the conversation itself is material
     and the intended reader can access it. Prefer a durable source when one
     covers the same evidence.
   - Keep a compact evidence footer with short, human-readable link labels.
     Verify that every PDF link annotation resolves to the intended URL.
8. Include representative iconic images by default to add personality and
   reinforce the work or attribution:
   - Give each major story a small work-specific icon or an accurate contributor
     portrait when one fits. Omit the visual only when it would mislead, add
     clutter, or compete with the one-page reading hierarchy.
   - Prefer the capability's actual Notion page icon when available, including
     the Static Sites icon. Fetch the page's icon metadata and download its
     source asset; refresh expiring file URLs when necessary.
   - Use real Slack profile pictures for named contributors. Resolve each
     person's identity before retrieving the photo. For a shared feedback or
     collaboration story, use overlapping circular portraits, such as Chad and
     Juan Pinilla, with a narrow page-colored border and clear face crops.
   - Never generate a person's likeness. If a verified portrait is unavailable,
     use an accurate user-provided or previously approved image, or a
     work-specific icon.
   - Use recognizable product icons for branded technologies. Prefer official
     assets or the product's maintained repository. Use the Datadog logo for a
     Datadog contribution story; preserve its colors and aspect ratio.
   - Use a construction emoji (🚧) for migration groundwork such as iQuote 1.0
     and a green checkbox emoji (✅) for release checks. Render native color
     emoji or use faithful emoji assets that survive PDF export; don't replace
     them with generic line drawings. Apply these choices when the matching
     story is present, without inserting those projects into unrelated weeks.
   - When Chad provides a prior brief, inspect it for visual continuity without
     copying its layout mechanically.
9. Apply these layout rules:
   - Produce a readable, letter-sized PDF of exactly one page. Remove
     lower-value content instead of shrinking or muting one item's typography.
   - Keep typography uniform across peer items, including dense maintenance or
     component-upgrade details.
   - Give summary boxes visible space below the introductory deck. Vertically
     center their primary bold text, and render each upper label in a darker
     shade of the box color instead of gray.
   - Align the left edge of each icon or portrait with the body copy below it.
     Vertically center single-line headings against their visual; keep wrapped
     headings naturally balanced.
   - Keep the evidence footer when omitting an empty leadership callout.
10. Render and inspect the final page. Verify exact pagination, spacing,
    typography, portrait crops, brand icons, alignment, and link annotations
    before delivering it. Check every expected inline link as well as the
    headline, statistics, and footer links. Wrapped linked phrases may create
    multiple annotations; verify their destinations and coverage, not just the
    annotation count. Confirm the three section headings have no number labels.
