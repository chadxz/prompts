# Shared helpers for tools keyed by the current agent harness session.
#
# The op-tmux helper and cleanup hook both use these functions so they agree
# on how to resolve the harness/thread id, validate it as a tmux session name,
# and derive the private tmux socket path for that session.

harness_session_id_from_json() {
  local payload="$1"

  if [[ -z "$payload" ]] || ! command -v python3 >/dev/null 2>&1; then
    return 1
  fi

  python3 -c '
import json
import sys

preferred_keys = (
    "session_id",
    "sessionId",
    "harness_session_id",
    "harnessSessionId",
    "thread_id",
    "threadId",
    "conversation_id",
    "conversationId",
)

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)


def find_value(value):
    if isinstance(value, dict):
        for key in preferred_keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate

        for child in value.values():
            candidate = find_value(child)
            if candidate:
                return candidate

    if isinstance(value, list):
        for child in value:
            candidate = find_value(child)
            if candidate:
                return candidate

    return None


session_id = find_value(data)
if not session_id:
    sys.exit(1)

print(session_id)
' <<<"$payload"
}

harness_session_id_from_env_or_stdin() {
  local candidate=""

  local env_name
  for env_name in \
    HARNESS_SESSION_ID \
    AGENT_SESSION_ID \
    CODEX_SESSION_ID \
    CODEX_THREAD_ID \
    CLAUDE_SESSION_ID \
    CLAUDE_CODE_SESSION_ID \
    CURSOR_SESSION_ID \
    PI_SESSION_ID \
    THREAD_ID \
    SESSION_ID; do
    candidate="$(printenv "$env_name" 2>/dev/null || true)"
    if [[ -n "$candidate" ]]; then
      print -r -- "$candidate"
      return 0
    fi
  done

  if [[ ! -t 0 ]]; then
    local stdin_payload
    stdin_payload="$(cat)"
    candidate="$(harness_session_id_from_json "$stdin_payload" 2>/dev/null || true)"
    if [[ -n "$candidate" ]]; then
      print -r -- "$candidate"
      return 0
    fi
  fi

  return 1
}

harness_tmux_session_name_is_safe() {
  local session_id="$1"

  [[ -n "$session_id" ]] || return 1
  [[ "$session_id" =~ '^[A-Za-z0-9_.-]+$' ]] || return 1
}

harness_tmux_socket_path() {
  local session_id="$1"
  local socket_dir="${OP_TMUX_SOCKET_DIR:-/tmp/op-tmux}"
  local socket_token

  if command -v python3 >/dev/null 2>&1; then
    socket_token="$(
      python3 -c 'import hashlib, sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:24])' "$session_id"
    )"
  else
    socket_token="$(printf '%s' "$session_id" | cksum | awk '{ print $1 }')"
  fi

  mkdir -p "$socket_dir"
  print -r -- "${socket_dir%/}/${socket_token}.sock"
}

harness_tmux_target() {
  local session_id="$1"

  print -r -- "=${session_id}"
}

harness_tmux_pane_target() {
  local session_id="$1"

  print -r -- "=${session_id}:"
}

harness_shell_quote() {
  local value="$1"

  printf "'"
  printf "%s" "$value" | sed "s/'/'\\\\''/g"
  printf "'"
}
