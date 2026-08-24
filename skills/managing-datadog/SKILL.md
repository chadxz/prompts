---
name: managing-datadog
description:
  Manages Datadog dashboards, SLOs, monitors, and synthetic tests as
  code — push (create/update), pull (download), and list resources via
  the Datadog API. Prefers the pup CLI over direct API calls when pup
  is available and authenticated. Complements the Datadog MCP server.
  Use when the user mentions Datadog dashboards, SLOs, monitors,
  synthetics, or wants to push/pull/list Datadog resources.
user-invocable: false
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep"]
---

# Datadog Resource Management

## Prefer pup over direct API calls

When the `pup` CLI is available and authenticated, prefer it over raw `curl` or
other direct HTTP requests to the Datadog API. Check first:

```bash
command -v pup >/dev/null && pup auth status
```

`pup` is authenticated when `pup auth status` reports an active session, or when
`DD_API_KEY` and `DD_APP_KEY` are set in the environment.

- Prefer dedicated pup commands when they cover the need (`pup monitors`,
  `pup dashboards`, `pup slos`, `pup synthetics`, metrics/logs/APM helpers, and
  similar).
- Use `pup api <endpoint>` for endpoints without a dedicated command.
- Pass `--yes` for non-interactive writes. When authoring a script the user will
  run outside an agent session, add `--no-agent` so output shape matches their
  shell.
- Do not invent `curl` + API-key calls while pup can complete the request.

Keep using the bundled script below for the push/pull/list as-code workflow it
owns (create-vs-update, ID pull-back, response unwrapping). That script already
routes synthetics through pup; use pup directly for ad-hoc Datadog API work the
script does not cover.

## Credentials

The following Datadog credentials were loaded from 1Password at invocation time.
Use them as inline env var exports when calling the script — do NOT wrap
commands with `op run`. For pup-only work with an active OAuth session, these
keys are optional.

!`op run -- bash -c 'echo "DD_API_KEY=${DD_API_KEY:-$DATADOG_API_KEY}"; echo "DD_APP_KEY=${DD_APP_KEY:-$DATADOG_APP_KEY}"; echo "DD_SITE=${DD_SITE:-${DATADOG_SITE:-us3.datadoghq.com}}"' 2>&1`

If the output above shows errors, empty values, or `op` is not found, read
[credentials setup](reference/credentials.md) and help the user configure their
environment. If pup is already authenticated via `pup auth login`, continue with
pup instead of blocking on API-key setup.

## Script

For push, pull, and list operations on dashboards, SLOs, monitors, and synthetic
tests, delegate to the bundled script:

```bash
DD_API_KEY={api_key} DD_APP_KEY={app_key} DD_SITE={site} \
  bash ${CLAUDE_SKILL_DIR}/scripts/datadog.sh <resource> <command> [args...]
```

Substitute `{api_key}`, `{app_key}`, and `{site}` with the resolved credential
values above.

### Supported operations

| Resource    | Command | Arguments                        |
| ----------- | ------- | -------------------------------- |
| `dashboard` | `push`  | `<file.json>`                    |
| `dashboard` | `pull`  | `<id> [output_file.json]`        |
| `dashboard` | `list`  | `[query]`                        |
| `slo`       | `push`  | `<file.json>`                    |
| `slo`       | `pull`  | `<id> [output_file.json]`        |
| `slo`       | `list`  | `[query]`                        |
| `monitor`   | `push`  | `<file.json>`                    |
| `monitor`   | `pull`  | `<id> [output_file.json]`        |
| `monitor`   | `list`  | `[query]`                        |
| `synthetic` | `push`  | `<file.json>`                    |
| `synthetic` | `pull`  | `<public_id> [output_file.json]` |
| `synthetic` | `list`  | `[query]`                        |

The script handles create-vs-update logic (presence of `id` field, or
`public_id` for synthetics), post-create pull-back to persist assigned IDs,
response unwrapping, and credential validation automatically.

`synthetic` commands require the `pup` CLI; the script already routes those
calls through pup. pup uses the same DD_API_KEY/DD_APP_KEY values when set and
falls back to its own OAuth session (`pup auth login`) otherwise.

## File organization

Store resource JSON files in subdirectories under `datadog/` relative to the
working directory:

```
datadog/dashboards/
datadog/slos/
datadog/monitors/
datadog/synthetics/
```

Create directories as needed. When pulling without an explicit output file, save
to the appropriate subdirectory using the resource ID as the filename. Adjust
paths if the user specifies a preference.

## Beyond push/pull/list

For capabilities the script does not cover — querying metrics, managing
incidents, viewing traces, APM, synthetic test results, error tracking, security
signals, etc. — prefer **pup** (dedicated commands or `pup api`) when it is
available and authenticated. Fall back to the **Datadog MCP server** tools
(prefixed `datadog-mcp:`) when pup cannot complete the task or MCP is a better
fit for interactive investigation.

If the Datadog MCP server is not configured, read
[MCP setup](reference/mcp-setup.md) and guide the user through adding it.
