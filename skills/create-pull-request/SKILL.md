---
name: create-pull-request
description:
  Creates a commit and opens a pull request using Chad's commit
  template and PR conventions. Use when the user wants both the
  commit and the pull request handled together.
user-invocable: true
---

# Create Pull Request

Create a commit, then open a pull request.

## Commit Message

Create a commit message following my personal Git commit template.

### Template Lookup

First, retrieve my commit template:

```bash
git config --get commit.template
```

Then read the file at that path to understand the format.

### Voice

Apply the writing-in-my-voice skill to all prose sections of the
commit message.

### Constraints

- **Title**: Maximum 50 characters
- **Body**: Line length must not exceed 72 characters

## Pull Request Description

Don't use `--fill`. Instead, use `gh pr create --title` and `--body`
separately.

The PR body must use the same structure as the commit message body
(the format from my commit template), with two differences:

1. Remove hard line breaks so GitHub's markdown renderer can wrap
   text naturally.
2. Apply the writing-in-my-voice skill to all prose in the PR body.

## Before Starting

Unless I've already specified:

1. Check if I'm on `main` — if so, ask if I want to create a new branch first
2. Ask if I want to include a **co-authors** section
3. Ask for the **associated ticket number**
4. Ask what branch to use as the base for the pull request

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
