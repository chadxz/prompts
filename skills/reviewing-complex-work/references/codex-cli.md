# Reviewing with Codex CLI

Read this when the peer reviewer is Codex CLI. Flags and event shapes here were
verified against `codex-cli` 0.144.1.

## Select the Model

Ask Codex for the authenticated account's current model catalog. `codex --help`
documents the model flag, but it does not list the models the account can use:

```bash
codex debug models | jq -r '
  .models[]
  | select(.visibility == "list")
  | [
      .slug,
      .default_reasoning_level,
      ([.supported_reasoning_levels[]?.effort] | join(","))
    ]
  | @tsv
'
```

Choose the exact slug for the newest permitted flagship or coding model, then
choose the highest reasoning level it reports that stays single-agent. Exclude
`ultra`, because it adds automatic delegation. Set those values as `MODEL` and
`REASONING_EFFORT` for the invocation below.

## Invoke

Run detached from the worktree, with every scratch file under `~/tmp`. Events
stream to one file and the final message lands in another. Launch through Bash
so the wrapper can persist Codex's exit status after the original shell returns:

```bash
cd "$WORKTREE"
nohup bash -c '
  codex exec \
    --model "$1" \
    --sandbox read-only \
    --cd "$2" \
    --ephemeral \
    --json \
    --output-last-message "$3/final.md" \
    --disable multi_agent \
    -c "model_reasoning_effort=\"$4\"" \
    -c "approval_policy=\"never\"" \
    -c "tools.web_search=true" \
    - < "$3/brief.txt" \
    > "$3/review.jsonl" 2>&1
  review_exit_code=$?
  printf "%s\n" "$review_exit_code" > "$3/review.exit.tmp"
  mv "$3/review.exit.tmp" "$3/review.exit"
  exit "$review_exit_code"
' _ "$MODEL" "$WORKTREE" "$review_dir" "$REASONING_EFFORT" \
  > "$review_dir/launcher.log" 2>&1 &
printf '%s\n' "$!" > "$review_dir/review.pid"
```

`--output-last-message` is the reason Codex is the easiest peer to collect from:
the final review lands in a plain file, so no extraction step can truncate or
misparse it.

The brief uses stdin instead of command substitution, so its size is not bound
by the shell's argument limit. `approval_policy="never"` returns blocked actions
to the peer immediately rather than waiting for a human who is not present. The
PID names the launcher for deliberate interruption; `review.exit` is the
terminal status to trust during collection.

## Read-Only Enforcement

`--sandbox read-only` is the strongest enforcement of the three peers, because
it is applied by the sandbox rather than by prompt or tool policy. The session
still lists `apply_patch`, but writes fail at the sandbox boundary.

Do not pass `--dangerously-bypass-approvals-and-sandbox`. It removes exactly the
property that makes the review safe.

`--add-dir` grants write access alongside the workspace, so it is the wrong tool
for a read-only review. Codex needs no grant to read scratch files: under
`--sandbox read-only` the whole filesystem is readable, so a brief staged in
`~/tmp` and any ledger or artifact beside it are already reachable. Name those
paths as readable roots in the brief so the peer knows the intended scope, and
do not add a directory flag for them.

`--ephemeral` keeps the peer from persisting session files, which suits a
one-shot review.

## Tools

Under `--sandbox read-only` with `tools.web_search=true`, the session reports
shell execution (`exec`, `exec_command`, `write_stdin`, `wait`), `web__run` for
web search, `view_image`, and MCP resource readers (`list_mcp_resources`,
`read_mcp_resource`, `list_mcp_resource_templates`). That is a good review
surface: shell covers `git`, `gh`, and file inspection, and web search covers
advisories and upstream behavior.

Codex enables multi-agent tools by default. The invocation disables the
`multi_agent` feature, which removes those tools and enforces the one-hop rule
at the harness boundary. Keep the matching instruction in the brief as defense
in depth: the peer must not delegate or invoke another agent CLI.

## Purpose-Built Review Mode

`codex exec review` accepts `--uncommitted`, `--base <BRANCH>`, or
`--commit <SHA>` and scopes the diff itself. It is a reasonable choice when the
review is exactly "the changes on this branch" and the brief adds no scope of
its own. Prefer plain `codex exec` when the brief carries accepted decisions,
non-goals, validation evidence, and a custom output contract, because those
survive better as an explicit prompt.

## Collect

The final review lands in `final.md`, but do not read it until the run is known
to have finished. A completed run exits zero, emits a `turn.completed` event,
and leaves a non-empty final-message file:

```bash
if [ ! -s "$review_dir/review.exit" ]; then
  if [ -s "$review_dir/review.pid" ] && \
      kill -0 "$(cat "$review_dir/review.pid")" 2>/dev/null; then
    echo "RUNNING"
    exit 0
  else
    echo "FAILED missing terminal status"
    exit 1
  fi
fi

review_exit_code=$(cat "$review_dir/review.exit")
completed=$(
  jq -Rr 'fromjson? // empty
    | select(.type=="turn.completed") | .type' \
    "$review_dir/review.jsonl" | wc -l
)
if [ "$review_exit_code" -ne 0 ] || [ "$completed" -eq 0 ] || \
    [ ! -s "$review_dir/final.md" ]; then
  echo "FAILED exit=$review_exit_code turn_completed=$completed"
  exit 1
else
  cat "$review_dir/final.md"
fi
```

Do not call `wait` from the collecting shell. Once the detached launcher has
outlived the shell that started it, its PID is not that shell's child and `wait`
returns 127 instead of Codex's exit status.

Observed event types are `thread.started`, `turn.started`, `item.completed`, and
`turn.completed`. The `turn.completed` event carries a `usage` object with
`input_tokens`, `cached_input_tokens`, `output_tokens`, and
`reasoning_output_tokens`.

## Inspect While It Runs

Completed items carry `.item.type`, so progress needs no item contents:

```bash
jq -Rr 'fromjson? // empty | select(.type=="item.completed") | .item.type' "$review_dir/review.jsonl" \
  | awk '{n++; last=$0} END{print (n+0)" items, last="last}'
```

Narration so far comes from the agent-message items:

```bash
jq -Rr 'fromjson? // empty | select(.type=="item.completed")
        | select(.item.type=="agent_message") | .item.text' "$review_dir/review.jsonl"
```

Treat that text as provisional and use it to steer the run, not to collect
findings. The final review is whatever lands in the `--output-last-message`
file.

`agent_message` is the only item type confirmed here. Other item types carry
their own fields, so a view of what the peer is currently inspecting has to be
built against a real review's stream; list `.item.type` first and project from
what that shows.
