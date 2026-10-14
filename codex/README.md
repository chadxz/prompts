# Codex idle compaction

Resuming a large chat after its prompt cache expires processes the full context
again. The idle compaction hook compacts a large chat while that history can
still use cached input, leaving a smaller context for a later cold resume.

Run `bash setup_codex.sh` from the checkout you want to install. Setup merges
the handlers into `~/.codex/hooks.json` and trusts their exact definitions
through Codex's public configuration API. It preserves unrelated hooks and trust
state. `CODEX_HOME` selects a different Codex configuration directory when
configured.

## Behavior

After `Stop`, a detached worker waits 20 minutes. It only requests compaction
when the context has at least 200,000 tokens, the chat is unarchived and idle,
and its model/provider and latest response still match. New prompts, session
starts, interruption, compaction, and session end cancel pending work. Archiving
also cancels work through `SessionEnd`; the worker rechecks archive state before
sending a request.

The worker skips requests once its conservative cache age reaches 25 minutes,
including after machine sleep. Cache age starts at the preceding response or
tool result, rather than at the end of a potentially long model generation. Only
OpenAI models numbered GPT-5.6 or later qualify for the documented 30-minute
minimum cache lifetime. Failed or uncertain requests aren't retried.

The desktop app must still be running and own the chat. The helper uses its
internal Unix-socket owner-routing protocol to reach `thread/compact/start`.
That connection can change between app releases. An unavailable owner or a
protocol mismatch skips the request; the helper doesn't resume a thread in
another server. It reads Codex's transcript and state database without writing
them. Its own timer and audit database stores identifiers and activity metadata,
without chat text, under `~/.codex/idle-compaction/`.

## Configuration and inspection

Edit `~/.codex/idle-compaction.json` to adjust the defaults:

```json
{
  "enabled": true,
  "idle_seconds": 1200,
  "max_cache_age_seconds": 1500,
  "min_context_tokens": 200000
}
```

`idle_seconds` must be shorter than `max_cache_age_seconds`, which can't exceed
1500. Set `enabled` to `false` to disable compaction, including pending work.
Setup preserves this file on subsequent runs.

Inspect pending timers and the latest audit records:

```sh
uv run --no-project --script codex/idle_compaction.py status
```

Run the safety and installation tests:

```sh
uv run --no-project python -m unittest discover -s codex -v
```

See the official [hook lifecycle](https://learn.chatgpt.com/docs/hooks),
[compaction endpoint](https://learn.chatgpt.com/docs/app-server#trigger-thread-compaction),
and
[cache lifetime](https://developers.openai.com/api/docs/guides/prompt-caching#cache-lifetime)
documentation.
