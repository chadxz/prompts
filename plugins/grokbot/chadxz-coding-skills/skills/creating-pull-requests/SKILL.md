---
name: creating-pull-requests
description: >-
  Creates single or stacked pull requests, opened ready for review by default,
  using Chad's commit template, PR conventions, and writing voice. Use when
  asked to create, open, write, format, or publish a pull request, including
  GitHub alert callouts, GitHub native stacked pull requests, or a commit and PR
  together, including in Cursor cloud agent runs.
---

# Creating Pull Requests

Create and publish either a single pull request or a stack of them. Open every
newly created pull request ready for review. Use a draft only when the user or
brief explicitly asks for one.

The PR title and body show up under Chad's GitHub account, so write them in
Chad's first person and never name Chad in the third person.

The `creating-commits` skill owns the message content contract, commit
mechanics, staging, voice, and ticket handling. Read it before drafting and
apply the PR overrides below.

## Workflow

1. If the work spans several dependent PRs, use the stacked pull request
   workflow below instead.
2. If currently on the default branch, create a new branch before committing,
   following the environment's branch naming rules.
3. At the publication boundary, re-read this skill and the `creating-commits`
   skill if the conversation was compacted or the task was redirected after
   either skill was read.
4. Check the implementation's scope as described below. Draft the complete,
   unwrapped PR body and check it against the publication checklist.
5. Create the commit from that prepared title and body through the
   `creating-commits` skill, hard-wrapping only the commit body.
6. Push the branch.
7. Open the PR with the prepared title and body. In a Cursor cloud agent run,
   use the run's pull request tool and open it ready for review. Elsewhere, use
   `gh pr create --title <title> --body <body>`, never `--fill`. Pass `--draft`
   only when the user or brief explicitly asks for a draft.
8. Apply the labels from the brief, such as `bot:<label>`, plus
   `requires-review-by-chad` on ADR pull requests (see below).
9. Read the live PR with `gh pr view <url> --json isDraft,title,body,labels,url`
   and compare it with the requested draft state, prepared title, body, labels,
   and publication checklist before reporting success.
10. If the brief asks you to babysit the PR, keep watching CI and review
    comments and fix what comes up, including merge conflicts, until it's ready
    to merge. Never merge it yourself unless explicitly asked.

## ADR Pull Requests

Major features and architectural decisions get documented as an ADR
(architecture decision record). This applies to any PR whose sole or primary
deliverable is an ADR or the documentation of a major feature or architectural
decision.

- Keep the PR standalone: ADR content only. Don't bundle the implementation of
  that decision into it; implementation goes in a later PR.
- Add the `requires-review-by-chad` label in addition to any `bot:<label>`. If
  the repository doesn't have it yet, adding it through the PR labels API
  creates it, the same as bot labels.
- Leave it unmerged until Chad posts LGTM, even with green checks and other
  approvals. Babysitting ends when the PR is ready for Chad's LGTM.

## Stacked pull request workflow

