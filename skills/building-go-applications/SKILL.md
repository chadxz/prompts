---
name: building-go-applications
description: >
  Build, modify, review, and debug Go applications using Convergint Go
  conventions. Use for Go services, CLIs, libraries, mise and CI tasks, tests,
  linting, configuration, HTTP clients, telemetry, persistence, Docker
  packaging, releases, and Go applications that use Temporal.
---

# Building Go Applications

## Workflow

1. Read the repository instructions and nearby Go modules before choosing a
   pattern. Local conventions override this skill.
2. Identify whether the module is a service, CLI, published library, worker, or
   small job. Use that profile to select the relevant references below.
3. Read only the references required for the task. Read each selected reference
   completely before editing.
4. Keep behavior in testable packages, add or update tests with the behavior,
   and expose the development workflow through module-owned mise tasks.
5. Run the module's canonical format, lint, test, build, and validation tasks.
   Review generated artifacts and the final diff before handing off.

## Core Project Shape

Use a module-local `go.mod` and `go.sum`. Put service and CLI entrypoints under
`cmd/<binary>/main.go`, with domain behavior under `internal/`. A very small
one-command job may stay at the module root when that is already the local
pattern.

Keep `main` boring. It should parse input, load validated configuration, set up
logging and telemetry, wire dependencies, start the process, and handle
shutdown. Put decisions and behavior in testable packages.

Name packages for ownership, such as `config`, `telemetry`, `client`, `server`,
`collector`, `pipeline`, `audit`, `cursor`, and `otlp`. Avoid grab-bag packages
and files such as `utils`, `helpers`, and `constants`.

Choose the application profile before adding project-specific tooling:

- Services emphasize configuration, telemetry, health, graceful shutdown, and
  deployment validation.
- CLIs emphasize help, exit codes, dry-run guarantees, stable machine-readable
  output, subprocess boundaries, and release archives.
- Published libraries emphasize small public APIs, examples, compatibility,
  Semantic Versioning, and API stability.

## Core Coding And Testing Conventions

Default to Effective Go, Go Code Review Comments, and the Uber Go Style Guide.
Preserve these Convergint preferences:

- Write tests before changing behavior when practical.
- Prefer small, consumer-owned interfaces at package boundaries.
- Accept interfaces and return concrete types unless local code differs.
- Use functional options for clients, loggers, and configurable constructors.
- Keep public APIs smaller than internal APIs.
- Return early on errors and keep the happy path shallow.
- Wrap errors with context using `fmt.Errorf("context: %w", err)`.
- Keep error strings lowercase, without punctuation or a `failed to` prefix.
- Do not both log and return the same error.
- Preserve common initialisms such as `ID`, `URL`, `HTTP`, `JSON`, and `OTLP`.
- Use short receiver names that match the type.
- Preallocate slices with `make([]T, 0, n)` when capacity is known.
- Use structured parsers for structured data.
- Put package contracts in `doc.go` and comment every exported symbol.
- Use comments for intent, operational rationale, and non-obvious gotchas.
- Keep security, path, and secret-handling suppressions narrow and explained.

Keep unit tests next to the package under test. Prefer table-driven tests, mark
helpers with `t.Helper()`, and use the repository's existing assertion style.
Test error classification, context cancellation, malformed input, pagination,
rate limits, and graceful fallback behavior when they are part of the package
contract. Keep real services, subprocesses, containers, and worktrees in
integration tests.

## Reference Routing

- Read [Mise and CI](references/mise-and-ci.md) for mise tasks, lint, coverage,
  CI, integration tests, or repository plumbing.
- Read [Configuration and HTTP](references/configuration-and-http.md) for
  environment configuration, secrets, external APIs, or authentication.
- Read [Telemetry](references/telemetry.md) for `slog`, OpenTelemetry, Datadog
  correlation, or Prometheus exporters.
- Read [Persistence and idempotency](references/persistence-and-idempotency.md)
  for cursors, checkpoints, replay, deduplication, or optimistic concurrency.
- Read [Docker and release](references/docker-and-release.md) for Docker images,
  distributable CLIs, published libraries, or releases.
- Read [Documentation](references/documentation.md) for package comments, public
  API docs, README content, or contributor guidance.
- Read [Source map](references/source-map.md) to find current examples in
  Convergint repositories.

When a Go application uses Temporal, also read the
`developing-temporal-applications` skill. This skill owns Go project structure,
tooling, and general coding conventions. The Temporal skill owns workflow and
activity boundaries, determinism, retries, schedules, workers, and Temporal
test-suite guidance.
