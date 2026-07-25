# Changelog

All notable changes to `wt-stack` are documented here. Releases follow Semantic
Versioning.

## Unreleased

### Added

- Versioned JSON output schema.
- Unit-only coverage gate and optional real Git integration suite.
- User, contributor, security, compatibility, and release documentation.

### Changed

- Dry runs no longer fetch, continue, abort, push, or persist remote state.
- Commands reject unexpected positional arguments.
- State and lock files are readable only by the current user.

## 0.2.0

### Added

- Direct GitHub API support for pull requests and Stacks.
- GitHub CLI configuration and keychain credential discovery without executing
  `gh`.
- GitHub Enterprise remote resolution, rate-limit handling, pagination, and API
  error details.
