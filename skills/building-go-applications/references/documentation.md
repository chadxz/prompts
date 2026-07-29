# Documentation

Use `doc.go` for every package, including `main`.

Package documentation should explain the contract, ownership, concurrency model,
security boundaries, and important side effects. Exported-symbol comments should
explain behavior, error semantics, ownership, mutability, and concurrency when
those details affect callers. Avoid comments that restate the identifier.

Keep end-user and contributor documentation separate:

- `README.md` is user-facing. Include purpose, prerequisites, installation, a
  complete quick start, every command or public API, options, compatibility,
  operational guarantees, recovery, and troubleshooting.
- `CONTRIBUTING.md` is terse and development-facing. Include the mise workflow,
  package boundaries, unit and integration policy, lint and documentation
  expectations, coverage minimum, schema compatibility, and release checks.

Do not put directory structures in README files. Explain the relevant package or
command boundaries in prose instead.

Keep code examples brief and runnable. Verify documented commands and public
examples through tests or CI when practical.
