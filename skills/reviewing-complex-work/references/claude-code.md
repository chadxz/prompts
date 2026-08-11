# Reviewing with Claude Code

Read this when the peer reviewer is Claude Code. Flags and event shapes here
were verified against `claude` 2.1.223.

## Invoke

Run Claude as the foreground process in the caller's managed persistent command
session, with every scratch file under `~/tmp`. Give the command a short initial
yield so the caller receives a session handle while Claude keeps running:

```bash
cd "$WORKTREE"
exec claude -p \
  --model "$MODEL" \
  --effort max \
  --permission-mode bypassPermissions \
  --tools Read,Grep,Glob,Bash,WebSearch,WebFetch \
  --add-dir "$HOME/tmp" \
  --output-format stream-json --verbose \
  --no-session-persistence \
  "$(< "$review_dir/brief.txt")" \
  > "$review_dir/review.jsonl" 2>&1
```

Retain the execution or session handle returned by the command runner. In Codex,
start the command with a short yield and continue it through the returned
session ID. Do not add `nohup`, `&`, `disown`, or a PID file: the command runner
can terminate shell-backgrounded descendants as soon as the wrapper returns.
`exec` makes Claude the managed process, so its eventual exit status remains
available through the same session handle.

Discover the model rather than assuming one. `--model` accepts an alias such as
`opus` or a full identifier; pass the full identifier so a later alias remapping
cannot silently change the tier.

## Tools

`--tools` is an allowlist drawn from the built-in set, so naming the six tools
above both grants what a review needs and excludes editing and delegation. A
probe of that exact list returns `Bash, Glob, Grep, Read, WebFetch, WebSearch`
and nothing else, which is the intended surface:

- `Read`, `Grep`, `Glob` for source, tests, and documentation;
- `Bash` for `git`, `gh`, build metadata, and other read-only inspection;
- `WebSearch`, `WebFetch` for advisories, upstream behavior, and version
  semantics not present in the repository.

Because the allowlist omits `Edit`, `Write`, and `NotebookEdit`, no editing tool
exists in the session. It also omits `Task`, which keeps the review one hop
deep. Add `--disallowedTools Edit,Write,NotebookEdit` if a caller prefers an
explicit denial as well; it is redundant with the allowlist.

`Bash` can still write files, so the mutation check in `SKILL.md` remains the
real guarantee.

## Permission Mode

Use `bypassPermissions`. It is the only mode that lets the granted tools run
without a human present.

Do not use `plan`. Plan mode's contract is to research and then call
`ExitPlanMode`, which is unavailable under `-p`, so reviews end by explaining
that they cannot propose a plan instead of delivering findings.

Do not use `dontAsk` when `Bash` is granted. In that mode `Bash` is refused
outright, with a denial message stating that Bash is unavailable because Claude
Code is running in don't-ask mode. The review silently degrades to static
reading.

Claude Code confines reads to the working directory, so any path outside it
needs `--add-dir`. Without it the peer cannot open the file and will review the
wrong scope while saying so only in passing.

Pass `--add-dir "$HOME/tmp"` whenever the brief points at something staged
there. It is harmless when the brief points only at the worktree, so including
it by default is reasonable; drop it when the brief must be confined to the
repository.

## Turn and Spend Limits

Do not pass `--max-turns`. A ceiling truncates the review mid-investigation and
yields `subtype: error_max_turns` with narration in place of findings.

`--max-budget-usd` is acceptable as a runaway guard only. When it trips, the
result carries `subtype: error_max_budget_usd`, so the status check below
catches it.

## Collect

First confirm that the managed command session completed. Because stdout is
redirected, an empty continuation response while it runs is normal; use the
event-stream projections below to inspect progress. Once the session completes,
extract the review and surface a failed run as a failure rather than as
findings:

```bash
jq -Rr 'fromjson? // empty | select(.type=="result")
        | if .subtype=="success" then .result
          else "FAILED subtype=\(.subtype) reason=\(.terminal_reason // "n/a") turns=\(.num_turns) cost=\(.total_cost_usd) errors=\(.errors // [] | join("; "))"
          end' "$review_dir/review.jsonl"
```

The `result` event carries `subtype`, `terminal_reason`, `num_turns`,
`total_cost_usd`, `is_error`, and `errors`. A completed review is
`subtype: success` with `terminal_reason: completed`, and `.result` holds the
review text. Observed failure shapes are `error_max_turns`
(`terminal_reason: max_turns`), `error_during_execution`
(`terminal_reason: aborted_streaming`, which is what an interrupted process
looks like), and `error_max_budget_usd`.

## Inspect While It Runs

Assistant events carry `.message.content[]`, which supports three views. All
three are safe to re-run at any point; none of them read tool results, which is
where the stream's volume lives.

Progress:

```bash
jq -Rr 'fromjson? // empty | select(.type=="assistant")
        | .message.content[]? | select(.type=="tool_use") | .name' "$review_dir/review.jsonl" \
  | awk '{n++; last=$0} END{print (n+0)" tool calls, last="last}'
```

This reports progress such as `47 tool calls, last=Grep`. If it reports
`0 tool calls` while the process is alive, fall back to the schema-independent
progress check in `SKILL.md`.

What the peer is inspecting, which is how a wrong-scope review is caught early:

```bash
jq -Rr 'fromjson? // empty | select(.type=="assistant")
        | .message.content[]? | select(.type=="tool_use")
        | "\(.name)\t\(.input.file_path // .input.pattern // .input.command // "")"' \
  "$review_dir/review.jsonl" | tail -15
```

Narration so far, which surfaces a rabbit hole or an unexpected wall:

```bash
jq -Rr 'fromjson? // empty | select(.type=="assistant")
        | .message.content[]? | select(.type=="text") | .text' "$review_dir/review.jsonl"
```

Treat this text as provisional. It includes intermediate reasoning the peer may
revise before the `result` event, so use it to steer the run rather than to
collect findings.
