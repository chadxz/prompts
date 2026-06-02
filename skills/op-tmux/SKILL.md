---
name: op-tmux
description:
  Run 1Password CLI `op run` work inside a tmux session named after the
  current agent harness session or thread id. Use when commands need
  1Password-resolved environment variables across multiple tool calls, when
  Touch ID should be approved once for a turn, or when Datadog/API credentials
  are stored as `op://` references.
allowed-tools: ["Bash", "Read", "Grep"]
---

# Op Tmux

Use this skill when a task needs repeated shell commands that depend on
1Password CLI secret references. The tmux session name must match the current
harness session id. Prefer the bundled script instead of hand-rolling tmux
commands.

The helper has one normal interaction pattern: pass a single quoted command
string after `--`. On first use, it starts a dedicated tmux server for the
harness session under `op run`; later calls reuse that session. Each call uses
`tmux run-shell` to execute an isolated shell command that inherits the resolved
environment from the server. This avoids repeated 1Password prompts, supports
parallel calls, and keeps agent-owned credentialed tmux state separate from the
user's normal tmux server.

Resolve this skill package on disk, then run the helper by relative path from
the skill directory:

```bash
scripts/op-tmux.zsh
```

Do not assume a particular installed Codex skills path.

## Session id

The script resolves the session id from common harness environment variables. In
Codex app sessions, the usual source is `CODEX_THREAD_ID`. Do not invent a
friendly session name, pass an override, or add a prefix; the cleanup hook
expects the tmux session name to be the harness id.

## Run

Run commands with:

```bash
scripts/op-tmux.zsh --env-file ~/.config/codex/datadog.env -- \
  'printenv DD_SITE'
```

If there is no env file, omit `--env-file`. `op run` will still resolve any
`op://` references present in the inherited environment.

If credentialed work needs an env file, include `--env-file` on the first helper
call. A running session will reject a later call that asks for a different env
file, because the resolved credentials come from the original tmux server
environment.

The user may need to approve Touch ID or another 1Password prompt. The prompt
may not be visible in command output, so wait for the user to approve if the
session appears stalled.

The script streams combined command stdout and stderr through `tmux run-shell`
and exits with the command status. Multiple invocations can run in parallel
against the same session without sharing shell state.

Never print secret variables. Use presence checks such as `${DD_API_KEY:+set}`
instead.

If a command needs state, include that state in the single command string, for
example `cd app && export FEATURE=1 && ./script`. Do not depend on hidden shell
state across invocations.

## Cleanup

The Codex Stop hook kills the tmux session at the end of the turn.
