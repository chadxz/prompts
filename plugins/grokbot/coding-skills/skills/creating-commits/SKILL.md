---
name: creating-commits
description: >-
  Creates Git commits using Chad's commit template and writing voice, including
  commits that seed a pull request. Use when committing changes, creating a
  commit, or drafting a commit message to Chad's standards, including in Cursor
  cloud agent runs.
---

# Creating Commits

Create a commit using Chad's personal commit structure and message contract.
These commits show up under Chad's GitHub account, so write titles and bodies in
Chad's first person and never name Chad in the third person.

## Workflow

1. Inspect the working tree with `git status --short`.
2. Review the relevant diff before writing the message.
3. Find the commit template. Run `git config --get commit.template` and read
   that file when it's set. Otherwise, such as on a cloud VM, use the template
   in "Commit Template" below. The template owns the visible headings,
   separator, and ticket placeholder. This skill owns the authoring requirements
   below.
4. If the conversation was compacted or the task was redirected after this skill
   was read, re-read this skill immediately before drafting the message.
5. For a pull-request commit, read the `creating-pull-requests` skill and draft
   the final, unwrapped PR body first. For a standalone commit, draft the
   message directly.
6. Apply the `writing-in-my-voice` skill to all prose sections when it's
   available. Without it, keep the voice plain, direct, and conversational, and
   use contractions.
7. Check the draft against the message content contract below.
8. Before committing, confirm that the draft explains the problem, outcome,
   approach, and validation at a depth suited to the change's complexity, with
   relevant context, tradeoffs, and source links where applicable. State when no
   relevant external source exists. In an interactive session, give the user
   that confirmation as a short checkpoint. In an autonomous run, such as a
   cloud agent, check it yourself and continue.
9. Stage only the files that belong in this commit.
10. Create the commit with the generated message.

Do not run `git commit` until every applicable contract item is present. A
message with the right headings can still fail the contract.

## Commit Template

Use this structure when no `commit.template` is configured. The first line is
the title.

```text
<title>

Why?
====

<why>

How?
====

<how>

----

[Related to EE-<number>](https://linear.app/convergint/issue/EE-<number>).
```

## Message Content Contract

Write for a junior software engineer who has no prior context for the change.
The reader must understand the message without inspecting the diff or opening a
link first. Use plain language and define unfamiliar terms where they first
appear.

Scale the description to the complexity of the change and the context needed to
understand it. Simple changes usually need only a brief explanation in each
section. Complex changes need a more thorough account of the background,
reasoning, tradeoffs, and validation. Judge complexity by the reasoning and
context a reader needs: a small diff can require substantial explanation, and a
large mechanical change can be simple to explain.

Use the contract below to choose relevant content. It isn't a requirement for a
separate sentence or paragraph per bullet. Keep the problem, outcome, approach,
and validation clear; include supporting details only where they help the reader
understand or assess the change. Don't invent business stakes, alternatives, or
unfamiliar terms to fill out the message.

The `Why?` section must explain the problem and value, with relevant context:

- The existing system or behavior and the background needed to understand it.
- The concrete problem and its impact on the business: cost, risk, delay, lost
  revenue, support load, or a capability the company cannot offer yet.
- The value this change creates: who is unblocked, what we can ship or operate
  after this that we could not before, and why that matters now.
- Any unfamiliar project, tool, or domain term used in the explanation.
- Direct links to relevant ADRs, design documents, dependent or preceding pull
  requests, and maintained third-party documentation or repositories when those
  sources exist.

Never treat a ticket, plan, ADR, RFC, brief, or "the user asked" as the reason
for the change. Those are pointers to the work. Sentences like "the ticket says
so," "the plan calls for this," "this implements EE-1232," or "the RFC requires
it" fail the contract even when they are factually true. Name the operational or
business outcome instead. Links still belong in `Why?` as supporting sources;
they do not replace the value explanation.

The `How?` section must explain the approach and validation, with relevant
implementation detail:

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

For stacked work, keep each commit scoped to the review unit owned by its
branch. Later commits on a branch with an open PR can describe their incremental
change; they don't replace the PR description.

## Defaults

Unless the user or brief already specified otherwise:

- Follow the branch rules of the environment. In a cloud agent run, commit to
  the run's working branch, never to the default branch. In an interactive
  session, commit to the branch that's checked out and don't create or switch
  branches unless asked.
- Assume there is no co-authors section.
- Use the ticket from the brief or user when one is given. Don't create a Linear
  ticket by default.
- When the repository remote is a personal repository under `github.com/chadxz/`
  or hosted on Tangled, do not create a ticket for the commit.

## Ticket Handling

If the brief or user provides a ticket ID, include the template's `Related to`
line using that ticket. If there is no ticket, remove the `Related to` line
instead of leaving a placeholder.

If you're explicitly asked to create a Linear ticket and the repository is not a
personal repository under `github.com/chadxz/` or hosted on Tangled:

1. Draft the commit title and `Why?` section first.
2. Create a Linear-specific copy of the `Why?` content. Remove hard line breaks
   inside prose paragraphs, including prose within list items. Preserve all
   intentional Markdown structure, including blank lines, headings, separate and
   nested list items, blockquotes, and code blocks. Do not reuse the 72-column
   commit body verbatim.
3. Create the ticket on the `EE` team, assigned to Chad, with the Linear tool
   available in your environment (a Linear MCP server, or
   `linctl issue create
   --team EE --assign-me` on Chad's Mac). Move it to
   `In Review`.
4. Use the returned ticket identifier in the commit message.

If no Linear tool is available, commit without the `Related to` line and report
that the ticket is missing.

The commit message's 72-character body limit does not apply to Linear ticket
descriptions or comments. Let Linear wrap their prose in the UI.

## Message Constraints

- Title: maximum 50 characters.
- Body: line length must not exceed 72 characters.
- Preserve the template's section structure unless the ticket handling rules say
  to remove the `Related to` line or the `creating-pull-requests` skill adds a
  frontend `Demo` section to the prepared PR body.
