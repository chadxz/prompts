#!/usr/bin/env zsh
#
# Codex Stop hook for op-tmux sessions.
#
# skills/run-op-in-tmux/scripts/op-tmux.zsh starts a private tmux server named
# after the current harness/thread id. This hook resolves that same id and kills
# the server at the end of the agent turn so resolved 1Password credentials do
# not outlive the delegated work.

set -euo pipefail

script_dir="${0:A:h}"

# shellcheck source=../lib/harness-session.zsh
source "${script_dir:h}/lib/harness-session.zsh"

session_id="$(harness_session_id_from_env_or_stdin || true)"

if [[ -z "$session_id" ]]; then
  exit 0
fi

if ! harness_tmux_session_name_is_safe "$session_id"; then
  print -r -- "Skipping tmux cleanup for unsafe harness session id." >&2
  exit 0
fi

if ! command -v tmux >/dev/null 2>&1; then
  exit 0
fi

socket_path="$(harness_tmux_socket_path "$session_id")"

if tmux -S "$socket_path" has-session -t "$(harness_tmux_target "$session_id")" 2>/dev/null; then
  tmux -S "$socket_path" kill-server 2>/dev/null || true
fi

rm -f "$socket_path"
rm -rf "$socket_path.lock"
