# Telemetry

## Logging

Use structured `slog` JSON logging for long-running services and workers.
Include service, environment, and version attributes from platform environment
variables. Do not log and return the same error.

## OpenTelemetry

When using OpenTelemetry:

- Create resources with `service.name`, `service.version`, deployment
  environment, `language=golang`, `git.commit.sha`, and a stripped
  `git.repository_url` from `REPOSITORY_URL`.
- Set W3C trace context and baggage propagation for distributed traces.
- Return no-op or global providers when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset.
- Wrap outbound HTTP clients with `otelhttp.NewTransport`.
- Shut down tracer, meter, and log providers with a bounded timeout.
- Add Datadog `dd.trace_id` and `dd.span_id` fields to logs using the low 64
  bits of the OpenTelemetry trace ID and the span ID in decimal form.
- Keep operational telemetry service names distinct from forwarded data service
  names.

## Prometheus Exporters

Expose OpenMetrics, `/healthz`, and `/readyz`. Test descriptors, labels, metric
families, and error states. Use Prometheus collectors and OpenTelemetry SDK test
readers to verify emitted telemetry.

When API latency or rate limits make fresh collection risky, cache scrape data
with TTLs. Preserve the last successful cache when refresh fails, and emit cache
age, cache hit, collection success, and collection duration metrics.

When exported metric metadata changes, update metric tests and checked-in
example metric output.
