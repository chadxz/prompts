#!/usr/bin/env zsh
#
# Run one command inside a harness-scoped tmux server started under `op run`.
#
# This is the implementation for the run-op-in-tmux skill. It pairs with
# ../../../hooks/cleanup-harness-tmux-session.zsh, which tears down the same
# tmux server at the end of the agent turn. See ../SKILL.md for the workflow
# agents should follow.

set -euo pipefail

script_dir="${0:A:h}"

# shellcheck source=../../../lib/harness-session.zsh
source "${script_dir:h:h:h}/lib/harness-session.zsh"

usage() {
  cat <<'EOF'
Usage:
  op-tmux.zsh [--env-file FILE] [--shell SHELL] [--timeout SECONDS] -- 'command'
EOF
}

require_session_id() {
  local session_id="$1"

  if [[ -z "$session_id" ]]; then
    print -r -- "Could not resolve a harness session id." >&2
    return 1
  fi

  if ! harness_tmux_session_name_is_safe "$session_id"; then
    print -r -- "Unsafe harness session id for tmux: $session_id" >&2
    return 1
  fi
}

require_command() {
  local command="$1"

  if [[ -z "$command" ]]; then
    usage >&2
    return 2
  fi
}

require_tmux() {
  if ! command -v tmux >/dev/null 2>&1; then
    print -r -- "tmux is required." >&2
    return 1
  fi
}

require_op() {
  if ! command -v op >/dev/null 2>&1; then
    print -r -- "1Password CLI 'op' is required." >&2
    return 1
  fi
}

require_perl() {
  if ! command -v perl >/dev/null 2>&1; then
    print -r -- "perl is required for op-tmux timeout handling." >&2
    return 1
  fi
}

require_timeout() {
  local timeout="$1"

  if [[ ! "$timeout" =~ '^[0-9]+$' ]] || (( timeout < 1 )); then
    print -r -- "--timeout must be a positive integer number of seconds." >&2
    return 2
  fi
}

tmux_socket_path() {
  local session_id="$1"

  harness_tmux_socket_path "$session_id"
}

tmux_command() {
  local session_id="$1"
  shift

  tmux -S "$(tmux_socket_path "$session_id")" "$@"
}

session_shell_path() {
  local session_id="$1"
  local fallback_shell="$2"
  local configured_shell

  configured_shell="$(
    tmux_command "$session_id" show-environment \
      -t "$(harness_tmux_target "$session_id")" OP_TMUX_SHELL 2>/dev/null |
      sed -n 's/^OP_TMUX_SHELL=//p'
  )"

  if [[ -n "$configured_shell" ]]; then
    print -r -- "$configured_shell"
  else
    print -r -- "$fallback_shell"
  fi
}

normalize_env_file() {
  local env_file="$1"

  if [[ -z "$env_file" ]]; then
    print -r -- ""
    return 0
  fi

  if [[ ! -f "$env_file" ]]; then
    print -r -- "Env file not found: $env_file" >&2
    return 1
  fi

  print -r -- "${env_file:A}"
}

existing_session_env_file() {
  local session_id="$1"
  local target

  target="$(harness_tmux_target "$session_id")"
  tmux_command "$session_id" show-environment \
    -t "$target" OP_TMUX_ENV_FILE 2>/dev/null |
    sed -n 's/^OP_TMUX_ENV_FILE=//p' || true
}

validate_existing_session_env() {
  local session_id="$1"
  local requested_env_file="$2"
  local recorded_env_file

  if [[ -z "$requested_env_file" ]]; then
    return 0
  fi

  recorded_env_file="$(existing_session_env_file "$session_id")"
  if [[ "$recorded_env_file" == "$requested_env_file" ]]; then
    return 0
  fi

  if [[ -z "$recorded_env_file" ]]; then
    print -r -- \
      "Existing op-tmux session was started without this --env-file." >&2
  else
    print -r -- \
      "Existing op-tmux session uses a different --env-file:" >&2
    print -r -- "  $recorded_env_file" >&2
  fi
  print -r -- "Cleanup the harness tmux session, then retry with:" >&2
  print -r -- "  --env-file $requested_env_file" >&2
  return 1
}

