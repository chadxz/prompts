---
name: managing-stacked-changes
description:
  Plans, creates, updates, publishes, merges, and retires dependent GitHub pull
  requests with wt-stack in Chad's bare sibling-worktree layout. Use for
  non-trivial implementation work with two or more ordered, independently
  reviewable changes, stacked pull requests, dependent branches, merging a
  Stack, or an existing wt-stack Stack.
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

Start from a task-specific worktree selected through the `using-git-worktrees`
skill. Inspect the repository before changing Stack state:

```console
git status --short --branch
git worktree list
wt-stack --version
wt-stack doctor
```

Treat `wt-stack` as installed and use v0.6.0 or newer. If the shell reports
`command not found`, or the installed version is older, install it from the
prompts repository:

```console
mise trust ~/src/personal/prompts/main/apps/wt-stack/mise.toml
mise -C ~/src/personal/prompts/main/apps/wt-stack install
mise run -C ~/src/personal/prompts/main/apps/wt-stack :install
wt-stack --version
```

Resume the prerequisite checks after installation. If authentication is
unavailable or GitHub Stacks support is disabled for the repository, continue
with the normal single-branch workflow and report that capability as a
consideration.

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

Create the bottom branch and task worktree with the `using-git-worktrees` skill.
From that worktree, verify prerequisites and adopt the branch:

```console
wt-stack init --name <stack>
```

`init` discovers the selected remote's default branch. Use `--remote <remote>`
to select another remote or `--base <branch>` for an intentional base override.
If discovery fails, inspect the remote configuration instead of assuming `main`.

Implement and commit the bottom review unit before creating the next branch.
`add` bases the new branch on the current active Stack tip:

```console
wt-stack --stack <stack> add <next-branch>
wt-stack --json --stack <stack> status
```

Change into the worktree reported by `status`, implement the next review unit,
and commit it through the `creating-commits` skill. Repeat `add` from bottom to
top.

To adopt an existing linear chain, ensure each branch is checked out in a
sibling worktree and list the branches from bottom to top:

```console
wt-stack init --name <stack> <bottom-branch> <next-branch>
```

Do not rewrite published history solely to convert existing work into a Stack.
Ask before restructuring branches that other people may already use.

## Commit and publish

Treat publication as a separate phase from implementation. Immediately before
the first or delayed publication, re-read the `creating-commits` and
`creating-pull-requests` skills. Re-read them again when the conversation was
compacted or the user redirected the task after they were last read.

Prepare the final unwrapped pull request title and body for every unpublished
branch before committing or syncing. Check each body against the publication
checklist in `creating-pull-requests`, then derive the branch tip's commit title
and wrapped body from it. `wt-stack` uses the tip commit to initialize a missing
pull request; that generated description is not the final publication step.

Preview the complete mutation, then publish:

```console
wt-stack --dry-run --stack <stack> sync --draft
wt-stack --stack <stack> sync --draft
wt-stack --json --stack <stack> status
```

`sync` refreshes pull request state, rebases active branches from bottom to top,
pushes them atomically with explicit leases, creates missing pull requests as
drafts, repairs their bases, and creates or updates the GitHub Stack. Omit
`--draft` only when the user explicitly asks to open the Stack ready for review.

Do not manually rebase Stack branches, push them individually, or create their
pull requests with `gh pr create`. After `sync`, apply the prepared metadata to
every newly created pull request with
`gh pr edit <url> --title <title> --body <body>`. Then read each live pull
request with `gh pr view <url> --json title,body,url` and compare it with the
prepared content and publication checklist. Do not report successful publication
until every live description passes that check.

## Continue working

Commit changes in the worktree that owns the affected review unit. Run the same
dry run and `sync` sequence to update the Stack. When the change affects an
existing pull request description, reapply the prepared metadata with
`gh pr edit` and verify it with `gh pr view` after synchronization.

Rebases fetch and pin the trunk commit before replaying branches. Saved branch
boundaries are validated before the cascade starts. If that validation fails,
inspect the reported history and boundary; do not guess a fork point or edit
Stack metadata to bypass the check. Use `wt-stack rebase --no-fetch` only when
intentionally working from already fetched refs.

When `wt-stack` reports an actual paused rebase, resolve and stage the conflicts
in the reported worktree, then choose one recovery command. An ordinary Git or
preflight error does not necessarily leave a rebase to continue:

```console
wt-stack continue
wt-stack abort
```

`continue` resumes the recorded cascade against its pinned trunk commit and
validates the remaining branch boundaries. `abort` restores every participating
branch to its pre-rebase commit. Do not start another Stack mutation while a
rebase is paused.

## Merge a published Stack

Merge only when the user requests it or the active workflow owns that action.
Verify the selected pull requests are ready for review and satisfy repository
review and check requirements. For a locally tracked Stack, preview and submit
through `wt-stack`:

```console
wt-stack --dry-run --stack <stack> merge
wt-stack --json --stack <stack> merge
```

The default selection includes all active branches through the local Stack tip.
Add `--through <local-branch>` to both commands to merge only the prefix ending
at that branch. This takes a local branch name, not a pull request number. The
preflight checks published heads, bases, ancestry, worktree cleanliness, and
remote Stack membership. Resolve discrepancies before submitting a merge.

For direct merges, add `--merge-method squash`, `merge`, or `rebase` to both
commands when repository policy calls for it. Omitting the flag uses GitHub's
default, which is a merge commit for direct merges. Omit it for a merge queue;
GitHub chooses the queue's method. Do not use `gh pr merge` for Stack-owned pull
requests.

Read `merge.status` in the JSON result. `merged` means the merge completed;
`enqueued` means GitHub queued it; `pending` means the asynchronous merge is
still unresolved. A successful exit alone does not mean the Stack merged.
`--timeout <duration>` bounds polling, not the server operation, and does not
cancel a merge when it expires.

Preserve the returned pull request number and merge UUID for pending operations
or polling errors. Resume observation without submitting another merge:

```console
wt-stack --json --stack <stack> merge --resume <uuid> --pr <number>
```

Do not combine `--resume` with `--through` or `--merge-method`. If GitHub
reports an existing operation, inspect it with `--resume`; do not assume it uses
the newly requested method. Report queued or pending work as such and wait for
actual GitHub merge completion before cleanup.

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
- The merge status and, when pending, the pull request number, UUID, and resume
  command.
- Any paused rebase and the exact worktree that needs conflict resolution.
- Any prerequisite failure that forced the single-branch fallback.
