# Docker and Release

## Docker Packaging

Use multi-stage Dockerfiles for deployable Go workloads:

- Build with `golang:<version>-alpine`.
- Install CA certificates for outbound TLS and `tzdata` when needed.
- Copy `go.mod` and `go.sum` before source files, then run `go mod download` and
  `go mod verify`.
- Build static Linux binaries with `CGO_ENABLED=0 GOOS=linux GOARCH=amd64`,
  `-trimpath`, and `-ldflags="-w -s"`.
- Use `-buildvcs=false` when VCS stamping is unreliable in the build context.
- Run on `gcr.io/distroless/static-debian12:nonroot`.
- Copy certificates, zone information, and the binary into the runtime image.
- Run as `nonroot:nonroot`.

Use `docker buildx build`, not `docker build`.

Match health checks to the workload. Web exporters expose a port and readiness
path. CronJobs use `HEALTHCHECK NONE`. Workers default their entrypoint to the
worker command.

## Published Libraries and Distributable CLIs

Keep public APIs smaller than internal APIs. Prefer `internal/` until another
module has a real import requirement. Provide runnable examples for primary
entry points and test the oldest supported Go version plus the current version.

Treat command help and machine-readable output as APIs. Test them, version
schemas explicitly, document exit codes, and require consumers to ignore unknown
fields within a supported schema version.

Use Semantic Versioning and automate releases from immutable tags. Release
archives for supported operating systems and architectures with embedded
versions, checksums, SBOMs, signatures or build-provenance attestations, and
reproducible `-trimpath` builds. Document unsupported platforms instead of
shipping an untested binary.

Run `go mod verify`, a pinned `govulncheck`, and release-configuration
validation in CI. Update `CHANGELOG.md` before tagging a release.

Published libraries and distributable CLIs should also include `LICENSE`,
`SECURITY.md`, and `CHANGELOG.md`.
