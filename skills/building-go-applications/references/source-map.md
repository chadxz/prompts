# Source Map

This skill was extracted from Go code and contributor guidance in these local
repositories:

- `/Users/chad/src/convergint/ee-monorepo/main`
- `/Users/chad/src/convergint/it-monorepo/main`

Use this file to find representative examples quickly. It is provenance, not a
second instruction file. The source code remains the authority; re-read current
files before applying a convention.

## Shared Guidance

- `ee-monorepo/CONTRIBUTING.md`: mise-first workflow, project-owned `ci` tasks,
  and coverage expectations for test tasks. Its Nx affected-CI guidance is
  EE-specific.
- `it-monorepo/apps/saviynt-audit-log-collector/CONTRIBUTING.md`: mise task
  syntax, local discovery artifact handling, and Terraform apply guardrails.
- `ee-monorepo/apps/anypoint-exporter/CONTRIBUTING.md`: Effective Go, Go Code
  Review Comments, Uber style, small interfaces, functional options, retries,
  TDD, `testify`, coverage, and metric-update workflow.
- `ee-monorepo/tools/ci-matrix/CONTRIBUTING.md`: CLI structure, `mise :ci`,
  schema generation, table-driven tests, error-string style, and helper rules.
- `ee-monorepo/apps/mulesoft-otel-collector/smoke-test/CONTRIBUTING.md`: simple
  Go smoke-test validation using tidy, format, and test tasks.

## EE Monorepo Repo Plumbing

These examples explain the EE source material behind the repository integration
caveat in `SKILL.md`. They are not portable Go conventions by themselves:

- `nx.json` registers `./libraries/nx-go`.
- `libraries/nx-go/src/index.ts` detects Go project dependencies by scanning
  existing Nx projects with `go.mod` and parsing Go imports. It does not create
  Nx projects.
- `tools/ci-matrix/internal/project/project.go` includes `project.json` parsing,
  safe path validation, deploy target schema, and mise `ci` detection.
- `tools/ci-matrix/internal/matrix/matrix.go` discovers deployment manifests
  named `web-*`, `worker-*`, and `job-*`, validates target environments, and
  builds phased deploy matrices.
- `apps/anypoint-exporter/project.json` and
  `apps/observability-canary/project.json` show deploy targets that point at app
  manifests.

## Go App Examples

### Anypoint Exporter

Path: `ee-monorepo/apps/anypoint-exporter`

- `cmd/anypoint_exporter/main.go`: Cobra CLI, config precedence, env-backed
  flags, version command, telemetry startup, Prometheus server startup, signal
  handling, graceful shutdown, and redacted effective config printing.
- `internal/config/config.go`: YAML and environment config loading, defaults,
  validation, duration parsing, and CLI overrides.
- `internal/auth/client.go`: OAuth token caching with mutex, refresh buffer,
  injected clock, context-aware requests, and logging.
- `internal/client/client.go`: Anypoint HTTP adapter using retryablehttp,
  context-aware requests, bearer tokens, pagination, and response handling.
- `internal/server/server.go`: custom Prometheus registry, `/metrics`,
  `/healthz`, `/readyz`, OpenTelemetry-wrapped metrics endpoint, server
  timeouts, and shutdown.
- `internal/collector/cached_collector.go`: on-demand TTL scrape cache,
  thundering-herd prevention, previous-cache preservation on refresh failure,
  and cache metrics.
- `internal/telemetry/telemetry.go` and `logger.go`: OTel resource attributes,
  optional OTLP startup, HTTP wrapping, structured logs, and Datadog trace
  correlation fields.
- `Dockerfile`: Alpine builder, distroless nonroot runtime, CA certs, zoneinfo,
  static binary flags, and `docker buildx` task integration.

### Observability Canary

Path: `ee-monorepo/apps/observability-canary`

- `main.go`: small job entrypoint, deferred metric reporting even on early
  return, panic recording, root spans, and outcome handling.
- `config.go`: environment-only config, Datadog site normalization, poll
  schedule parsing, and required variable validation.
- `check.go`: Datadog Logs Search polling, fixed poll schedule, rate-limit
  header handling, retry-after parsing, bounded sleeps, and outcome
  classification.
