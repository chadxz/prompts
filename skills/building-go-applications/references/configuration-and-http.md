# Configuration and HTTP

## Configuration and Secrets

Put configuration in a dedicated package. Define environment variable names as
constants, set defaults in one place, and validate configuration before the
application starts work.

Use these conventions:

- Use an application-specific environment prefix.
- Trim and normalize URLs, sites, environment names, and comma-separated lists.
- Parse durations with `time.ParseDuration`.
- Reject zero or negative operational limits when they break runtime behavior.
- Load `APP_NAME`, `APP_ENV`, `APP_VERSION`, `COMMIT_SHA`, and `REPOSITORY_URL`
  for service metadata when relevant.
- Redact secrets in effective-configuration output.
- Reject unresolved `op://` references when secrets should resolve before
  startup.
- Include `_ "time/tzdata"` when a distroless workload needs IANA time zones.

Never commit secret material, copied credentials, or resolved secret files. Keep
secret-bearing local artifacts under ignored paths such as `dist/`.

Test environment-driven configuration with `t.Setenv`.

## HTTP and API Clients

Accept `context.Context` for external calls, configure explicit timeouts, and
close response bodies. Keep API adapters small and test them with
`httptest.Server`.

Use retry logic only for APIs and failure classes that need it. Existing
exporters use `hashicorp/go-retryablehttp` for rate limiting and transient
server errors such as 429, 502, 503, and 504. Preserve context cancellation in
retry policies.

For token-based APIs:

- Cache tokens behind a mutex.
- Refresh before expiry with a small buffer.
- Retry once after a 401 response.
- Classify 403 responses before retrying because they may mean permanent
  permissions, preview access, or rate limiting.

Honor `Retry-After` and vendor rate-limit reset headers. Wrap request and
decoding errors with context, bound large response reads, and classify permanent
status codes with typed or sentinel errors.

Use structured parsers and vendor SDK types instead of string manipulation for
JSON, YAML, TOML, Terraform, and other structured formats.
