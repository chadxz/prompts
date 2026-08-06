# Reviewing with Cursor Agent

Read this when the peer reviewer is Cursor Agent. Flags and event shapes here
were verified against `cursor-agent` 2026.07.23-e383d2b.

## Invoke

Run detached from the worktree, with every scratch file under `~/tmp`:

```bash
cd "$WORKTREE"
nohup cursor-agent -p \
  --model "$MODEL" \
  --mode ask \
  --sandbox enabled \
  --trust \
  --workspace "$WORKTREE" \
  --add-dir "$HOME/tmp" \
  --output-format stream-json \
  "$(cat "$review_dir/brief.txt")" \
  > "$review_dir/review.jsonl" 2>&1 &
echo "$!" > "$review_dir/review.pid"
```

List models with `cursor-agent models` and pin an exact identifier. The account
exposes several providers, so Cursor is a useful peer when the host and the
other installed CLI share a provider. Its parameterized model syntax accepts
bracket overrides, for example
`'claude-opus-4-8[context=1m,effort=high,fast=false]'`.

`--trust` is required for a non-interactive run in a directory Cursor has not
seen. Without it the process exits non-zero and prints a prompt to run
interactively or pass `--trust`, `--yolo`, or `-f`, which is easy to mistake for
a model failure.

## Read-Only Enforcement

`-p` on its own has access to all tools, including write and shell, so a mode
flag is mandatory for a review:

- `--mode ask` for question-and-answer style review;
- `--mode plan` for read-only analysis that proposes changes without making
  them.

Either keeps the session read-only. Add `--sandbox enabled` so sandboxing does
not depend on local configuration.

Never pass `--force`, `--yolo`, or `-f`. They are the opposite of what a review
needs, and `--yolo` is only an alias for `--force`.

Reads are scoped to the workspace, so pass `--add-dir "$HOME/tmp"` whenever the
brief points at something staged there. Without it the peer cannot open the file
and will review the wrong scope.

## Tools

In `--mode ask` the session reports `Shell`, `Glob`, `Grep`, `Read`,
`WebSearch`, `WebFetch`, `Task`, `TodoWrite`, MCP access (`GetMcpTools`,
`FetchMcpResource`, `CallMcpTool`), and image generation, alongside editing
tools that the mode gates.

That covers a review well: shell for `git` and `gh`, the search tools for
source, and web search and fetch for advisories and upstream behavior.

Two cautions:

- The registry lists `Write`, `Delete`, `StrReplace`, and `EditNotebook` even in
  read-only mode. The mode gates them, and `--sandbox enabled` backs that up,
  but the mutation check in `SKILL.md` remains the real guarantee.
- `Task` allows delegation, and no flag removes it. State the one-hop rule in
  the brief: the peer must not spawn subagents, delegate, or invoke another
  agent CLI.

## Collect

Cursor's `stream-json` mirrors Claude Code's event shape, so the same projection
works:

```bash
jq -Rr 'fromjson? // empty | select(.type=="result")
        | if .subtype=="success" then .result
          else "FAILED subtype=\(.subtype) is_error=\(.is_error) duration_ms=\(.duration_ms)"
          end' "$review_dir/review.jsonl"
```

Observed event types are `system` with `subtype: init`, `user`, `assistant`, and
`result`. A completed review is `subtype: success` with `is_error: false`, and
`.result` holds the review text. The `result` event also carries `duration_ms`,
`duration_api_ms`, `session_id`, `request_id`, and a `usage` object with
`inputTokens`, `outputTokens`, `cacheReadTokens`, and `cacheWriteTokens`.

The `system` init event reports the resolved `model`, `permissionMode`, and
`cwd`. Check it once on the first run to confirm the mode and model actually
took effect, since a mistyped model can otherwise resolve to a default.

`--stream-partial-output` adds text deltas. Leave it off: it multiplies stream
volume without improving the extraction, which reads only the final event.

## Heartbeat

Cursor emits one `assistant` event per step, so line growth tracks progress:

```bash
printf '%s events, last=%s\n' "$(wc -l < "$review_dir/review.jsonl")" \
  "$(tail -1 "$review_dir/review.jsonl" | jq -Rr 'fromjson? // empty | .type // "partial"')"
```

A tool-name heartbeat equivalent to the Claude Code one is likely available
through `.message.content[]`, but the tool-call shape was not confirmed here.
Verify it against a real review before relying on it, and use the event-count
form above until then.
