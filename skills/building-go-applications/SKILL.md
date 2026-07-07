---
name: building-go-applications
description: >
  Build, modify, review, and debug Go applications using Convergint Go
  conventions. Use for Go app scaffolding, mise tasks, unit tests, linting,
  formatting, coverage, Docker packaging, configuration, HTTP clients,
  OpenTelemetry/Datadog logging, Temporal workers, and coding conventions
  extracted from existing Convergint Go apps.
---

# Building Go Applications

## App Scaffolding

Start every non-trivial Go app with:

- Module-local `go.mod` and `go.sum`.
- `mise.toml` pinning Go, `golangci-lint`, and task-specific tools.
- App-owned mise tasks for `format`, `format-check`, `lint`, `test`, `tidy`,
  `build`, and `ci`.
- Race-enabled unit tests with coverage artifacts under `dist/`.
- A Dockerfile and `docker` task for deployable workloads.
- Validation tasks for app-owned manifests, Terraform, shell scripts, and
  generated schemas.

Use `cmd/<binary>/main.go` for services and CLIs, with domain code under
`internal/`. Keep very small one-command jobs at the module root when that is
already the local pattern.

Name packages for ownership: `config`, `telemetry`, `client`, `server`,
`collector`, `pipeline`, `audit`, `cursor`, `otlp`, and similarly narrow domain
terms. Avoid grab-bag packages and files such as `utils`, `helpers`, and
`constants`.

Keep `main` boring. It should parse flags, load validated configuration, set up
logging and telemetry, wire clients and stores, start the service, and handle
graceful shutdown. Put behavior in testable internal packages.

## Mise Tasks

Use mise as the app's public development and CI interface. Do not make future
agents remember raw tool invocations.

Pin extra tools only when tasks use them, such as `dprint`, `shellcheck`,
`terraform`, `tflint`, `jq`, and Temporal CLIs.

Use this task recipe unless the app has an established variant:

```toml
[tasks.format]
run = "gofmt -w ."

[tasks.format-check]
run = """
#!/usr/bin/env bash
set -euo pipefail
files="$(gofmt -l .)"
if [ -n "$files" ]; then
  echo "$files"
  gofmt -d .
  exit 1
fi
"""

[tasks.lint]
run = "golangci-lint run"

[tasks.test]
run = """
mkdir -p dist
go test -v -race -coverprofile=dist/coverage.out -covermode=atomic ./...
go run github.com/boumenot/gocover-cobertura@latest \
  < dist/coverage.out > dist/coverage.xml
"""

[tasks.tidy]
run = "go mod tidy"
```

The `build` task writes binaries to `dist/`. The `docker` task uses
`docker buildx build`. The `ci` task composes `format-check`, `lint`, `test`,
`build`, deployable Docker checks, and app-owned validation.

## Coding Conventions

Default to Effective Go, Go Code Review Comments, and the Uber Go Style Guide.
Preserve these Convergint preferences:

- Write tests before changing behavior when practical.
- Prefer small interfaces at package boundaries.
- Accept interfaces and return concrete types unless local code differs.
- Use functional options for clients, loggers, and configurable constructors.
- Return early on errors and keep the happy path shallow.
- Wrap errors with context using `fmt.Errorf("context: %w", err)`.
- Keep error strings lowercase, without punctuation, and without a `failed to`
  prefix.
- Do not both log and return the same error.
- Preserve common initialisms: `ID`, `URL`, `HTTP`, `JSON`, `OTLP`.
- Use short receiver names that match the type.
- Use `make([]T, 0, n)` when capacity is known.
- Add package comments and comments on exported symbols.
- Use comments for intent, operational rationale, and non-obvious gotchas.
- Keep security, path, and secret-handling suppressions narrow and explained.

Use structured parsers for structured data. Prefer `encoding/json`,
`gopkg.in/yaml.v3`, TOML parsers, Terraform SDK/framework APIs, and vendor SDK
types over string manipulation.

## Configuration And Secrets

Put configuration in a dedicated package. Define env var names as constants, set
defaults in one place, and validate before the app starts doing work.

Configuration conventions:

- Use an app-specific env prefix.
- Trim and normalize URLs, sites, environment names, and comma-separated lists.
- Parse durations with `time.ParseDuration`.
- Reject zero and negative operational limits when they break runtime behavior.
- Load `APP_NAME`, `APP_ENV`, `APP_VERSION`, `COMMIT_SHA`, and `REPOSITORY_URL`
  for service metadata when relevant.
- Redact secrets in any effective-config output.
- Reject unresolved `op://` references when secrets should resolve before
  startup.
- Include `_ "time/tzdata"` when a distroless workload needs IANA timezones.

Never commit secret material: bearer tokens, copied passwords, and resolved
secret files. Keep secret-bearing local artifacts under ignored paths such as
`dist/`.

## HTTP And API Clients

External calls accept `context.Context`, use explicit timeouts, and close
response bodies. Keep API adapters small and test them with `httptest.Server`.

Use retry logic for APIs that need it. Existing exporters use
`hashicorp/go-retryablehttp` for rate limiting and transient server errors such
as 429, 502, 503, and 504. Preserve context cancellation in retry policies.

