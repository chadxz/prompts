# Contributing to wt-stack

`wt-stack` keeps orchestration in `internal/stack`, Git execution in
`internal/gitrepo`, GitHub HTTP behavior in `internal/github`, shared state in
`internal/state`, and presentation in `internal/cli`. Keep those boundaries
narrow and keep `cmd/wt-stack` limited to process startup.

## Development loop

Install the pinned tools, then run the full required suite:

```console
mise -C apps/wt-stack install
mise //apps/wt-stack:ci
```

Use the focused tasks while iterating:

```console
mise //apps/wt-stack:format
mise //apps/wt-stack:lint
mise //apps/wt-stack:test
mise //apps/wt-stack:build
```

Real Git and sibling-worktree tests are intentionally optional and excluded from
the unit coverage gate:

```console
mise //apps/wt-stack:test-integration
```

The unit coverage profile excludes `internal/gitrepo` because it is the
operating-system subprocess adapter. Its parsers, argument construction, and
error handling still have deterministic unit tests; real Git behavior stays in
the optional integration suite.

## Quality bar

- Put every package contract in `doc.go` and document every exported symbol.
- Preserve the configured correctness, security, and documentation linters.
- Add deterministic unit tests for behavior and error paths. Keep unit coverage
  at or above the minimum in `mise.toml`.
- Use the `integration` build tag only for tests that require real Git
  repositories, subprocesses, or worktrees.
- Keep JSON schema version `1` backward compatible. Update command tests and
  `docs/json-schema.json` when output changes.
- Preserve dry-run's no-mutation guarantee and explicit force-with-lease
  behavior.
- Pin build and validation tools. Run tidy, module verification, vulnerability
  checks, race tests, and both formatters before release.
- Keep user guidance in `README.md`. Keep this file limited to development and
  maintenance expectations.

Release tags use `v<major>.<minor>.<patch>` and must include an updated
`CHANGELOG.md`.
