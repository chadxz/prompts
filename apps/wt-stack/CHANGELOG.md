# Changelog

All notable changes to `wt-stack` are documented here. Releases follow Semantic
Versioning.

## Unreleased

### Added

- Human-readable status includes full pull request URLs without requiring
  terminal hyperlink support.

- Non-interactive async Stack merging with prefix selection, expected head
  checks, read-only dry runs, bounded polling, and request resumption.
- Structured merge results distinguish pending, merged, enqueued, and failed
  operations while preserving request identifiers on polling errors.

### Fixed

- Documentation and doctor help describe Stacks API availability without stale
  private-preview or waitlist claims.

- Initialization uses the selected remote's default branch when `--base` is
  omitted, including read-only discovery during dry runs.

- Rebase validates saved parent boundaries before rewriting any branch and
  recovers stale metadata only from validated parent history.

- Rebase fetches its trunk explicitly, pins the target across conflict recovery,
  verifies ancestry, and distinguishes failed starts from recoverable conflicts.

## 0.5.0 - 2026-08-10

### Added

- Draft pull request creation through `submit --draft` and `sync --draft`.

## 0.4.0 - 2026-07-24

### Added

- Direct GitHub and local Stack removal with `unstack` and `delete`.
- Automatic version selection, changelog promotion, tag creation, and release
  publication after `main` passes CI.

### Changed

- Local builds derive versions from app-qualified `wt-stack/v*` tags.
- Stack submission starts a new GitHub Stack after every member of the previous
  Stack has merged.
- User documentation links to GitHub's official Stacked Pull Requests guide and
  covers the complete Stack lifecycle and shell completion command.

## 0.3.1 - 2026-07-24

### Added

- Versioned JSON output schema.
- Unit-only coverage gate and optional real Git integration suite.
- User, contributor, release, security, and compatibility documentation.

### Changed

- Dry runs no longer fetch, continue, abort, push, or persist remote state.
- Commands reject unexpected positional arguments.
- Release checksums use the current Cosign bundle format.
- State and lock files are readable only by the current user.

## 0.2.0

### Added

- Direct GitHub API support for pull requests and Stacks.
- GitHub CLI configuration and keychain credential discovery without executing
  `gh`.
- GitHub Enterprise remote resolution, rate-limit handling, pagination, and API
  error details.
