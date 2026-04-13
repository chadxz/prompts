---
name: create-commit
description:
  Creates a commit using Chad's commit template and writing voice.
  Use when the user wants to create a commit or needs a commit
  message formatted to Chad's standards.
user-invocable: true
---

# Create Commit

Create a commit message following my personal Git commit template.

## Template Lookup

First, retrieve my commit template:

```bash
git config --get commit.template
```

Then read the file at that path to understand the format.

## Voice

Apply the writing-in-my-voice skill to all prose sections of the
commit message.

## Constraints

- **Title**: Maximum 50 characters
- **Body**: Line length must not exceed 72 characters

## Before Generating

Unless I've already specified:

1. Check if I'm on `main` — if so, ask if I want to create a new branch first
2. Ask if I want to include a **co-authors** section
3. Ask for the **associated ticket number**

## Ticket Handling

If no ticket number was provided:

1. Draft the commit **title** and **Why?** section first.
2. Create a new Linear ticket using that title and Why? as the body
   under the `EE` team:
   ```bash
   linctl issue create --title "<commit title>" \
     --description "<Why? content>" --team EE --assign-me --json
   ```
3. Immediately move it to **In Review**:
   ```bash
   linctl issue update <TICKET_ID> --state "In Review"
   ```
4. Use the returned ticket identifier as the associated ticket for the rest
   of the commit message.
