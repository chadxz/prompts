---
name: managing-datadog
description:
  Manages Datadog dashboards, SLOs, and monitors as code — push
  (create/update), pull (download), and list resources via the Datadog
  API. Complements the Datadog MCP server. Use when the user mentions
  Datadog dashboards, SLOs, monitors, or wants to push/pull/list
  Datadog resources.
user-invocable: false
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep"]
---

# Datadog Resource Management

## Credentials

The following Datadog credentials were loaded from 1Password at
invocation time. Use them as inline env var exports when calling the
script — do NOT wrap commands with `op run`.

!`op run -- bash -c 'echo "DD_API_KEY=${DD_API_KEY:-$DATADOG_API_KEY}"; echo "DD_APP_KEY=${DD_APP_KEY:-$DATADOG_APP_KEY}"; echo "DD_SITE=${DD_SITE:-${DATADOG_SITE:-us3.datadoghq.com}}"' 2>&1`

If the output above shows errors, empty values, or `op` is not found,
read [credentials setup](reference/credentials.md) and help the user
configure their environment.

## Script

For push, pull, and list operations on dashboards, SLOs, and monitors,
delegate to the bundled script:

```bash
DD_API_KEY={api_key} DD_APP_KEY={app_key} DD_SITE={site} \
  bash ${CLAUDE_SKILL_DIR}/scripts/datadog.sh <resource> <command> [args...]
```

Substitute `{api_key}`, `{app_key}`, and `{site}` with the resolved
credential values above.

### Supported operations

| Resource    | Command | Arguments                  |
|-------------|---------|----------------------------|
| `dashboard` | `push`  | `<file.json>`              |
| `dashboard` | `pull`  | `<id> [output_file.json]`  |
| `dashboard` | `list`  | `[query]`                  |
| `slo`       | `push`  | `<file.json>`              |
| `slo`       | `pull`  | `<id> [output_file.json]`  |
| `slo`       | `list`  | `[query]`                  |
| `monitor`   | `push`  | `<file.json>`              |
| `monitor`   | `pull`  | `<id> [output_file.json]`  |
| `monitor`   | `list`  | `[query]`                  |

The script handles create-vs-update logic (presence of `id` field),
post-create pull-back to persist assigned IDs, response unwrapping,
and credential validation automatically.

## File organization

Store resource JSON files in subdirectories under `datadog/` relative
to the working directory:

```
datadog/dashboards/
datadog/slos/
datadog/monitors/
```

Create directories as needed. When pulling without an explicit output
file, save to the appropriate subdirectory using the resource ID as
the filename. Adjust paths if the user specifies a preference.

## Beyond push/pull/list

For capabilities the script does not cover — querying metrics,
managing incidents, viewing traces, APM, synthetics, error tracking,
security signals, etc. — delegate to the **Datadog MCP server**
tools (prefixed `datadog-mcp:`).

If the Datadog MCP server is not configured, read
[MCP setup](reference/mcp-setup.md) and guide the user through
adding it.
