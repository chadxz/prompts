---
name: creating-pull-requests
description:
  Creates draft single pull requests or publishes existing wt-stack Stacks
  with new pull requests left in draft, using Chad's commit template, PR
  conventions, and writing voice. Use when the user asks to create, open,
  write, format, or publish a pull request, including GitHub alert callouts,
  stacked pull requests, or a commit and PR together.
user-invocable: true
---

# Creating Pull Requests

Create and publish either a single pull request or an existing Stack. Leave
every newly created pull request in draft unless the user explicitly asks to
open it ready for review.

The `creating-commits` skill owns the message content contract, commit
mechanics, staging, voice, and the `linctl` ticket commands. Read it before
drafting and apply the PR overrides below.

## Workflow

1. When `wt-stack` is available, run `wt-stack --json status`.
2. If the current branch belongs to a Stack, use the stacked pull request
   workflow below and stop the single pull request workflow.
3. If currently on `main`, create a new branch before committing. Choose a
   sensible branch name based on the work.
4. At the publication boundary, re-read this skill and the `creating-commits`
   skill if the conversation was compacted or the user redirected the task after
   either skill was read.
5. Draft the complete, unwrapped PR body and check it against the publication
   checklist below.
6. Create the commit from that prepared title and body through the
   `creating-commits` skill, hard-wrapping only the commit body.
7. Push the branch.
8. Open the PR with `gh pr create --draft --title` and `--body`. Do not use
   `--fill`. Omit `--draft` only when the user explicitly asks to open the PR
   ready for review.
9. Read the live PR with `gh pr view <url> --json isDraft,title,body,url` and
   compare it with the requested draft state, prepared title, body, and
   publication checklist before reporting success.

## Stacked pull request workflow

Read and follow the `managing-stacked-changes` skill before publishing a Stack.

1. At the publication boundary, re-read this skill, the `creating-commits`
   skill, and the `managing-stacked-changes` skill if the conversation was
   compacted or the user redirected the task after any of them was read.
2. Prepare and validate the final unwrapped title and body for every unpublished
   review unit before committing or syncing.
3. Use the `creating-commits` skill for any uncommitted review unit, deriving
   its message from the prepared PR title and body.
4. Unless the user explicitly asks to open the Stack ready for review, run the
   dry-run and synchronization sequence from the `managing-stacked-changes`
   skill with `--draft`. Omit `--draft` only for that explicit override.
5. Run `wt-stack --json --stack <name> status` and collect every pull request
   URL.
6. For every newly created pull request, always run
   `gh pr edit <url> --title <title> --body <body>` with the prepared unwrapped
   content. Treat the commit-derived body as an initial value, not the final PR
   description. Apply requested labels and reviewers through the corresponding
   `gh pr edit` options.
7. Read each live PR with `gh pr view <url> --json isDraft,title,body,url` and
   compare it with the requested draft state, prepared content, and publication
   checklist.
8. Report the Stack name, branch order, and every pull request URL only after
   the live state and descriptions pass that check.

Do not run `gh pr create`, push branches individually, or set pull request bases
manually for Stack-owned branches. `wt-stack` owns those operations and keeps
the remote Stack consistent.

Do not add pull request body alerts or instructions that tell reviewers which
pull request in a Stack to merge first. GitHub's native Stack UI shows the
order, and its merge workflow handles the required lower layers and retargets
the remaining higher layers. Reserve callouts for context GitHub does not
already communicate.

## PR Overrides

These override the `creating-commits` skill's defaults when the commit is part
of a pull request:

- Do not commit directly to `main`. Branch first.
- If no ticket number was provided, create a Linear ticket by default using the
  ticket creation steps in the `creating-commits` skill, unless the repository
  is a personal repository under `github.com/chadxz/` or hosted on Tangled.
- Keep the Linear ticket description unwrapped even though the commit message
  body is wrapped at 72 characters. Preserve all intentional Markdown structure
  and let Linear wrap prose in the UI.
- Use the ticket identifier in both the commit message and the PR body.
- Use `main` as the base for a single pull request unless the user says
  otherwise. `wt-stack` owns the bases within a Stack.

## Pull Request Body

The PR body must use the commit template's visible structure and satisfy the
message content contract in `creating-commits`. The template is a structural
skeleton; the skills are the authoritative source for authoring requirements.
Correct headings alone are not evidence that the description complies.

Apply two presentation changes:

1. Remove hard line breaks so GitHub's markdown renderer can wrap text
   naturally.
2. Apply the `writing-in-my-voice` skill to all prose.

## Publication Checklist

Before creating or updating the pull request, verify all of the following:

- The body is written for a junior software engineer with no prior context.
- `Why?` supplies the necessary background, concrete problem and impact, reason
  for the change, plain-language definitions, and every available relevant
  source link.
- `How?` explains the chosen approach, component responsibilities, meaningful
  tradeoffs, validation commands and results, why that evidence matters, and
  every available relevant implementation or third-party source link.
- The prose stands on its own. Links provide supporting detail rather than
  replacing the explanation.
- The body is unwrapped for GitHub while preserving intentional Markdown
  structure.
- Every newly created pull request is in draft unless the user explicitly asked
  to open it ready for review.
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