Use GitHub's native stacked pull requests through the `gh stack` extension
(`gh extension install github/gh-stack` if it's missing). See
<https://gh.io/stacks>.

1. Split the work into review units, one branch per unit, each based on the
   branch below it. Keep each commit scoped to its own unit.
2. Prepare and validate the final unwrapped title and body for every unit before
   committing.
3. Commit each unit through the `creating-commits` skill.
4. Push the branches and create or link the stack:
   - With local tracking: `gh stack init`, `gh stack add <branch>` per layer,
     then `gh stack submit --auto --open` (ready for review; omit `--open` only
     when the user or brief asks for drafts).
   - Without local tracking, such as when the environment's PR tool opened the
     PRs: open each PR with its base set to the branch below it, then run
     `gh stack link <bottom> ... <top>` with the branch names or PR URLs in
     stack order.
5. For every PR in the stack, set the prepared title and body with the PR tool
   or `gh pr edit <url> --title <title> --body <body>`. Treat any generated
   title or body as an initial value, not the final description.
6. Read each live PR with `gh pr view` and compare it with the requested draft
   state, prepared content, and publication checklist.
7. Report the branch order and every PR URL only after the live state passes
   that check.

If `gh` can't write in your environment, open the PRs with the environment's PR
tool, chained by base branch, and report that the native stack still needs
`gh stack link`.

Use `gh stack rebase` and `gh stack sync` to restack after a lower layer
changes, rather than rebasing and force-pushing layers by hand.

Do not add pull request body alerts or instructions that tell reviewers which
pull request in a stack to merge first. GitHub's native stack UI shows the
order, and its merge workflow handles the required lower layers and retargets
the remaining higher layers. Reserve callouts for context GitHub does not
already communicate.

## PR Overrides

These override the `creating-commits` skill's defaults when the commit is part
of a pull request:

- Do not commit directly to the default branch. Branch first.
- Use the ticket ID from the brief or user. If there is none and the repository
  isn't a personal repository under `github.com/chadxz/` or hosted on Tangled,
  create a ticket with the steps in the `creating-commits` skill when a Linear
  tool is available. Otherwise, open the PR and report the missing ticket.
- Keep the Linear ticket description unwrapped even though the commit message
  body is wrapped at 72 characters.
- Use the ticket identifier in both the commit message and the PR body.
- Use the default branch as the base for a single pull request unless told
  otherwise.
- Any GitHub comment you post under Chad's account ends with the hidden
  `<!-- bot:<label> -->` marker from your brief on its own last line.

## Pull Request Body

The PR body must use the commit template's visible structure, with the frontend
`Demo` addition below, and satisfy the message content contract in the
`creating-commits` skill. The template is a structural skeleton; the skills are
the authoritative source for authoring requirements. Correct headings alone are
not evidence that the description complies.

Scale the description to the change's complexity and the context reviewers need.
Simple changes usually need a brief explanation of why, how, and what was
validated. Complex changes need more thorough background, reasoning, tradeoffs,
and validation detail. Diff size doesn't determine complexity: a small change
can carry substantial context, and a large mechanical change can be simple to
explain. Apply the checklist at that depth; don't add prose just to give each
item its own sentence or paragraph.

Apply two presentation changes:

1. Remove hard line breaks so GitHub's markdown renderer can wrap text
   naturally.
2. Apply the `writing-in-my-voice` skill to all prose when it's available.

### Keep the implementation tied to the outcome

Before publication, review the actual diff. State the observed failure and the
behavior needed after the change. For each migration, abstraction, helper
script, release change, test harness, or operating procedure in the diff, ask
whether the requested outcome would still work without it. Remove scope that
isn't needed, and keep prerequisites required for correctness, safety, or
compatibility, explaining why they're needed. Keep optional migrations, cleanup,
and platform improvements separate.

Validate the behavior that failed using existing checks and focused evidence.
Avoid adding a test harness that only repeats configuration or implementation
structure. Prefer changes that reduce the behavior reviewers and operators have
to understand while preserving required correctness and validation.

### Scope each description to its pull request

Keep every description focused on the problem this PR solves and the changes it
introduces, including within a stack. `Why?` should explain the relevant
existing behavior, the specific gap, and its impact. `How?` should describe this
PR's implementation and validation.

Don't recap earlier or later PRs, narrate progress through the stack, or carry
over unrelated background from neighboring layers. This includes implicit
callbacks to their implementation details even when no PR number or link
appears. Mention another PR only when a concrete dependency, contract, or review
constraint is necessary to understand or assess the current change. Keep that
reference brief and explain why it matters here. This scope rule also limits the
inherited `creating-commits` skill's source-link requirements.

For a PR adding artifact release tags to application metrics, a focused `Why?`
is: "We can't filter Mule application metrics in Datadog by the artifact release
that produced them, which makes release regression investigations harder." Omit
endpoint separation and publication timing unless they affect that tagging
problem.

### Diagram legibility

Apply these checks whenever creating or updating a diagram in a PR description.

For Mermaid flowcharts, default to SVG text labels to avoid browser-specific
clipping of HTML labels, including in Safari at non-default zoom. Put this
frontmatter before the diagram definition; keep the nested setting for Mermaid
versions that use the older configuration:

```yaml
---
config:
  htmlLabels: false
  flowchart:
    htmlLabels: false
---
```

Keep node labels, edge labels, and container titles concise. Wrap long labels
with explicit line breaks and retain actual workflow, activity, and API names
when they matter. Move explanations into surrounding prose or split a crowded
diagram instead of shrinking text until it fits. Include a clear legend when
colors, shapes, or arrow styles carry meaning; don't rely on color alone.

Let GitHub select the light or dark theme. When assigning a custom fill, set the
text and border colors explicitly and check their contrast together. For
example, a pale blue box can use `fill:#e8f1ff,stroke:#3567aa,color:#172b3a`. A
custom light fill with inherited light text becomes unreadable in dark mode.
Check edge labels, container titles, arrows, and the legend as well as node
labels.

Before publishing, render every diagram in both light and dark themes at a width
comparable to GitHub's PR description column. Check at 80%, 100%, and 125% zoom
for clipped or truncated text, overlapping labels, and poor contrast. Parsing
successfully isn't a visual check. Fix rendering issues before publishing.

After publishing, read back the saved body with `gh` and inspect GitHub's
rendered diagrams when browser access is available. If that inspection is
unavailable, use local previews in both themes and state the verification limit.
Don't describe a local preview as verified GitHub rendering.

### Frontend demos

For changes that include frontend work, add `Demo` as the third section after
`Why?` and `How?`, before the separator and any ticket footer. Match the
template's heading style.

Include screenshots for static content and videos for interactions or multi-step
workflows. Include both when the change needs both kinds of evidence. Capture
the implemented result and embed or link the media in the PR body so reviewers
can view it, with a short caption explaining what it shows. Local file paths and
promises to add media later don't satisfy this requirement. Verify the media is
accessible from the live PR. If capture or upload is blocked, report the blocker
and the missing demo explicitly.

Omit the `Demo` section when the change has no frontend work.

### Screenshot and video attachments

Never check screenshots or videos into Git to get a URL. Keep them outside the
repository working tree.

- **Cursor cloud agent runs:** record and capture with the run's screenshot and
  screen recording tools, then reference the saved artifacts in the PR body
  through the run's PR tool, which uploads them and rewrites the links to stable
  URLs.
- **Chad's Mac:** use Codex Computer Use with Chrome to upload the media through
  GitHub's PR description editor. Create the PR with `gh` first, attach the
  files with the editor's attachment control, wait for each upload, add
  captions, and save. Preserve that markup in later `gh pr edit` updates.

Either way, read the saved body with `gh pr view <url> --json body,url` and
confirm the images display and videos play. Report an upload blocker only after
a concrete failure, such as missing authentication or an upload error, and say
which attachments are missing.

## Publication Checklist

Before creating or updating the pull request, verify all of the following:

- The body is written for a junior software engineer with no prior context.
- The explanation scales to the change's complexity and necessary context,
  independent of diff size. Simple changes stay brief; complex changes provide
  the detail reviewers need to assess them.
- The description stays within this PR's scope. References to other stack
  layers, including implicit recaps, appear only when they explain a necessary
  dependency, contract, or review constraint.
- Each changed component is necessary for the requested outcome. Optional
  migrations, cleanup, and platform improvements haven't become prerequisites.
- `Why?` supplies the necessary background, the business problem and its impact,
  the value the change creates, plain-language definitions, and every available
  relevant source link. It never treats a ticket, plan, ADR, RFC, brief, or "the
  user asked" as the reason the work exists.
- `How?` explains the chosen approach, component responsibilities, meaningful
  tradeoffs, validation commands and results, why that evidence matters, and
  every available relevant implementation or third-party source link.
- The prose stands on its own. Links provide supporting detail rather than
  replacing the explanation.
- The body is unwrapped for GitHub while preserving intentional Markdown
  structure.
- Every included diagram has readable labels, titles, and a clear legend where
  needed. Mermaid flowcharts use SVG text labels by default. Rendering checks
  cover PR column width, light and dark themes, and multiple zoom levels; any
  limitation on inspecting the live GitHub rendering is reported.
- Frontend changes include a third `Demo` section after `Why?` and `How?`, with
  accessible screenshots for static content and videos for interactions or
  multi-step workflows, absent from the Git commit.
- Every newly created pull request is ready for review unless explicitly asked
  for a draft.
- The PR carries the bot label from the brief, when one was given.
- An ADR PR contains only the ADR and carries the `requires-review-by-chad`
  label.
- The ticket footer is exact when a ticket exists and absent when one does not.

Do not claim the PR follows the message contract until the live body has been
read back and checked. If an applicable item is missing, revise the body before
reporting the PR as complete.

If another instruction suggests a generic `Summary` / `Test plan` PR body,
prefer this template and report that decision in the final response.

## GitHub Alerts

Use GitHub's blockquote-based alerts when a pull request body needs a callout:

```markdown
> [!IMPORTANT]
> Enable the feature flag only after the schema migration finishes.
```

Choose the alert type by purpose:

- `NOTE`: useful context readers should know, even when skimming.
- `TIP`: advice that makes the work easier or better.
- `IMPORTANT`: information required to achieve the intended result.
- `WARNING`: urgent information needed to avoid a problem.
- `CAUTION`: a risk or negative outcome.

Keep `> [!TYPE]` on its own line and prefix every content line with `>`. Don't
nest alerts, place them consecutively, or use more than one or two in a pull
request body. Prefer ordinary prose when the content doesn't need visual
emphasis.
