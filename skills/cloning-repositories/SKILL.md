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
git --git-dir=<repo>/.git config --get core.bare
```

The command should print `true`. If it prints `false`, or if `git -C <repo>
worktree add main` reports that `main` is already used by the root checkout,
the repository was cloned with raw Git. Remove the bad clone and repeat the
clone with the explicit bare form.

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

For task branches, use the worktree convention from `$using-git-worktrees`.

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