- `report.go`: direct Datadog metric submission with count and distribution
  payloads.
- `telemetry.go`: lightweight optional tracing for CronJob-style workloads.
- `Dockerfile` and `deployment/job-production.yaml`: distroless CronJob image
  and platform job manifest with `HEALTHCHECK NONE`.

### MuleSoft OTEL Collector Smoke Test

Path: `ee-monorepo/apps/mulesoft-otel-collector/smoke-test`

- `main.go`: standard library `flag` CLI, environment-to-endpoint mapping, Basic
  Auth header construction, OTLP trace, metric, and log exporters, and password
  input from stdin.
- `main_test.go`: table-driven validation of environment mapping and constants.

### CI Matrix Tool

Path: `ee-monorepo/tools/ci-matrix`

- `cmd/ci-matrix/main.go`: standard library CLI, bounded stdin reads, schema
  subcommand, Nx affected/all project discovery, filters, and JSON output.
- `internal/project/project.go`: JSON/TOML parsing, safe path validation, deploy
  target types, and `mise.toml` CI-task detection.
- `internal/matrix/matrix.go`: CI/CD matrix generation, deploy manifest
  discovery, environment validation, explicit target expansion, deploy phase
  ordering, and warnings.
- `internal/nx/nx.go`: shelling out to Nx with stderr capture and JSON parsing.

### Terraform Provider Charon

Path: `ee-monorepo/libraries/terraform-provider-charon`

- `main.go`: Terraform provider server entrypoint and debug flag.
- `internal/provider/provider.go`: provider config schema, environment fallback,
  sensitive API key handling, timeout validation, and diagnostics.
- `internal/provider/client.go`: small HTTP API adapter, bearer auth, typed API
  errors, 404 handling, and delete idempotency.
- `internal/provider/resource_server.go`: framework resource lifecycle,
  validators, import state, conflict/not-found diagnostics, and API/state
  mapping helpers.

## IT Monorepo Example

### Saviynt Audit Log Collector

Path: `it-monorepo/apps/saviynt-audit-log-collector`

- `cmd/saviynt_audit_log_collector/main.go`: subcommands, structured logger,
  worker startup, schedule reconciliation, telemetry and sink shutdown, Temporal
  client wiring, Saviynt client factory, cursor-store selection, and production
  guardrails for Azure Table cursor storage.
- `internal/config/config.go`: environment config constants, defaults,
  validation, timezone loading, duration and integer parsing, unresolved
  1Password reference rejection, and tenant lookup.
- `internal/telemetry/telemetry.go` and `logger.go`: OTel resources, W3C
  propagation, optional OTLP providers, HTTP client wrapping, slog JSON output,
  Temporal logger adapter, and Datadog trace ID conversion.
- `internal/pipeline/temporal.go`: Temporal envconfig client, tracing
  interceptor, worker registration, schedule create/update, and operator-state
  preservation.
- `internal/pipeline/audit_workflow.go`: deterministic workflow input tuning,
  activity retry policy, non-retryable error types, pagination, continue-as-new,
  cursor persistence, and schedule options.
- `internal/pipeline/read_cursor.go`, `fetch_page.go`, `submit_page.go`, and
  `persist_cursor.go`: activity boundaries, Saviynt page fetches, OTLP
  submission, optimistic concurrency, and non-retryable conflict handling.
- `internal/audit/transform.go`: row normalization, stable identities, synthetic
  fingerprints, parse-error events, cursor edge deduplication, and high-water
  advancement rules.
- `internal/cursor/store.go` and `azure_table.go`: in-memory store for tests and
  local development, Azure Table store, ETag versioning, and conflict mapping.
- `internal/otlp/sink.go`: OTLP log sink, no-op mode, forwarded audit resource
  identity, force flush, Datadog trace attributes, and large payload chunking.
- `internal/saviynt/client.go`: Saviynt login, refresh-token flow, runtime
  analytics requests, status classification, limited response reads, and
  envelope parsing.
- `.github/workflows/saviynt-audit-log-collector.yml`: app-specific CI/CD, mise
  setup, `mise run :ci`, Datadog coverage upload, and deployment action.
- `Dockerfile` and `deployment/worker-production.yaml`: worker image and
  platform worker manifest with `useTemporal: true`.
