---
name: creating-commits
description:
  Creates Git commits using Chad's commit template and writing voice, including
  PR-ready commits for wt-stack branches. Use when the user asks to commit
  changes, create a commit, or draft a commit message formatted to Chad's
  standards.
user-invocable: true
---

# Creating Commits

Create a commit using Chad's personal commit template.

## Workflow

1. Inspect the working tree with `git status --short`.
2. Review the relevant diff before writing the message.
3. Read the commit template:
   ```bash
   git config --get commit.template
   ```
   Then read the file at that path.
4. Apply the `writing-in-my-voice` skill to all prose sections.
5. Stage only the files that belong in this commit.
6. Create the commit with the generated message.

## Stack-aware commits

When `wt-stack` is available, run `wt-stack --json status` before staging to
determine whether the current branch belongs to a Stack. A repository without
local Stack state continues through the normal workflow.

For a Stack-owned branch:

- Preserve the branch and review-unit boundaries from
  `managing-stacked-changes`.
- Keep the commit scoped to the review unit owned by the current branch and
  worktree.
- Before the first `wt-stack sync`, make the branch tip's commit title and body
  suitable for the pull request. `wt-stack` uses that commit when it creates a
  missing pull request.
- Leave rebasing and pushing to `wt-stack sync`. Do not push a Stack branch
  independently as part of a combined commit-and-publish request.

Once the pull request exists, later commits can describe their incremental
change. `wt-stack` does not replace existing pull request metadata from those
commit messages.

## Defaults

Unless the user already specified otherwise:

- Commit to the branch that is currently checked out, even if it is `main`.
- Do not create or switch branches unless the user explicitly asks.
- Assume there is no co-authors section.
- Assume there is no associated Linear ticket.
- Do not create a Linear ticket by default.
- When the repository remote is a personal repository under `github.com/chadxz/`
  or hosted on Tangled, do not create a ticket for the commit.

## Ticket Handling

If the user provides a ticket number, include the template's `Related to` line
using that ticket.

If the repository is a personal repository under `github.com/chadxz/` or hosted
on Tangled, do not create a ticket for the commit. If there is no user-provided
ticket, remove the template's `Related to` line.

If the user explicitly asks to create a Linear ticket and the repository is not
a personal repository under `github.com/chadxz/` or hosted on Tangled:

1. Draft the commit title and `Why?` section first.
2. Create a Linear-specific copy of the `Why?` content. Remove hard line breaks
   inside prose paragraphs, including prose within list items. Preserve all
   intentional Markdown structure, including blank lines, headings, separate and
   nested list items, blockquotes, and code blocks. Do not reuse the 72-column
   commit body verbatim.
3. Create the ticket under the `EE` team:
   ```bash
   linctl issue create --title "<commit title>" \
     --description "<Why? content>" --team EE --assign-me --json
   ```
4. Move it to `In Review`:
   ```bash
   linctl issue update <TICKET_ID> --state "In Review"
   ```
5. Use the returned ticket identifier in the commit message.

The commit message's 72-character body limit does not apply to Linear ticket
descriptions or comments. Let Linear wrap their prose in the UI.

If there is no ticket, remove the template's `Related to` line instead of
leaving a placeholder.

## Message Constraints

- Title: maximum 50 characters.
- Body: line length must not exceed 72 characters.
- Preserve the template's section structure unless the ticket handling rules say
  to remove the `Related to` line.
