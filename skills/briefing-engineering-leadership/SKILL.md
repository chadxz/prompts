---
name: briefing-engineering-leadership
description:
  Creates a manager-facing weekly engineering outcomes brief as a one-page PDF
  after a research-informed interview. Use when Chad asks for an outcomes
  brief, leadership brief, or update for his boss covering his personal impact,
  his team's outcomes, and engineering-wide signals. Do not use for weekly
  activity reports, activity digests, source-by-source summaries, or
  organization-wide week-in-review reports.
---

# Engineering leadership brief

Do not request or run peer review for this workflow, including through the
`reviewing-complex-work` skill.

Use the `writing-in-my-voice` skill for Chad's prose and the `pdf:pdf` skill for
PDF creation, rendering, and verification.

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
5. Select and attribute the stories before writing:
   - Put each story in the single section where it best belongs. Do not repeat
     one outcome in both Chad's outcomes and an engineering signal.
   - Credit the project leader and implementers by name. Distinguish Chad's role
     precisely, such as leading a cutover, steering a design, sponsoring work,
     or contributing implementation.
   - Use evidence-backed status language. Say work is complete when it is
     complete, and do not soften it to "moved forward." Do not imply completion
     when material work remains.
   - Organize around outcomes rather than tools or activity counts. State why
     each included item matters.
   - Do not add a "no decision needed" or similar filler callout. If there is no
     request for leadership, omit the callout entirely.
6. Write the brief in exactly three sections: My outcomes, Team outcomes, and
   Engineering signals.
7. Link the strongest available context directly from each relevant story or
   headline:
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
   - Use real portraits for named contributors when accurate images are
     available from user-provided or prior approved artifacts.
   - Never generate a person's likeness. Reuse an approved portrait or use a
     work-specific icon instead.
   - Use recognizable product icons for branded technologies. Prefer official
     assets or the product's maintained repository.
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
    before delivering it.
