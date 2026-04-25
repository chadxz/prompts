# pi-datadog-mcp

`pi-datadog-mcp` connects pi to Datadog's managed MCP server. It handles
Datadog auth, discovers the MCP tools exposed by the current Datadog
session, and keeps the TUI output compact enough to stay readable.

## What it does

The extension adds these entry points:

- `/datadog-mcp`
- `datadog_mcp_connect`
- `datadog_mcp_status`
- `datadog_mcp_disconnect`

After connecting, it discovers the Datadog MCP tools for the current
site and toolsets, then registers them dynamically.

When you reconnect with a different site or toolset selection, the
extension updates the active Datadog tool set to match the new MCP
session. Tools discovered from an older session stay registered for the
life of the pi process, but stale ones are deactivated and won't be
offered as active tools.

## Authentication

The extension supports both Datadog MCP auth paths:

- OAuth 2.1 with PKCE and dynamic client registration
- API key + application key header auth

If saved header credentials are available, the extension uses them. If
saved OAuth tokens are available, it uses those. If neither is
configured, the default interactive connect flow starts OAuth.

The default OAuth redirect URI is:

- `http://127.0.0.1:8563/oauth/callback`

## Configuration

The extension supports these environment variables and matching pi
flags:

- `DATADOG_MCP_SITE`
- `DATADOG_MCP_URL`
- `DATADOG_MCP_TOOLSETS`
- `DATADOG_MCP_REDIRECT_URI`
- `DATADOG_MCP_AUTH_FILE`
- `DD_API_KEY`
- `DD_APPLICATION_KEY`

By default, the extension targets the US3 Datadog site and leaves the
server default `core` toolset in place.

`DATADOG_MCP_AUTH_FILE` defaults to:

- `~/.pi/agent/datadog-mcp-auth.json`

The persisted auth file contains bearer credentials when you use saved
OAuth or saved header auth. The extension writes it with owner-only file
permissions.

Runtime header credentials from environment variables or CLI flags are
used at runtime, but they are not copied into the persisted auth file.
If you want the keys stored on disk, save them explicitly with the
`/datadog-mcp api-key ...` and `/datadog-mcp application-key ...`
commands.

## Useful commands

- `/datadog-mcp`
- `/datadog-mcp status`
- `/datadog-mcp oauth`
- `/datadog-mcp headers`
- `/datadog-mcp disconnect`
- `/datadog-mcp forget`
- `/datadog-mcp site us3`
- `/datadog-mcp url https://mcp.us3.datadoghq.com/api/unstable/mcp-server/mcp`
- `/datadog-mcp toolsets core,dashboards`
- `/datadog-mcp redirect-uri http://127.0.0.1:8563/oauth/callback`
- `/datadog-mcp api-key <value>`
- `/datadog-mcp application-key <value>`

If you change the site, URL, or toolsets while connected, reconnect to
pick up the new MCP session and tool list.

## Development

- `npm test`
- `npm run lint`
- `npm run check`
