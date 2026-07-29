# Persistence and Idempotency

Use these conventions for cursors, checkpoints, stateful polling, and replay:

- Make idempotency explicit.
- Use optimistic concurrency when multiple runs can update one checkpoint.
- Generate stable identities from native IDs when present.
- Fall back to deterministic fingerprints built from stable fields.
- Preserve raw input in attributes when it is needed for debugging.
- Emit parse-error records so malformed rows remain visible.
- Do not let parse-error event timestamps advance high-water cursors.
- Keep replay overlap and edge identities so cursor-boundary events deduplicate.

Test state versioning, corrupt state, atomic persistence, locking, recovery, and
concurrent updates. Use fake clocks for expiry, polling, and cursor behavior.

Keep persistence interfaces consumer-owned and narrow. Map storage conflicts,
missing state, and permanent data errors into stable typed or sentinel errors at
the package boundary.
