# wt-stack

`wt-stack` manages stacked branches when a repository uses a bare Git directory
with sibling worktrees. It keeps one stack definition in the repository's common
Git directory, runs every rebase in the worktree that owns the affected branch,
and delegates GitHub's remote Stack operations to
[`github/gh-stack`](https://github.com/github/gh-stack).

This fills the local coordination gap in `gh-stack`: branch ownership remains
with Git worktrees, while GitHub remains the source of truth for pull requests
and the Stack itself.

## Requirements

- Git
- [mise](https://mise.jdx.dev/)
- [GitHub CLI](https://cli.github.com/) authenticated for the repository
- `gh-stack`, installed with `gh extension install github/gh-stack`
- Access to GitHub's Stacked Pull Requests preview for the target repository

Run `wt-stack doctor --json` in a worktree to verify the local extension and
repository preview access.

## Install

The repository setup scripts build the CLI into `~/.local/bin/wt-stack`.
To install it directly:

```console
mise trust apps/wt-stack/mise.toml
mise install -C apps/wt-stack
mise run -C apps/wt-stack install
```

## Workflow

Adopt an existing bottom-to-top branch chain:

```console
wt-stack init --name delivery feature/api feature/ui
```

Create the next branch in a sibling worktree:

```console
wt-stack --stack delivery add feature/docs
```

Inspect the stack from any sibling worktree or the bare repository container:

```console
wt-stack status
wt-stack status --json
```

Rebase every active branch onto the latest trunk and then its preceding active
branch:

```console
wt-stack --stack delivery rebase
```

If Git reports a conflict, the JSON error identifies the owning worktree and
provides the exact continuation commands. Resolve and stage files there, then
continue the entire cascade:

```console
wt-stack continue
```

To restore every branch to its pre-rebase commit:

```console
wt-stack abort
```

Push branches with explicit leases and create or update the GitHub Stack:

```console
wt-stack --stack delivery submit
```

For the normal update loop, refresh pull request state, cascade the rebase,
push, and update the remote Stack with one command:

```console
wt-stack --stack delivery sync
```

## Agent interface

Use `--json` for stable machine-readable results. Successful mutations report
`"status": "ok"`; `--dry-run` reports `"status": "planned"`. A paused rebase
returns exit code `3` and includes the branch, worktree, `continue`, and `abort`
fields. Other failures return exit code `1`.

Local state is stored in `<git-common-dir>/wt-stack.json`, so every linked
worktree sees the same stack and rebase session. A repository-wide file lock and
atomic writes protect concurrent agents from corrupting that state.

`push`, `submit`, and `sync` refuse dirty branch worktrees. Rewritten branches
are pushed atomically with one explicit `--force-with-lease` per remote ref. The
CLI never force-pushes the trunk branch.

## Development

Run the complete local validation suite:

```console
mise run -C apps/wt-stack ci
```
