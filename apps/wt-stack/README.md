# wt-stack

`wt-stack` manages stacked branches in repositories that use a bare Git
directory with sibling worktrees. It runs each rebase in the worktree that owns
the branch, pushes rewritten branches with explicit leases, and creates or
updates GitHub pull requests and Stacks without executing `gh`.

The command follows GitHub's
[official Stacked Pull Requests documentation][github-stacks-docs]. Git remains
the source of truth for branches and worktrees. GitHub remains the source of
truth for pull requests and the remote Stack.

`wt-stack` provides the non-interactive lifecycle needed by agents working in
the sibling-worktree layout. It does not reproduce `gh stack`'s interactive
checkout, navigation, branch-restructuring, or pull request editor.

## Quick start

This example creates a two-branch stack named `delivery`, publishes it, handles
updates, and finishes after the pull requests merge.

Start in the worktree for the first feature branch. Confirm that GitHub
authentication and the Stacked Pull Requests preview are available:

```console
wt-stack doctor
```

Adopt the first branch. List multiple existing branches from bottom to top when
adopting a chain that already exists:

```console
wt-stack init --name delivery feature/api
```

Create the next branch and its sibling worktree on top of `feature/api`:

```console
wt-stack --stack delivery add feature/ui
wt-stack --stack delivery status
```

`status` prints the new worktree path. Change into that worktree, make the UI
changes, and commit them normally.

Publish the stack:

```console
wt-stack --stack delivery sync
```

`sync` refreshes pull request state, fetches the trunk branch, rebases the
active branches from bottom to top, pushes them atomically with explicit leases,
and creates or updates the GitHub Stack.

Continue working in either branch-owning worktree. Commit changes and run the
same command to update the stack:

```console
wt-stack --stack delivery sync
```

If a rebase pauses, resolve and stage the conflicts in the worktree printed by
`wt-stack`, then continue:

```console
wt-stack continue
```

Use `wt-stack abort` instead to stop the cascade and restore every branch to its
pre-rebase commit.

After GitHub merges each pull request, refresh local metadata:

```console
wt-stack --stack delivery refresh
```

Merged members stay in the recorded history and are excluded from later rebases,
pushes, and Stack updates. After the full Stack is merged, retire its GitHub and
local Stack records:

```console
wt-stack --stack delivery unstack
```

`unstack` preserves pull requests, branches, and worktrees. Remove clean merged
worktrees with `git worktree remove <path>` when they are no longer needed.

## Installation

