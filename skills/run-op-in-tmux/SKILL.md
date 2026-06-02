---
name: run-op-in-tmux
description:
  Runs shell commands under 1Password CLI `op run` inside a harness-scoped
  tmux session. Use when commands need to resolve `op://` references in the
  environment or .env files.
allowed-tools: ["Bash", "Read", "Grep"]
---

# Run op in tmux

Use this skill when a task needs shell commands that depend on 1Password CLI
secret references, especially repeated commands that should share one
credentialed environment. Prefer the bundled script instead of hand-rolling
tmux or `op run` commands.

Do not use this skill for one-off non-secret commands, commands that can safely
receive explicit non-secret environment values, or ordinary interactive tmux
work unrelated to harness-scoped credentials.

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

## Default workflow

1. Resolve this skill package on disk and run commands from the skill
   directory, or invoke the script by its resolved absolute path.
2. Include `--env-file` on the first helper call when credentialed work depends
   on a file of `op://` references.
3. Start with a non-secret presence check when credentials matter, such as
   `printf '%s\n' "${DD_API_KEY:+set}"`.
4. Run each task command as one quoted string after `--`.
5. Use `--timeout SECONDS` for long commands instead of wrapping the helper in a
   separate timeout tool.
6. Report command results normally, but never print secret values.

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

If the helper says it cannot resolve a harness session id, stop using the helper
for that task and explain the missing session context. Do not make up a session
name.

If the helper rejects an env file because the session was already started with
different credentials, follow its cleanup instruction or wait for the current
turn cleanup hook before retrying with the intended env file.

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

## Maintenance validation

After editing this skill or the helper script, run:

```bash
validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator"
uv run "$validator/scripts/quick_validate.py" skills/run-op-in-tmux
zsh -n skills/run-op-in-tmux/scripts/op-tmux.zsh
skills/run-op-in-tmux/scripts/op-tmux.zsh --help
```

Do not run a real credentialed command as validation unless the user asked for
credentialed work or the task already requires those credentials.
