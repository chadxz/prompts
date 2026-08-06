# Activity report visual design contract

Read this reference whenever the user asks for a new UI, redesign, retheme, coat
of paint, or a distinctly different look. The goal is a coherent new interface,
not a decorative layer over the previous one.

## Preserve the product contract

A redesign may change presentation and information architecture. It must keep:

- the selected personal or org scope
- the explicit report window
- evidence-backed narrative and metrics
- direct evidence and drill-down links
- Slack mute behavior when it is present
- the generated `summary.json` contract
- the required searchable, single-page PDF companion
- semantic navigation, headings, and main content
- keyboard access and visible focus states
- usable desktop and mobile layouts

Do not let visual work delay the evidence refresh unless the user explicitly
asks for a visual-only prototype.

## Audit the baseline first

Before editing markup, CSS, JavaScript, or assets:

1. Serve the existing report.
2. Capture one desktop view around 1440 by 1000 and one mobile view around 390
   by 844 with the in-app browser.
3. Open at least one drill-down page.
4. Record the baseline visual fingerprint:
   - palette and contrast mode
   - display and body typography
   - page and navigation structure
   - card, table, badge, and callout silhouettes
   - texture, illustration, and motion language
5. Note any layout, contrast, clipping, or interaction defects that the new
   design must remove.

If the in-app browser is unavailable, inspect the served HTML and source CSS,
record that screenshots could not be captured, and continue. Do not claim that
visual QA was completed.

## Write a named design brief

Choose a concept that fits the report's content and differs from the baseline.
Names such as "operations field journal," "editorial briefing," or "signal
console" are useful because they imply a system. "Modern" or "clean" is too
vague.

Record this compact brief before implementation:

```text
Concept:
Audience and reading mode:
Information hierarchy:
Palette change:
Typography change:
Spatial or navigation change:
Component silhouette change:
Texture or motion change:
Behaviors and evidence contracts preserved:
```

The concept is a decision tool. It should explain why the page looks the way it
does, not become marketing copy inside the report.

## Pass the distinctness gate

Compare the new design with the baseline across five dimensions:

1. Palette: hue family, contrast mode, surface system, and accent strategy.
2. Typography: type categories, scale, weight, density, and label treatment.
3. Spatial structure: navigation, grid, reading order, rhythm, and density.
4. Component silhouette: cards, sections, tables, badges, callouts, and edges.
5. Texture or motion: illustration, pattern, depth, transitions, and feedback.

The redesign must materially change at least four of the five dimensions. A
token rename, color substitution, new hero image, or extra gradient does not
count as a material change by itself.

The new design must also remain internally consistent. Every changed dimension
should support the named concept rather than becoming a collection of visual
effects.

## Replace instead of layering

Treat the generator as source code, not as a finished page to patch from the
outside.

- Replace superseded markup and CSS in the renderer.
- Remove old selectors, tokens, and media rules that no longer serve the UI.
- Keep one intentional visual system in each generated document.
- Do not append a second `<style>` block whose purpose is to override the old
  design.
- Do not leave dead render functions that still contain the prior narrative or
  interface when the active report no longer uses them.
- Do not generate an image, texture, or icon set that the final HTML does not
  reference.
- Reuse one token system and component language across the main page and every
  drill-down page.
- Update `export_single_page_pdf.py` when the new layout needs different export
  rules. The PDF must look like the same design, not a generic print fallback.

If a staged migration temporarily needs two style blocks, consolidate them
before reporting the redesign as complete.

## Required interaction and layout states

Verify all of these states, not only the top of the home page:

- desktop home page
- mobile home page
- sticky or compact navigation, if present
- expanded evidence details
- at least one long workstream title
- at least one long evidence URL or table cell
- empty or sparse evidence state
- every drill-down page type
- the complete rendered single-page PDF
- keyboard focus on links, buttons, and disclosures
- reduced-motion preference

Use real current report content for QA. Placeholder copy often hides the exact
wrapping and density failures that appear in the final report.

## Accessibility and resilience gate

The generated pages need:

- one descriptive `<title>`
- one `<main>` landmark
- a skip link that becomes visible on focus
- a logical heading hierarchy
- unique element IDs
- visible `:focus-visible` treatment
- controls with accessible names
- sufficient text and control contrast
- no information communicated only by color
- `prefers-reduced-motion` behavior for nonessential movement
- horizontal overflow contained to data tables, not the page
- layouts that remain usable at 320 CSS pixels wide

Prefer native HTML semantics. Add ARIA only when native elements cannot express
the interaction.

## Visual QA workflow

After `mise run report` and `mise run verify-report` pass:

1. Confirm the server is returning the newly generated file, not a stale runtime
   on the same port.
2. Reload the home page in the in-app browser.
3. Capture desktop and mobile screenshots using the same sizes as the baseline.
4. Compare them against the design brief and five-dimension gate.
5. Inspect for overflow, overlap, clipped text, unreadable contrast, unstable
   sticky elements, and excessive empty space.
6. Open every drill-down type and confirm the same design system is present.
7. Exercise disclosures, navigation, direct evidence links, and mute controls.
8. Repeat screenshots after fixes that affect layout or visual tokens.
9. Render the PDF to PNG and inspect it independently. Browser-screen success
   does not prove that PDF backgrounds, badges, tables, or long-page sizing are
   correct.

When browser control is unavailable, run the deterministic verifier, fetch all
served pages over HTTP, and inspect the generated HTML. Report the missing
screenshot pass as an explicit verification gap.

## Completion statement

When handing off a redesign, state:

- the named concept
- the exact reporting window and scope
- which four or five dimensions changed
- whether desktop and mobile visual QA passed
- whether all drill-down pages share the new system
- whether the PDF is one page and passed rendered-PNG inspection
- the result of `mise run verify-report` and `mise run check`

Do not describe the UI as entirely new unless it passed the distinctness gate.
