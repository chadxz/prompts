---
name: using-git-worktrees
description:
  Chooses single-branch or wt-stack review topology and uses task-specific Git
  worktrees before changing files in a repository. Use for repository edits,
  non-trivial work with ordered review units, and workspaces managed by
  Conductor.build, Cursor, Codex.app, Claude Code, or other coding agents.
---

# Using Git Worktrees

Use this before changing files in a Git repo. The goal is to keep each task in
its own working tree, branch, dependencies, and verification state.

Chad's repositories use the bare container layout owned by the
`cloning-repositories` skill: a bare repository at `<repo>/.git` with worktrees
directly under `<repo>/`, and the default branch worktree at `<repo>/main`. Read
that skill for clone commands and layout details. Do not use a normal checkout
at the repository root and do not put task worktrees under `.worktrees/`.

## When to use this

Use the workflow for file-changing work inside a Git repository. Skip it for
read-only tasks, discussion, research, or commands that do not modify repo
files.

## Start with the current state

If you are already inside a worktree, run:

```bash
git status --short --branch
git worktree list
```

If you are at the repository container, run:

```bash
git -C <repo> worktree list
```

Treat unrelated dirty work as user-owned. Do not move, stage, revert, clean, or
overwrite another checkout's changes unless the user explicitly asks.

## Choose the review topology

Decide how reviewers should receive the work before creating the first task
branch. Review dependency determines this choice. File count, elapsed time, and
implementation difficulty do not.

Default to a `wt-stack` Stack when the task contains two or more ordered changes
that reviewers could understand and merge independently. Common examples
include:

- A refactor followed by behavior that depends on it.
- An API or schema followed by its consumers or migration.
- Infrastructure followed by application adoption.
- A foundation change followed by independently useful integrations.

Keep one branch when the result is one coherent review unit, even when it
touches many files. Use separate non-stacked branches when the changes are
independent and neither branch should be based on the other.

When a Stack applies, read and follow the `$managing-stacked-changes` skill. Let
that skill create or adopt the task branches and sibling worktrees. If
`wt-stack doctor` reports that the repository lacks GitHub Stacks support, use
the normal single-branch workflow and report the unavailable capability as a
consideration.

If a single-branch task grows into multiple ordered review units before
publication, adopt the current branch as the bottom of a Stack and add later
units through the `$managing-stacked-changes` skill. Do not rewrite published
history solely to manufacture a Stack.

## Choose a single-branch worktree

If the current checkout is already for this task, use it. If the current
checkout belongs to a different task, create a manual worktree.

- Conductor.build workspaces already satisfy this workflow. Use the current
  workspace unless the user asks for a separate one.
- Cursor `/worktree`, `/best-of-n`, and background-agent worktrees satisfy this
  workflow for isolated tasks. For feature work that should survive cleanup, use
  a manual worktree or a persistent Cursor window opened on that worktree.
- Codex.app managed worktrees satisfy this workflow for per-thread background
  work. For long-lived work, use a permanent Codex worktree or a manual
  worktree.
- Other coding agents should use a manual worktree when they are not already
  running in a task-specific checkout.

## Manual worktree convention

Store manual worktrees directly under the repo container:

```text
<repo>/<task-slug>
```

The repo container is a bare repository, so these task worktrees are adjacent to
`.git` and `main` rather than nested inside another working tree.

Use short slugs. Include issue identifiers when present:

```text
fix-sftp-tenant-validation
EE-1234-fix-sftp-tenant-validation
gh-5678-fix-sftp-tenant-validation
```

Use matching branch names:

```text
agent/fix-sftp-tenant-validation
EE-1234/fix-sftp-tenant-validation
gh-5678/fix-sftp-tenant-validation
```

For example:

```bash
git -C ~/src/convergint/ee-monorepo worktree add \
  -b agent/fix-sftp-tenant-validation \
  ~/src/convergint/ee-monorepo/fix-sftp-tenant-validation
```

## Work from the worktree

After choosing the worktree:

1. Change into the worktree.
2. Re-read repository instructions from inside that checkout.
3. Run setup commands if the project needs dependencies, generated files, or
   per-worktree environment files.
4. Make edits, run verification, and inspect `git status --short --branch` from
   the worktree before reporting back.

Do not run broad destructive cleanup until you understand which worktree you are
inside and what other worktrees exist for the repository.

## Finish safely

Commit, push, open a PR, merge, remove the worktree, or delete the branch only
when the user asks or the active agent workflow owns that action.

When reporting completion, include the worktree path and branch name when a
manual worktree was created. If worktree creation was blocked, explain the
blocker and wait for direction instead of editing the main checkout.
