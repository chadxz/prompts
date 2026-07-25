# Changelog

All notable changes to `wt-stack` are documented here. Releases follow Semantic
Versioning.

## Unreleased

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