parse_args() {
  session_id="$(harness_session_id_from_env_or_stdin || true)"
  env_file=""
  shell_path="${SHELL:-/bin/zsh}"
  timeout="300"
  command_to_run=""

  local saw_separator="0"
  local -a command_parts=()
  local arg

  while (( $# > 0 )); do
    arg="$1"
    shift

    if [[ "$saw_separator" == "1" ]]; then
      command_parts+=("$arg")
      continue
    fi

    case "$arg" in
      --env-file=*)
        env_file="${arg#--env-file=}"
        ;;
      --env-file)
        if (( $# == 0 )); then
          print -r -- "--env-file requires a value." >&2
          return 2
        fi
        env_file="$1"
        shift
        ;;
      --shell=*)
        shell_path="${arg#--shell=}"
        ;;
      --shell)
        if (( $# == 0 )); then
          print -r -- "--shell requires a value." >&2
          return 2
        fi
        shell_path="$1"
        shift
        ;;
      --timeout=*)
        timeout="${arg#--timeout=}"
        ;;
      --timeout)
        if (( $# == 0 )); then
          print -r -- "--timeout requires a value." >&2
          return 2
        fi
        timeout="$1"
        shift
        ;;
      --)
        saw_separator="1"
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        print -r -- "Unknown option: $arg" >&2
        return 2
        ;;
    esac
  done

  if (( ${#command_parts[@]} != 1 )); then
    print -r -- "Pass the command as one quoted string after --." >&2
    return 2
  fi

  command_to_run="${command_parts[1]}"
}

ensure_session() {
  local session_id="$1"
  local env_file="$2"
  local shell_path="$3"
  local target
  local requested_env_file
  local lock_dir
  local lock_timeout
  local lock_deadline
  local start_status

  require_tmux
  require_op

  requested_env_file="$(normalize_env_file "$env_file")"

  target="$(harness_tmux_target "$session_id")"

  if tmux_command "$session_id" has-session -t "$target" 2>/dev/null; then
    if ! validate_existing_session_env "$session_id" "$requested_env_file"; then
      return 1
    fi
    return 0
  fi

  lock_dir="$(tmux_socket_path "$session_id").lock"
  lock_timeout="${OP_TMUX_LOCK_TIMEOUT:-60}"
  if [[ ! "$lock_timeout" =~ '^[0-9]+$' ]] || (( lock_timeout < 1 )); then
    lock_timeout="60"
  fi
  lock_deadline=$(( SECONDS + lock_timeout ))

  while ! mkdir "$lock_dir" 2>/dev/null; do
    if tmux_command "$session_id" has-session -t "$target" 2>/dev/null; then
      if ! validate_existing_session_env "$session_id" "$requested_env_file"; then
        return 1
      fi
      return 0
    fi

    if (( SECONDS >= lock_deadline )); then
      print -r -- "Timed out waiting for op-tmux startup lock:" >&2
      print -r -- "  $lock_dir" >&2
      return 124
    fi

    sleep 0.25
  done

  if tmux_command "$session_id" has-session -t "$target" 2>/dev/null; then
    rmdir "$lock_dir" 2>/dev/null || true
    if ! validate_existing_session_env "$session_id" "$requested_env_file"; then
      return 1
    fi
    return 0
  fi

  local -a op_command
  op_command=(op run)
  if [[ -n "$requested_env_file" ]]; then
    op_command+=(--env-file "$requested_env_file")
  fi
  op_command+=(
    --
    tmux -S "$(tmux_socket_path "$session_id")"
    new-session -d -s "$session_id" -- "$shell_path" -l
  )

  set +e
  "${op_command[@]}"
  start_status=$?
  set -e
  if (( start_status != 0 )); then
    rmdir "$lock_dir" 2>/dev/null || true
    return "$start_status"
  fi

  set +e
  tmux_command "$session_id" set-environment \
    -t "$target" OP_TMUX_SHELL "$shell_path"
  start_status=$?
  if (( start_status == 0 )); then
    tmux_command "$session_id" set-environment \
      -t "$target" OP_TMUX_ENV_FILE "$requested_env_file"
    start_status=$?
  fi
  set -e

  rmdir "$lock_dir" 2>/dev/null || true
  return "$start_status"
}

timeout_wrapper_perl() {
  cat <<'PERL'
use strict;
use warnings;

my ($timeout, $shell, $command) = @ARGV;
if ($timeout !~ /\A[0-9]+\z/ || $timeout < 1) {
  die "Invalid timeout: $timeout\n";
}

defined(my $pid = fork()) or die "fork: $!\n";
if ($pid == 0) {
  setsid() or die "setsid: $!\n";
  exec { $shell } $shell, "-lc", $command;
  die "exec $shell: $!\n";
}

my $timed_out = 0;
local $SIG{ALRM} = sub {
  $timed_out = 1;
  kill "TERM", -$pid;
  select undef, undef, undef, 2;
  kill "KILL", -$pid;
};

alarm($timeout);
my $waited = waitpid($pid, 0);
my $status = $?;
alarm(0);

if ($timed_out) {
  print STDERR "Timed out waiting for tmux command.\n";
  exit 124;
}
if ($waited == -1) {
  die "waitpid failed: $!\n";
}
if ($status & 127) {
  exit(128 + ($status & 127));
}
exit($status >> 8);
PERL
}

run_command() {
  local session_id="$1"
  local fallback_shell="$2"
  local timeout="$3"
  local command="$4"
  local perl_path
  local perl_code
  local run_shell_command
  local token
  local run_dir
  local status_file
  local command_status
  local run_status
  local shell_path

  require_perl
  shell_path="$(session_shell_path "$session_id" "$fallback_shell")"

  token="${RANDOM}-${RANDOM}-$$"
  run_dir="${TMPDIR:-/tmp}/op-tmux-runs"
  status_file="${run_dir}/op-tmux-${session_id}-${token}.status"
  mkdir -p "$run_dir"
  rm -f "$status_file"

  perl_path="$(command -v perl)"
  perl_code="$(timeout_wrapper_perl)"
  run_shell_command="$(harness_shell_quote "$perl_path")"
  run_shell_command+=" -MPOSIX=setsid -e $(harness_shell_quote "$perl_code")"
  run_shell_command+=" -- $(harness_shell_quote "$timeout")"
  run_shell_command+=" $(harness_shell_quote "$shell_path")"
  run_shell_command+=" $(harness_shell_quote "$command")"
  run_shell_command+=" 2>&1"
  run_shell_command+="; command_status=\$?"
  run_shell_command+="; printf '%s' \"\$command_status\""
  run_shell_command+=" > $(harness_shell_quote "$status_file")"
  run_shell_command+="; exit 0"

  set +e
  tmux_command "$session_id" run-shell "$run_shell_command"
  run_status=$?
  set -e

  if (( run_status != 0 )); then
    rm -f "$status_file"
    return "$run_status"
  fi

  if [[ ! -f "$status_file" ]]; then
    print -r -- "tmux command did not write an exit status." >&2
    return 1
  fi

  command_status="$(<"$status_file")"
  rm -f "$status_file"

  if [[ ! "$command_status" =~ '^[0-9]+$' ]]; then
    print -r -- "tmux command wrote an invalid exit status." >&2
    return 1
  fi

  return "$command_status"
}

parse_args "$@"
require_session_id "$session_id"
require_command "$command_to_run"
require_timeout "$timeout"
ensure_session "$session_id" "$env_file" "$shell_path"
run_command "$session_id" "$shell_path" "$timeout" "$command_to_run"
