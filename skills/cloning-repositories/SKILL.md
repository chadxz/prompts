---
name: cloning-repositories
description:
  Clones Git repositories into Chad's local repository container layout. Use
  when cloning, setting up, migrating, or explaining repositories that should
  store the bare Git repository at repo/.git and worktrees directly under the
  repo container.
---

# Cloning Repositories

Use this workflow when cloning repositories on Chad's computer.

## Default Layout

Repositories live as container directories with a bare Git repository at
`<repo>/.git` and one or more worktrees directly under `<repo>/`.

For example, cloning `https://github.com/chadxz/personal-website` should create
this layout:

```text
personal-website/.git
personal-website/main
personal-website/my-task
```

Do not use a normal checkout at the repository root. The root is the repository
container and the root `.git` directory is bare.

## Clone Commands

Before relying on a plain `git clone`, verify that Chad's wrapper is the first
Git executable on `PATH`:

```bash
type -a git
```

The first result must be the prompts wrapper, usually:

```text
git is /Users/chad/src/personal/prompts/main/bin/git
```

If another Git executable comes first, such as `/opt/homebrew/bin/git` or
`/usr/bin/git`, the wrapper will not run. Use the explicit bare clone form
instead:

```bash
git clone --bare <url> <repo>/.git
```

Use the normal command:

```bash
git clone https://github.com/chadxz/personal-website
```

Chad's `git` wrapper rewrites that to:

```bash
git clone --bare \
  https://github.com/chadxz/personal-website \
  personal-website/.git
```

When a custom directory name is needed, pass the container directory:

```bash
git clone https://github.com/chadxz/personal-website site
```

That clones the bare repository into `site/.git`.

If the wrapper is unavailable, run the bare clone form directly:

```bash
git clone --bare <url> <repo>/.git
```

After cloning, confirm the root `.git` directory is a bare repository before
adding worktrees:

```bash
git -C <repo> rev-parse --is-bare-repository
```

The command should print `true`. If it prints `false`, or if
`git -C <repo> worktree add main` reports that `main` is already used by the
root checkout, the repository was cloned with raw Git. Remove the bad clone and
repeat the clone with the explicit bare form.

## Where `core.bare` Lives

The wrapper finishes a clone by enabling `extensions.worktreeConfig` and moving
`core.bare = true` out of the shared `<repo>/.git/config` into the container's
own `<repo>/.git/config.worktree`. Git reads that file only for the container,
so the container stays bare while every worktree is a normal work tree.

This matters because Git applies a shared `core.bare = true` to every linked
worktree once `extensions.worktreeConfig` is enabled, and tools such as
Codex.app and Claude Code enable that extension on their own when they create
worktrees. In a container that still keeps `core.bare` in the shared config,
that flip makes `git status` in every worktree fail with "this operation must be
run in a work tree" until each worktree gets its own `core.bare = false`.

When using the explicit bare clone form without the wrapper, apply the same
layout by hand:

```bash
git -C <repo> config extensions.worktreeConfig true
git -C <repo> config --worktree core.bare true
git -C <repo> config --unset core.bare
```

### Repairing An Existing Container

If worktrees in an existing container report `true` from
`git rev-parse --is-bare-repository`, or `git status` fails there with "this
operation must be run in a work tree", check where `core.bare` is set:

```bash
git -C <repo> config --show-origin --get-all core.bare
```

If the only origin is `<repo>/.git/config`, run the three commands above. The
container keeps reporting bare, the worktrees recover immediately, and fresh
`git worktree add` calls need no per-worktree override. Do not fix this by
unsetting `extensions.worktreeConfig`; the next tool that creates a worktree
turns it back on and reintroduces the failure.

## First Worktree

After cloning, add the default branch worktree at `main` directly under the repo
container:

```bash
git -C personal-website worktree add main
```

For a non-`main` default branch, still use `main` as the worktree directory and
pass the branch name explicitly:

```bash
git -C my-repo worktree add main trunk
```

For task branches, use the worktree convention from the `$using-git-worktrees`
skill. That skill routes work with multiple ordered review units to the
`$managing-stacked-changes` skill. The bare repository and sibling-worktree
layout created here is the native layout for `wt-stack`.

## Bypassing The Override

Use one of these when raw Git clone behavior is intentionally needed:

```bash
GIT_BARE_CLONE_BYPASS=1 git clone <url>
git clone --no-bare <url>
git clone --bare <url> <target>
```

Explicit `--bare`, `--mirror`, `--no-bare`, and `--separate-git-dir` clone
commands pass through unchanged.

## Setup

The wrapper lives at `bin/git` in the prompts repo. Run one of the prompts setup
scripts after installing or updating prompts so `bin/` is first on `PATH`.
