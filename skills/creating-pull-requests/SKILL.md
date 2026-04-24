---
name: creating-pull-requests
description:
  Creates Git commits and opens pull requests using Chad's commit template,
  PR conventions, and writing voice. Use when the user asks to create a pull
  request, open a PR, or commit changes and create a PR together.
user-invocable: true
---

# Creating Pull Requests

Create a commit, push the branch, and open a pull request.

## Workflow

1. Inspect the working tree with `git status --short`.
2. Review the relevant diff before writing the commit message.
3. Read the commit template:
   ```bash
   git config --get commit.template
   ```
   Then read the file at that path.
4. Apply the `writing-in-my-voice` skill to commit and PR prose.
5. Stage only the files that belong in this PR.
6. Create the commit.
7. Push the branch.
8. Open the PR with `gh pr create --title` and `--body`.

## Defaults

Unless the user already specified otherwise:

- If currently on `main`, create a new branch before committing. Choose a
  sensible branch name based on the work.
- Assume there is no co-authors section.
- If no associated ticket number was provided, create one.
- Use `main` as the PR base branch.

## Ticket Handling

If no ticket number was provided:

1. Draft the commit title and `Why?` section first.
2. Create a Linear ticket using that title and `Why?` as the body under the
   `EE` team:
   ```bash
   linctl issue create --title "<commit title>" \
     --description "<Why? content>" --team EE --assign-me --json
   ```
3. Move it to `In Review`:
   ```bash
   linctl issue update <TICKET_ID> --state "In Review"
   ```
4. Use the returned ticket identifier in the commit message and PR body.

## Commit Message

- Follow the commit template exactly.
- Title: maximum 50 characters.
- Body: line length must not exceed 72 characters.

## Pull Request Body

Do not use `--fill`. Use `gh pr create --title` and `--body` separately.

The PR body must use the same structure as the commit message body, with two
changes:

1. Remove hard line breaks so GitHub's markdown renderer can wrap text
   naturally.
2. Apply `writing-in-my-voice` to all prose.
