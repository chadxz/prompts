# Reviewing with Codex CLI

Read this when the peer reviewer is Codex CLI. Flags and event shapes here were
verified against `codex-cli` 0.144.1.

## Invoke

Run detached from the worktree, with every scratch file under `~/tmp`. Events
stream to one file and the final message lands in another:

```bash
cd "$WORKTREE"
nohup codex exec \
  --model "$MODEL" \
  --sandbox read-only \
  --cd "$WORKTREE" \
  --ephemeral \
  --json \
  --output-last-message "$review_dir/final.md" \
  -c 'tools.web_search=true' \
  "$(cat "$review_dir/brief.txt")" \
  > "$review_dir/review.jsonl" 2>&1 &
echo "$!" > "$review_dir/review.pid"
```

`--output-last-message` is the reason Codex is the easiest peer to collect from:
the final review lands in a plain file, so no extraction step can truncate or
misparse it.

Set reasoning effort through config rather than a dedicated flag, for example
`-c model_reasoning_effort="xhigh"`. Discover valid models with `codex --help`
and the account's configured provider rather than assuming an identifier.

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

The session also exposes `collaboration.spawn_agent`,
`collaboration.wait_agent`, and related delegation tools. There is no flag that
removes them, so state the one-hop rule in the brief explicitly: the peer must
not spawn agents, delegate, or invoke another agent CLI.

## Purpose-Built Review Mode

`codex exec review` accepts `--uncommitted`, `--base <BRANCH>`, or
`--commit <SHA>` and scopes the diff itself. It is a reasonable choice when the
review is exactly "the changes on this branch" and the brief adds no scope of
its own. Prefer plain `codex exec` when the brief carries accepted decisions,
non-goals, validation evidence, and a custom output contract, because those
survive better as an explicit prompt.

## Collect

The final review is already a file:

```bash
cat "$review_dir/final.md"
```

Confirm the run actually finished before trusting it. A completed run exits
zero, emits a `turn.completed` event, and leaves a non-empty final-message file:

```bash
wait "$(cat "$review_dir/review.pid")"; exit_code=$?
completed=$(jq -Rr 'fromjson? // empty | select(.type=="turn.completed") | .type' "$review_dir/review.jsonl" | wc -l)
if [ "$exit_code" -ne 0 ] || [ "$completed" -eq 0 ] || [ ! -s "$review_dir/final.md" ]; then
  echo "FAILED exit=$exit_code turn_completed=$completed"
fi
```

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
