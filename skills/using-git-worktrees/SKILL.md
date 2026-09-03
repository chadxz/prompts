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

Resolve an existing worktree before running status, diff, build, test, or
file-changing commands. Run the bundled read-only resolver from this skill's
directory:

```bash
scripts/resolve-worktree --cwd "$PWD" --mode write
```

When the task names a repository, branch, or pull request, pass it directly:

```bash
scripts/resolve-worktree \
  --repo ~/src/convergint/ee-monorepo \
  --branch agent/fix-sftp-tenant-validation \
  --mode write

scripts/resolve-worktree \
  --pr convergint/ee-monorepo#5678 \
  --mode write
```

The resolver never creates a branch or worktree. It reports the repository
container, selected worktree, branch, head SHA, dirty state, default-branch
status, mise trust state, and whether a pull request worktree matches the
current PR head. Use its absolute `worktree` value as the working directory for
every later command.

The resolver requires Bash and Git. JSON output requires `jq`, and pull request
resolution also requires `gh`.

Write mode refuses the default-branch worktree unless `--allow-main` is
explicitly provided. If no matching worktree exists, continue through the
topology decision below and create one only after choosing a single branch or
Stack. Re-run the resolver after creation to verify the selected checkout.

Treat unrelated dirty work as user-owned. Do not move, stage, revert, clean, or
overwrite another checkout's changes unless the user explicitly asks.

## Keep the default worktree current

Fetch the remote default branch before using it as the base for a new task
worktree. Also fetch whenever status, branch comparisons, or another command
shows that the default-branch worktree may be behind:

```bash
git -C <repo-container> fetch origin <default-branch>
git -C <main-worktree> status --short --branch
git -C <main-worktree> rev-list --left-right --count \
  <default-branch>...origin/<default-branch>
```

The counts are local-ahead and local-behind, in that order. When the default
worktree is clean and the counts are `0 N`, where `N` is greater than zero,
update it immediately without waiting for another request:

```bash
scripts/resolve-worktree \
  --repo <repo-container> \
  --main \
  --mode write \
  --allow-main

git -C <main-worktree> merge --ff-only origin/<default-branch>
```

`--allow-main` applies only to this synchronization. Do not make task changes in
the default worktree.

If the default worktree is dirty, ahead, or diverged, do not stash, reset,
rebase, merge, or overwrite it. Treat its state as user-owned and report why a
safe fast-forward was not possible. Base new work on the fetched remote default
branch when that lets the task continue without modifying the blocked worktree.

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
3. Run `mise trust` if the checkout's mise configuration is untrusted.
4. Run setup commands if the project needs dependencies, generated files, or
   per-worktree environment files.
5. Make edits, run verification, and inspect `git status --short --branch` from
   the worktree before reporting back.

Do not run broad destructive cleanup until you understand which worktree you are
inside and what other worktrees exist for the repository.

## Merge Stack-owned pull requests

A pull request managed through the worktree Stack workflow can't be merged with
the regular `gh pr merge` command. That command uses GitHub's single-PR merge
path, which doesn't support Stack merges. Use the official `gh stack` extension
to submit an atomic Stack merge through GitHub's asynchronous Merge API:

```bash
gh stack merge <pull-request-or-stack-number> --yes --merge-method <method>
```

Use `squash`, `merge`, or `rebase` for `<method>` according to repository
policy. A pull request number merges that pull request and every unmerged pull
request below it. A Stack number merges the entire Stack. When the base branch
uses a merge queue, GitHub queues the Stack together and chooses the merge
method.

Install the extension if `gh stack merge` isn't available:

```bash
gh extension install github/gh-stack
```

After GitHub accepts the merge, refresh the local Stack state:

```bash
wt-stack --stack <stack> refresh
```

This restriction applies to Stack-owned pull requests. A single, unstacked pull
request created from a worktree can still use `gh pr merge`.

## Finish safely

Commit, push, open a PR, merge, remove the worktree, or delete the branch only
when the user asks or the active agent workflow owns that action.

When reporting completion, include the worktree path and branch name when a
manual worktree was created. If worktree creation was blocked, explain the
blocker and wait for direction instead of editing the main checkout.
