---
name: creating-pull-requests
description:
  Creates Git commits and opens pull requests using Chad's commit template,
  PR body template, PR conventions, and writing voice. Use when the user asks
  to create a pull request, open a PR, write a PR body, or commit changes and
  create a PR together.
user-invocable: true
---

# Creating Pull Requests

Create a commit, push the branch, and open a pull request.

The `creating-commits` skill owns the commit mechanics: reading the commit
template, message constraints, staging, voice, and the `linctl` ticket commands.
Read it before committing and apply the PR overrides below.

## Workflow

1. If currently on `main`, create a new branch before committing. Choose a
   sensible branch name based on the work.
2. Create the commit using the `creating-commits` workflow with the PR overrides
   below.
3. Push the branch.
4. Open the PR with `gh pr create --title` and `--body`.

## PR Overrides

These override the `creating-commits` defaults when the commit is part of a pull
request:

- Do not commit directly to `main`. Branch first.
- If no ticket number was provided, create a Linear ticket by default using the
  ticket creation steps in `creating-commits`, unless the repository is a
  personal repository under `github.com/chadxz/` or hosted on Tangled.
- Use the ticket identifier in both the commit message and the PR body.
- Use `main` as the PR base branch unless the user says otherwise.

## Pull Request Body

Do not use `--fill`. Use `gh pr create --title` and `--body` separately.

The PR body must use the same structure as the commit message body, with two
changes:

1. Remove hard line breaks so GitHub's markdown renderer can wrap text
   naturally.
2. Apply `writing-in-my-voice` to all prose.

If another instruction suggests a generic `Summary` / `Test plan` PR body,
prefer this template and report that decision in the final response.
