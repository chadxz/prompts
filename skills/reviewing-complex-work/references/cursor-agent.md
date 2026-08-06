# Reviewing with Cursor Agent

Read this when the peer reviewer is Cursor Agent. Flags and event shapes here
were verified against `cursor-agent` 2026.08.04-aaa8809.

## Select the Model

List the account catalog and pin an exact identifier:

```bash
cursor-agent models
```

Prefer the newest permitted flagship or coding model at the highest supported
single-agent thinking level. Current catalogs often expose that as a full slug
such as `claude-opus-5-thinking-xhigh` or `claude-opus-5-thinking-max`.
Parameterized models also accept quoted bracket overrides, for example
`'claude-opus-4-8[context=1m,effort=high,fast=false]'`. Do not pass a short
alias that may remap later.

Cursor exposes several providers, so it is a useful peer when the host and the
other installed CLI share a provider.

## Invoke

Run detached from the worktree, with every scratch file under `~/tmp`:

```bash
cd "$WORKTREE"
nohup cursor-agent -p \
  --model "$MODEL" \
  --mode ask \
  --force \
  --sandbox enabled \
  --trust \
  --workspace "$WORKTREE" \
  --add-dir "$HOME/tmp" \
  --output-format stream-json \
  "$(cat "$review_dir/brief.txt")" \
  > "$review_dir/review.jsonl" 2>&1 &
echo "$!" > "$review_dir/review.pid"
```

`--trust` is required for a non-interactive run in a directory Cursor has not
seen. Without it the process exits non-zero and prints a prompt to run
interactively or pass `--trust`, `--yolo`, or `-f`, which is easy to mistake for
a model failure.

Do not pass `-w` / `--worktree`. That creates a fresh isolated worktree and
reviews the wrong tree.

## Read-Only Enforcement

`-p` on its own has access to all tools, including write and shell, so a
read-only mode flag is mandatory. Use `--mode ask` for peer review. Ask mode is
Q&A-style and read-only; it matches the skill's verdict contract.

Do not use `--mode plan` for these reviews. Plan mode biases toward proposing a
plan instead of returning findings, and `--plan` under `-p` has historically
written files despite the read-only claim.

`--force` (`--yolo` / `-f`) is required with ask mode so readonly shell can run
under local allowlist configs. Without it, even `git status --short` returns
`permissionDenied` ("Command blocked by permissions configuration"), and the
review silently degrades to static `Read` / `Grep` / `Glob`. With
`--mode ask --force`, readonly shell succeeds while Write, StrReplace, and
write-shaped shell stay blocked by the mode.

Never pass `--force`, `--yolo`, or `-f` without also locking `--mode ask` and
`--sandbox enabled`. Bare force in agent mode is the opposite of a review.
`--yolo` is only an alias for `--force`.

Add `--sandbox enabled` so sandboxing does not depend on local configuration.
The mutation check in `SKILL.md` remains the real guarantee.

Never pass `--auto-review`. It can prompt mid-run and stalls a detached,
non-interactive review.

Reads are scoped to the workspace, so pass `--add-dir "$HOME/tmp"` whenever the
brief points at something staged there. Without it the peer cannot open the file
and will review the wrong scope.

Pass `--approve-mcps` only when the brief needs MCP tools that are not already
approved. Leave it off otherwise.

## Tools

In `--mode ask` the session reports `Shell`, `Glob`, `Grep`, `Read`,
`WebSearch`, `WebFetch`, `Task`, `TodoWrite`, MCP access (`GetMcpTools`,
`FetchMcpResource`, `CallMcpTool`), and image generation, alongside editing
tools that the mode gates.

With `--force`, that covers a review well: shell for `git` and `gh`, the search
tools for source, and web search and fetch for advisories and upstream behavior.

Two cautions:

- The registry lists `Write`, `Delete`, `StrReplace`, and `EditNotebook` even in
  ask mode. The mode gates them, and `--sandbox enabled` backs that up, but the
  mutation check in `SKILL.md` remains the real guarantee.
- `Task` allows delegation, and no flag removes it. State the one-hop rule in
  the brief: the peer must not spawn subagents, delegate, or invoke another
  agent CLI.

## Collect

Cursor's `stream-json` final event matches Claude Code's result shape:

```bash
jq -Rr 'fromjson? // empty | select(.type=="result")
        | if .subtype=="success" then .result
          else "FAILED subtype=\(.subtype) is_error=\(.is_error) duration_ms=\(.duration_ms)"
          end' "$review_dir/review.jsonl"
```

Observed event types are `system` with `subtype: init`, `user`, `thinking`,
`assistant`, `tool_call`, and `result`. A completed review is `subtype: success`
with `is_error: false`, and `.result` holds the review text. The `result` event
also carries `duration_ms`, `duration_api_ms`, `session_id`, `request_id`, and a
`usage` object with `inputTokens`, `outputTokens`, `cacheReadTokens`, and
`cacheWriteTokens`.

The `system` init event reports the resolved `model` and `cwd`. Check `model`
once on the first run, since a mistyped model can resolve to a default. Do not
use `permissionMode` to confirm ask mode: it stays `default` even when
`--mode ask` is set.

`--stream-partial-output` adds text deltas. Leave it off: it multiplies stream
volume without improving the extraction, which reads only the final event.

## Inspect While It Runs

Cursor emits `assistant` and `tool_call` events as it works, so line growth
tracks progress:

```bash
printf '%s events, last=%s\n' "$(wc -l < "$review_dir/review.jsonl")" \
  "$(tail -1 "$review_dir/review.jsonl" | jq -Rr 'fromjson? // empty | .type // "partial"')"
```

Narration so far:

```bash
jq -Rr 'fromjson? // empty | select(.type=="assistant")
        | .message.content[]? | select(.type=="text") | .text' "$review_dir/review.jsonl"
```

Tool names and inspected paths or commands use the top-level `tool_call` events,
not Claude Code's `.message.content[]` tool_use shape:

```bash
jq -Rr 'fromjson? // empty
        | select(.type=="tool_call" and .subtype=="started")
        | .tool_call | keys[] | select(endswith("ToolCall"))' \
  "$review_dir/review.jsonl"

jq -Rr 'fromjson? // empty
        | select(.type=="tool_call" and .subtype=="started")
        | .tool_call
        | (.readToolCall.args.path
           // .grepToolCall.args.path
           // .globToolCall.args.globPattern
           // .shellToolCall.args.command
           // empty)' \
  "$review_dir/review.jsonl"
```

If `shellToolCall` completions show `permissionDenied`, the invoke is missing
`--force` or ask mode is not in effect. Stop, fix the flags, and start over.

Treat narration and partial tool results as provisional and use them to steer
the run, not to collect findings.
