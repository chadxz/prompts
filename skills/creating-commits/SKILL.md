---
name: creating-commits
description:
  Creates Git commits using Chad's commit template and writing voice. Use when
  the user asks to commit changes, create a commit, or draft a commit message
  formatted to Chad's standards.
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
2. Create the ticket under the `EE` team:
   ```bash
   linctl issue create --title "<commit title>" \
     --description "<Why? content>" --team EE --assign-me --json
   ```
3. Move it to `In Review`:
   ```bash
   linctl issue update <TICKET_ID> --state "In Review"
   ```
4. Use the returned ticket identifier in the commit message.

If there is no ticket, remove the template's `Related to` line instead of
leaving a placeholder.

## Message Constraints

- Title: maximum 50 characters.
- Body: line length must not exceed 72 characters.
- Preserve the template's section structure unless the ticket handling rules
  say to remove the `Related to` line.
