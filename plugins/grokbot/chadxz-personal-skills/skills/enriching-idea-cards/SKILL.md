---
name: enriching-idea-cards
description: >-
  Use when enriching, reviewing, or triaging cards in a Notion ideas or
  future-work database: adding architectural fit, platform impact, prior art and
  effort analysis, gathering evidence from teammates, or logging rejected ideas.
---

# Enriching idea cards

Adds decision-ready analysis to idea cards in a Notion ideas database without
reshaping the team's template.

## Rules

- Never change a card's Status (or other triage properties); only the owner
  does. To prioritize an idea, strengthen its content and evidence.
- Keep cards slim and focused on the details. No meta commentary: no "revised to
  match" notes, interpretation caveats, pointer lines to other sections,
  struck-through answered questions, or process narration. When the owner
  decides something, fold it into the content as fact and delete the answered
  question.
- Never reshape the existing card template. Don't edit, reorder or remove
  existing headings or content. Add exactly one new section at the very bottom
  of the card.
- Use progressive disclosure: a 2-3 sentence summary first, then the detail
  underneath, so a reader can stop after the summary.
- Don't invent facts about internal systems. When internal context is missing,
  list it under Open questions.
- Cite external sources with links.
- Use only the workspace and database the caller names.

## Steps

1. **Pick cards.** Query the database. Prioritize cards whose status is closest
   to execution (for example On Deck before Ideas), then cards most relevant to
   the team's current top priority. Skip cards that already have an analysis
   section unless new evidence has arrived since it was written.
2. **Read the card.** Read the full page, including the template sections (such
   as Description and Evidence) and any linked docs. Note related or duplicate
   cards.
3. **Research.** Search the web for prior art, published architecture designs
   and third-party options. Check the team's preferred vendor first (for example
   Datadog, if that's the observability standard), then alternatives.
4. **Write one section at the bottom**, titled
   `<Bot name> analysis (YYYY-MM-DD)`, with these parts:
   - **Summary**: 2-3 sentences covering the recommendation and the main risk.
   - **Architectural fit**: how it fits the existing platform, patterns and
     direction.
   - **Impact on the wider platform**: rate it **Good** or **Low**, and say why.
   - **Prior art and third-party options**: the preferred vendor first, then
     alternatives, each with pros, cons and links.
   - **Effort estimate**: a t-shirt size, with the assumptions and the risks
     that would make it bigger. Leave the card's own size property unchanged
     unless the caller says to update it.
   - **Open questions**: anything that needs internal confirmation.
5. **Re-enrich with new evidence.** When teammates send new evidence that a
   feature deserves more weight, add it to the card's existing Evidence section
   (or append a dated Evidence update to the analysis section if the template
   has no Evidence section). Credit the source and include links.
6. **Log rejections.** When an idea is rejected (status moves to Not Doing, or
   the owner rejects it), record the reason on the card in a dated
   `Rejected (YYYY-MM-DD)` note at the bottom, saying who decided and why. Keep
   the rejected-ideas log the caller names, if any, in sync.
7. **Report.** Return a short list: each card touched with its link, its impact
   rating and size, and anything the owner needs to decide.

## Gathering evidence from teammates

During a scheduled pass, ask the relevant teammate bots whether they've seen new
evidence (support requests, incidents, recurring workarounds, audit findings)
that should give any card more weight. Ask once, with priority, and add what
comes back on the next step 5.
