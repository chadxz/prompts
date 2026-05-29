---
name: using-git-worktrees
description:
  Uses a task-specific git worktree before changing files in a Git repository.
  Covers manual worktrees and Conductor.build, Cursor, Codex.app, Claude Code,
  and other agent-managed workspaces.
---

# Using Git Worktrees

Use this before changing files in a Git repo. The goal is to keep the user's
main checkout clean while each task gets its own working tree, branch,
dependencies, and verification state.

## When to use this

Use the workflow for file-changing work inside a Git repository. Skip it for
read-only tasks, discussion, research, or commands that do not modify repo
files.

## Start with the current state

Run these from the repo the user asked about:

```bash
git status --short --branch
git worktree list
```

Treat unrelated dirty work as user-owned. Do not move, stage, revert, clean, or
overwrite another checkout's changes unless the user explicitly asks.

## Choose the worktree

If the current checkout is already for this task, use it. If it is the user's
main checkout or belongs to a different task, create a manual worktree.

- Conductor.build workspaces already satisfy this workflow. Use the current
  workspace unless the user asks for a separate one.
- Cursor `/worktree`, `/best-of-n`, and background-agent worktrees satisfy this
  workflow for isolated tasks. For feature work that should survive cleanup,
  use a manual worktree or a persistent Cursor window opened on that worktree.
- Codex.app managed worktrees satisfy this workflow for per-thread background
  work. For long-lived work, use a permanent Codex worktree or a manual
  worktree.
- Other coding agents should use a manual worktree when they are not already
  running in a task-specific checkout.

## Manual worktree convention

Store manual worktrees under the repo:

```text
<repo>/.worktrees/<task-slug>
```

Keep `/.worktrees/` in the global Git ignore file. Before creating a nested
worktree, verify that Git ignores it:

```bash
git check-ignore -q .worktrees/ || git check-ignore -q .worktrees/example
```

If that check fails, fix the ignore configuration before creating the worktree.

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
  ~/src/convergint/ee-monorepo/.worktrees/fix-sftp-tenant-validation
```

## Work from the worktree

After choosing the worktree:

1. Change into the worktree.
2. Re-read repository instructions from inside that checkout.
3. Run setup commands if the project needs dependencies, generated files, or
   per-worktree environment files.
4. Make edits, run verification, and inspect `git status --short --branch`
   from the worktree before reporting back.

Do not run broad destructive cleanup from the main checkout while nested
worktrees exist. In particular, inspect before running commands such as
`git clean -fdx`, because ignored `.worktrees/` directories can still be
removed by force-clean commands.

## Finish safely

Commit, push, open a PR, merge, remove the worktree, or delete the branch only
when the user asks or the active agent workflow owns that action.

When reporting completion, include the worktree path and branch name when a
manual worktree was created. If worktree creation was blocked, explain the
blocker and wait for direction instead of editing the main checkout.
