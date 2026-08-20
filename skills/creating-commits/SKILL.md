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

Create a commit using Chad's personal commit structure and message contract.

## Workflow

1. Inspect the working tree with `git status --short`.
2. Review the relevant diff before writing the message.
3. Read the commit template:
   ```bash
   git config --get commit.template
   ```
   The template owns the visible headings, separator, and ticket placeholder.
   This skill owns the authoring requirements below.
4. If the conversation was compacted or the user redirected the task after this
   skill was read, re-read this skill immediately before drafting the message.
5. For a pull-request commit, read the `creating-pull-requests` skill and draft
   the final, unwrapped PR body first. For a standalone commit, draft the
   message directly.
6. Apply the `writing-in-my-voice` skill to all prose sections.
7. Check the draft against the message content contract below.
8. Before committing, give the user a concise checkpoint confirming that the
   draft includes the audience context, problem and impact, approach and
   tradeoffs, validation, and every available relevant source link. State when
   no relevant external source exists.
9. Stage only the files that belong in this commit.
10. Create the commit with the generated message.

Do not run `git commit` until every applicable contract item is present. A
message with the right headings can still fail the contract.

## Message Content Contract

Write for a junior software engineer who has no prior context for the change.
The reader must understand the message without inspecting the diff or opening a
link first. Use plain language and define unfamiliar terms where they first
appear.

The `Why?` section must explain:

- The existing system or behavior and the background needed to understand it.
- The concrete problem and its impact on the business: cost, risk, delay,
  lost revenue, support load, or a capability the company cannot offer yet.
- The value this change creates: who is unblocked, what we can ship or operate
  after this that we could not before, and why that matters now.
- Any unfamiliar project, tool, or domain term used in the explanation.
- Direct links to relevant ADRs, design documents, dependent or preceding pull
  requests, and maintained third-party documentation or repositories when those
  sources exist.

Never treat a ticket, plan, ADR, RFC, or "the user asked" as the reason for the
change. Those are pointers to the work. Sentences like "the ticket says so,"
"the plan calls for this," "this implements EE-1232," or "the RFC requires it"
fail the contract even when they are factually true. Name the operational or
business outcome instead. Links still belong in `Why?` as supporting sources;
they do not replace the value explanation.

The `How?` section must explain:

- The chosen approach and the responsibilities of the important components.
- Meaningful tradeoffs or alternatives that affected the implementation.
- The validation commands and results, including why they provide useful
  evidence.
- Direct links to relevant implementation sources and third-party tools when
  those sources exist.

Links support the explanation; they do not replace it. Do not omit a relevant
source that is available in the task context. Skip details that are obvious from
the diff and avoid a step-by-step diary.

## Pull-request Commits

For a commit that will create a pull request, the complete unwrapped PR body is
the primary authoring artifact. Draft and validate it under the
`creating-pull-requests` skill first, then use the same title and prose for the
commit message, hard-wrapped at 72 characters. The wrapping rule controls line
width; it is not a target for message length.

## Stack-aware commits

When `wt-stack` is available, run `wt-stack --json status` before staging to
determine whether the current branch belongs to a Stack. A repository without
local Stack state continues through the normal workflow.

For a Stack-owned branch:

- Preserve the branch and review-unit boundaries from the
  `managing-stacked-changes` skill.
- Keep the commit scoped to the review unit owned by the current branch and
  worktree.
- Before the first `wt-stack sync`, derive the branch tip's commit title and
  body from the prepared PR title and body. `wt-stack` uses that commit to
  initialize a missing pull request.
- Leave rebasing and pushing to `wt-stack sync`. Do not push a Stack branch
  independently as part of a combined commit-and-publish request.

The commit-derived PR description is only an initial value. The
`creating-pull-requests` skill requires publishing and verifying the prepared
body after `wt-stack sync`. Once the pull request exists, later commits can
describe their incremental change because `wt-stack` does not replace existing
pull request metadata from those messages.

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
