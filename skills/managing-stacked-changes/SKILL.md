---
name: managing-stacked-changes
description:
  Plans, creates, updates, publishes, and retires dependent GitHub pull
  requests with wt-stack in Chad's bare sibling-worktree layout. Use for
  non-trivial implementation work with two or more ordered, independently
  reviewable changes, stacked pull requests, dependent branches, or an existing
  wt-stack Stack.
---

# Managing Stacked Changes

Use `wt-stack` to manage dependent review units as branches in sibling
worktrees. Git remains the source of truth for branches and worktrees. GitHub
remains the source of truth for pull requests and the remote Stack.

## Choose a Stack

Use a Stack when the task contains two or more ordered changes that reviewers
could understand and merge independently. Plan the review units from bottom to
top. Each later unit must depend on the branch immediately below it.

Good Stack boundaries include:

- A refactor followed by behavior that uses it.
- An API or schema followed by consumers or migration.
- Infrastructure followed by application adoption.
- A foundation followed by separate integrations.

Keep one branch for one coherent review unit, regardless of its file count. Give
independent changes separate branches based on the trunk branch.

## Verify prerequisites

Start from a task-specific worktree selected through `using-git-worktrees`.
Inspect the repository before changing Stack state:

```console
git status --short --branch
git worktree list
command -v wt-stack
wt-stack --version
wt-stack doctor
```

Stop Stack setup when `wt-stack` is missing, authentication is unavailable, or
GitHub Stacks support is disabled for the repository. Continue with the normal
single-branch workflow and report the missing capability as a consideration.
Require `wt-stack` v0.4.0 or newer for the complete lifecycle documented here.

Treat existing dirty work in any worktree as user-owned. Stack mutations that
rebase require every active worktree to be clean.

## Plan the review units

Choose a short Stack name and one branch name per review unit. Include the
ticket identifier when one exists. Record the intended order before creating
branches:

```text
Stack: EE-1234-delivery
1. EE-1234/api
2. EE-1234/consumer
```

Keep each branch limited to its review unit. A branch should build and test
against the branch directly below it.

## Start a new Stack

Create the bottom branch and task worktree with `using-git-worktrees`. From that
worktree, verify prerequisites and adopt the branch:

```console
wt-stack init --name <stack>
```

Implement and commit the bottom review unit before creating the next branch.
`add` bases the new branch on the current active Stack tip:

```console
wt-stack --stack <stack> add <next-branch>
wt-stack --json --stack <stack> status
```

Change into the worktree reported by `status`, implement the next review unit,
and commit it through `creating-commits`. Repeat `add` from bottom to top.

To adopt an existing linear chain, ensure each branch is checked out in a
sibling worktree and list the branches from bottom to top:

```console
wt-stack init --name <stack> <bottom-branch> <next-branch>
```

Do not rewrite published history solely to convert existing work into a Stack.
Ask before restructuring branches that other people may already use.

## Commit and publish

Before the first publication, ensure every branch tip has a commit title and
body suitable for its pull request. `wt-stack` uses the tip commit when it
creates a missing pull request.

Preview the complete mutation, then publish:

```console
wt-stack --dry-run --stack <stack> sync
wt-stack --stack <stack> sync
wt-stack --json --stack <stack> status
```

`sync` refreshes pull request state, rebases active branches from bottom to top,
pushes them atomically with explicit leases, creates missing pull requests,
repairs their bases, and creates or updates the GitHub Stack.

Do not manually rebase Stack branches, push them individually, or create their
pull requests with `gh pr create`. After `sync`, apply the PR body rules from
`creating-pull-requests` without restarting its workflow. Use `gh pr edit` for
unwrapped PR bodies, labels, or reviewers that `wt-stack` does not manage.

## Continue working

Commit changes in the worktree that owns the affected review unit. Run the same
dry run and `sync` sequence to update the Stack.

When a cascading rebase pauses, resolve and stage the conflicts in the worktree
reported by `wt-stack`, then choose one recovery command:

```console
wt-stack continue
wt-stack abort
```

`continue` resumes the recorded cascade. `abort` restores every participating
branch to its pre-rebase commit. Do not start another Stack mutation while a
rebase is paused.

## Finish the Stack

After GitHub merges each pull request, refresh local state:

```console
wt-stack --stack <stack> refresh
```

Merged branches remain in Stack history and are excluded from later rebases and
pushes. After the full Stack merges, remove its GitHub and local Stack records:

```console
wt-stack --stack <stack> unstack
```

`unstack` preserves pull requests, branches, commits, and worktrees. Remove
clean merged worktrees separately only when the user asks or the active workflow
owns cleanup.

## Report the result

Include:

- The Stack name and bottom-to-top branch order.
- The worktree path for each branch created during the task.
- Every pull request URL after publication.
- Any paused rebase and the exact worktree that needs conflict resolution.
- Any prerequisite failure that forced the single-branch fallback.
