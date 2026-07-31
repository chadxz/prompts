---
name: creating-pull-requests
description:
  Creates single pull requests or publishes existing wt-stack Stacks using
  Chad's commit template, PR conventions, and writing voice. Use when the user
  asks to create, open, write, format, or publish a pull request, including
  GitHub alert callouts, stacked pull requests, or a commit and PR together.
user-invocable: true
---

# Creating Pull Requests

Create and publish either a single pull request or an existing Stack.

The `creating-commits` skill owns the commit mechanics: reading the commit
template, message constraints, staging, voice, and the `linctl` ticket commands.
Read it before committing and apply the PR overrides below.

## Workflow

1. When `wt-stack` is available, run `wt-stack --json status`.
2. If the current branch belongs to a Stack, use the stacked pull request
   workflow below and stop the single pull request workflow.
3. If currently on `main`, create a new branch before committing. Choose a
   sensible branch name based on the work.
4. Create the commit using the `creating-commits` skill with the PR overrides
   below.
5. Push the branch.
6. Open the PR with `gh pr create --title` and `--body`.

## Stacked pull request workflow

Read and follow the `managing-stacked-changes` skill before publishing a Stack.

1. Use the `creating-commits` skill for any uncommitted review unit.
2. Run `wt-stack --stack <name> sync`.
3. Run `wt-stack --json --stack <name> status` and collect every pull request
   URL.
4. Apply the PR body rules below to each newly created pull request. Use
   `gh pr edit <url> --body <body>` when the body needs unwrapped prose. Apply
   requested labels and reviewers through the corresponding `gh pr edit`
   options.
5. Report the Stack name, branch order, and every pull request URL.

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

Do not use `--fill`. Use `gh pr create --title` and `--body` separately.

The PR body must use the same structure as the commit message body, with two
changes:

1. Remove hard line breaks so GitHub's markdown renderer can wrap text
   naturally.
2. Apply the `writing-in-my-voice` skill to all prose.

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
