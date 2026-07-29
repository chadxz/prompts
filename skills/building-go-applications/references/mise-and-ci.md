# Mise and CI

- [Module-owned workflow](#module-owned-workflow)
- [Coverage and integration tests](#coverage-and-integration-tests)
- [Linting](#linting)
- [Module-owned infrastructure](#module-owned-infrastructure)

## Module-Owned Workflow

Use mise as the module's public development and CI interface. Do not make
contributors or future agents remember raw tool invocations.

Pin Go, `golangci-lint`, and every tool used by a task. Pin extra tools only
when the module uses them, such as `dprint`, `shellcheck`, `terraform`,
`tflint`, `jq`, or vendor CLIs.

Expose module-owned tasks for:

- `format`
- `format-check`
- `lint`
- `test`
- `test-integration`
- `tidy`
- `tidy-check`
- `verify`
- `vuln`
- `build`
- `ci`

Use this baseline unless the module has an established variant:

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
#!/usr/bin/env bash
set -euo pipefail
mkdir -p dist
go test -race -coverpkg=./... \
  -coverprofile=dist/coverage.out -covermode=atomic ./...
go tool cover -html=dist/coverage.out -o dist/coverage.html
"""

[tasks.test-integration]
run = "go test -v -race -tags=integration ./..."

[tasks.tidy]
run = "go mod tidy"

[tasks.tidy-check]
run = "go mod tidy -diff"

[tasks.verify]
run = "go mod verify"

[tasks.vuln]
run = "go tool govulncheck ./..."
```

Record build-time Go commands with `go get -tool <package>@<version>` so
`go.mod` and `go.sum` pin the tool version and checksum. Keep report conversion
outside the coverage gate so a reporting-tool failure cannot disguise the unit
test result.

Write binaries and generated reports under `dist/`. Use `docker buildx build`
for Docker tasks. Compose `ci` from format checking, linting, unit tests, tidy
checking, module verification, vulnerability scanning, builds, deployable image
checks, and module-owned validation.

## Coverage and Integration Tests

Gate deterministic unit coverage. Put tests that require live services, cloud
accounts, Docker, or real subprocesses behind an `integration` build tag and the
`test-integration` task.

Use `-coverpkg=./...` so unit tests count packages exercised through another
package. If an operating-system adapter cannot be unit tested without becoming
an integration test, exclude it from the unit coverage package list and explain
the decision in contributor documentation.

Keep the native coverage profile as a CI artifact and generate HTML for local
diagnosis. Add another report format only when a CI consumer requires it, and
fail if the converter skips packages. Start the coverage minimum at the current
meaningful unit baseline and ratchet it upward. Do not lower it to merge a
change.

Use consumer-owned interfaces around Git, filesystems, clocks, HTTP adapters,
and remote APIs so orchestration can be unit tested with narrow fakes. Add fuzz
tests for parsers, decoders, pagination links, remote URLs, and other untrusted
structured input.

## Linting

Check in a version 2 `.golangci.yml` for every module. Start with:

```yaml
version: "2"

linters:
  enable:
    - bodyclose
    - contextcheck
    - errcheck
    - errname
    - errorlint
    - gocritic
    - godoclint
    - gosec
    - govet
    - ineffassign
    - misspell
    - nilerr
    - nilnesserr
    - noctx
    - nolintlint
    - revive
    - staticcheck
    - thelper
    - unconvert
    - unparam
    - unused
  settings:
    revive:
      rules:
        - name: exported
        - name: package-comments

formatters:
  enable:
    - gofmt
    - goimports

run:
  tests: true
  timeout: 5m
```

Add domain linters such as `rowserrcheck`, `sqlclosecheck`, `sloglint`,
`spancheck`, `testifylint`, or `promlinter` when their packages are present.
Avoid cosmetic or complexity linters without a concrete maintenance problem.
Keep exclusions path-specific, name the linter, and explain why the code is
safe. Never use a broad `nolint`.

## Module-Owned Infrastructure

Expose module-owned Terraform, manifests, shell scripts, and generated schemas
through tasks such as `infra:lint`, `infra:validate`, `validate-manifests`, and
`generate-schema`. Do not include `terraform apply` in normal validation or CI.

Keep repository plumbing separate from Go conventions.

In `ee-monorepo`, a new Go project may need `project.json` and deployment target
metadata because Nx affected-project CI uses `libraries/nx-go`. That plugin
discovers dependencies for existing Nx projects with `go.mod`; it does not
create projects.

Do not add `project.json` in repositories that do not use the EE Nx model. Do
not add deployment matrix metadata for ordinary Go applications.