For token-based APIs, cache tokens behind a mutex, refresh before expiry with a
small buffer, retry once after 401/403 responses, wrap request and decoding
errors with context, bound large response reads, and classify permanent status
codes with sentinel errors.

## Telemetry And Logging

Use structured `slog` JSON logging for long-running services and workers.
Include service, environment, and version attributes from platform environment
variables.

When using OpenTelemetry:

- Create resources with `service.name`, `service.version`, deployment
  environment, `language=golang`, `git.commit.sha`, and stripped
  `git.repository_url` from `REPOSITORY_URL` with the `http://`/`https://`
  prefix removed.
- Set W3C trace context and baggage propagation for distributed traces.
- If `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, return no-op/global providers.
- Wrap outbound HTTP clients with `otelhttp.NewTransport`.
- Shut down tracer, meter, and log providers with a bounded timeout.
- Add Datadog `dd.trace_id` and `dd.span_id` fields to logs using the low 64
  bits of the OpenTelemetry trace ID and the span ID in decimal form.
- Keep operational telemetry service names distinct from forwarded data service
  names.

Prometheus exporters expose OpenMetrics, `/healthz`, and `/readyz`; test
descriptors, labels, metric families, and error states. When API latency and
rate limits make fresh collection risky, cache scrape data with TTLs, preserve
the last successful cache on refresh failure, and emit cache age, cache hit,
collection success, and collection duration metrics.

## Temporal Workers

When a Go app uses Temporal, also consult the `developing-temporal-applications`
skill. Preserve these Go worker conventions:

- Build clients from `go.temporal.io/sdk/contrib/envconfig`.
- Default local development to `localhost:7233` and namespace `default`.
- Register workflows in one small function.
- Register activities as methods on an `Activities` struct.
- Keep nondeterministic work in activities.
- Copy operational tuning from config into workflow input.
- Mark permanent failures as non-retryable application errors with stable type
  strings.
- Use stable schedule IDs per tenant/environment.
- Preserve operator pause state and notes when reconciling schedules.
- Use `SCHEDULE_OVERLAP_POLICY_SKIP` for polling schedules.

Test workflows with `testsuite.WorkflowTestSuite`, test activities with
`TestActivityEnvironment`, and assert non-retryable error types when changing
retry classification.

## Persistence And Idempotency

For cursor, checkpoint, and stateful polling code:

- Make idempotency explicit.
- Use optimistic concurrency when multiple runs can update the same checkpoint.
- Generate stable identities from native IDs when present.
- Fall back to deterministic fingerprints built from stable fields.
- Preserve raw input in attributes for later debugging.
- Emit parse-error records so bad rows are visible.
- Do not let parse-error event timestamps advance high-water cursors.
- Keep replay overlap and edge identities so cursor-boundary events dedupe.

## Docker Packaging

Deployable Go workloads use multi-stage Dockerfiles:

- Builder: `golang:<version>-alpine`.
- Install CA certificates for outbound TLS; install `tzdata` for timezones.
- Copy `go.mod` and `go.sum` first, then run `go mod download` and
  `go mod verify`.
- Build static Linux binaries with `CGO_ENABLED=0 GOOS=linux GOARCH=amd64`,
  `-trimpath`, and `-ldflags="-w -s"`.
- Use `-buildvcs=false` when VCS stamping is unreliable in the build context.
- Runtime: `gcr.io/distroless/static-debian12:nonroot`.
- Copy certificates, zoneinfo, and the binary.
- Run as `nonroot:nonroot`.

Use health checks that match the workload. Web exporters expose a port and
readiness path. CronJobs use `HEALTHCHECK NONE`. Workers default their
entrypoint to the worker command.

## Testing Expectations

Keep unit tests next to the package under test. Use table-driven tests with
`t.Run`, mark helpers with `t.Helper()`, use `testify/require` for setup and
fatal preconditions, and use `testify/assert` where the project already uses
non-fatal comparisons.

Cover the app's operational edges:

- Env-driven config with `t.Setenv`.
- API clients with `httptest.Server`.
- Token expiry, polling, and cursor logic with fake clocks.
- Package boundaries with in-memory stores and small fake clients.
- Metrics with Prometheus and OpenTelemetry SDK test readers.
- Temporal workflows and activities with SDK test suites.
- Error classification, context cancellation, rate limits, pagination, malformed
  input, and graceful fallback behavior.

When exported metric metadata changes, update metric tests and checked-in
example metric output.

## App-Owned Infrastructure And Repository Integration

Expose app-owned Terraform, manifests, shell scripts, and generated schemas
through mise validation tasks such as `infra:lint`, `infra:validate`,
`validate-manifests`, and `generate-schema`. Do not include `terraform apply` in
normal validation and CI tasks.

Keep repository plumbing separate from Go conventions.

In `ee-monorepo`, new Go projects may need `project.json` and EE deployment
target metadata because the repo uses Nx affected-project CI and the
`libraries/nx-go` plugin. That plugin discovers dependencies for existing Nx
projects with `go.mod`; it does not create projects.

In repositories that do not use that EE Nx model, do not add `project.json`. Do
not add deployment matrix metadata for ordinary Go apps.