Released archives are available from the repository's
[GitHub Releases](https://github.com/chadxz/prompts/releases). Install the
archive for your operating system and architecture, then place `wt-stack` on
`PATH`.

The repository setup scripts also install the command into
`~/.local/bin/wt-stack`. Install the pinned build tools, then build that binary
directly from this repository:

```console
mise trust apps/wt-stack/mise.toml
mise -C apps/wt-stack install
mise run //apps/wt-stack:install
```

## Requirements and compatibility

Runtime requirements:

- Git 2.31 or newer.
- macOS or Linux.
- A GitHub account previously authenticated by GitHub CLI.
- Access to GitHub's Stacked Pull Requests preview for the target repository.

`wt-stack` reads GitHub CLI's existing configuration and system-keychain
credential directly. The core `gh` binary and `gh-stack` extension do not need
to be installed after authentication has been configured.

Stacked Pull Requests is currently a private preview. The official
documentation links to GitHub's preview waitlist and is the source of truth for
GitHub-side feature availability and behavior.

`WT_STACK_GIT_BIN` may select an alternate Git executable for testing or
diagnosis. It is trusted as executable code and should be set only to a binary
you control.

GitHub.com is covered by the automated HTTP suite. GitHub Enterprise Server and
GitHub Enterprise Cloud subdomains use their corresponding API endpoints, but
the target host must expose the Stacks preview API. Windows is not currently
supported because repository locking uses Unix file locks.

## Global options

Global options may appear before any command:

- `--stack <name>` selects a Stack explicitly. It is required when the current
  branch does not identify one and more than one Stack exists.
- `--json` emits the versioned machine-readable result on standard output or
  standard error.
- `--dry-run` validates and plans a mutation without changing branches,
  worktrees, state, or remotes.
- `--version` prints the installed version.
- `--help` prints command help.

## Commands

### `doctor`

```console
wt-stack [--stack <name>] doctor
```

Checks repository discovery, GitHub authentication, remote resolution, and
Stacks preview availability. Run it before adopting the first Stack or when
authentication and preview errors are unclear.

### `init`

```console
wt-stack init [branches...] [--name <name>] [--remote <remote>] \
  [--base <branch>]
```

Adopts an existing linear branch chain. Branches must be listed from bottom to
top, checked out in sibling worktrees, and based on the preceding branch. When
no branch is provided, `init` adopts the current branch.

- `--name <name>` sets the local Stack name. It defaults to the first branch
  name.
- `--remote <remote>` selects the Git remote. It defaults to `origin`.
- `--base <branch>` selects the trunk branch on the remote. It defaults to
  `main`.

Successful initialization enables Git rerere for the repository and writes the
Stack to shared state.

### `add`

```console
wt-stack [--stack <name>] add <branch> [--path <path>]
```

Creates a branch on top of the current active Stack tip and checks it out in a
new sibling worktree.

- `--path <path>` selects the new worktree path. It defaults to a sanitized
  branch-name directory under the repository container. Relative paths are
  resolved from that container.

### `status`

```console
wt-stack [--stack <name>] status
```

Shows each recorded branch, current commit, owning worktree, dirty or drifted
state, and pull request state. Without `--stack`, it shows all Stacks.

### `rebase`

```console
wt-stack [--stack <name>] rebase [--no-fetch]
```

Rebases each active branch onto the latest trunk and then onto the preceding
active branch. Every branch must have a clean owning worktree.

- `--no-fetch` uses existing remote-tracking refs without fetching first.
  Fetching is enabled by default.

### `continue`

```console
wt-stack continue
```

Continues a paused cascading rebase after conflicts have been resolved and
staged in the reported worktree.

### `abort`

```console
wt-stack abort
```

Aborts the current rebase and restores every branch in the cascade to the commit
recorded before the rebase started.

### `push`

```console
wt-stack [--stack <name>] push
```

Pushes every active branch in one atomic Git operation. Rewritten branches use
an explicit `--force-with-lease` value derived from the last fetched remote
commit. The trunk branch is never force-pushed.

### `refresh`

```console
wt-stack [--stack <name>] refresh
```

Reads current pull request state from GitHub and saves it to local Stack state.
Use it after merges or changes made through GitHub.

### `submit`

```console
wt-stack [--stack <name>] submit
```

Pushes active branches, creates missing pull requests, repairs pull request
bases, and creates or additively updates the GitHub Stack. It does not rebase
branches first.

### `sync`

```console
wt-stack [--stack <name>] sync
```

Runs the normal update loop: `refresh`, `rebase`, `push`, and Stack submission.
Use it for routine publication after committing branch changes.

### `unstack`

```console
wt-stack [--stack <name>] unstack [--local]
```

Dissolves the matching Stack on GitHub and removes its local record. The
`delete` command is an alias. Pull requests, branches, commits, and worktrees
are never deleted.

- `--local` removes only the local Stack record and leaves GitHub unchanged.

GitHub may preserve pull requests that are queued for merge or have auto-merge
enabled. When that happens, `wt-stack` keeps local tracking and reports that the
Stack remains. Disable those settings or let the queued merges finish before
retrying.

### `completion`

```console
wt-stack completion <bash|fish|powershell|zsh> [--no-descriptions]
```

Generates a shell completion script. Follow the shell-specific instructions
from `wt-stack completion <shell> --help` to load it for the current session or
install it permanently.

- `--no-descriptions` omits command descriptions from completion candidates.

## Agent interface

`--json` emits schema version `1`. Successful mutations use `"status": "ok"`;
dry runs use `"status": "planned"`. A paused rebase writes a structured error to
standard error and exits with code `3`. Other errors exit with code `1`.
`unstack` reports `localRemoved` and, when GitHub was contacted,
`remoteRemoved`.

The complete contract is in [`docs/json-schema.json`](docs/json-schema.json).
Consumers should ignore unknown fields and reject unsupported `schemaVersion`
values.

Local state is stored in `<git-common-dir>/wt-stack.json`, which makes it
visible from every linked worktree. State and lock files are user-readable only.
A repository-wide lock and atomic replacement prevent concurrent processes from
corrupting state.

## Troubleshooting and recovery

Run `wt-stack doctor --json` first for authentication, repository, or preview
errors. Reauthenticate with GitHub CLI when no usable credential is available
for the remote host.

When a rebase pauses, do not start another Stack mutation. Resolve it with
`continue` or restore it with `abort`. Both commands use the repository-wide
session recorded before the cascade.

If `wt-stack` reports a state version newer than it supports, upgrade the
binary. Do not edit or downgrade the state file. For malformed state, preserve
`wt-stack.json` for diagnosis before restoring it from a known-good backup.

Atomic pushes require the remote to support atomic ref updates. A rejected lease
means the remote branch changed after the last fetch; inspect the remote changes
and rerun the operation instead of bypassing the lease.

## Project documentation

- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [MIT license](LICENSE)

[github-stacks-docs]: https://github.github.com/gh-stack/
