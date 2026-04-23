# pi-slack-mcp

Slack MCP extension for pi.

It connects pi to Slack's official MCP server, discovers the available
Slack tools after auth, and keeps the TUI output compact so Slack results
don't take over the whole session. It does not add a persistent status
bar item.

## Slack app setup

Create or open a Slack app, then make these changes in the Slack app
settings:

1. Under **Agents & AI Apps**, turn **Model Context Protocol** on.
2. Under **OAuth & Permissions**, add the redirect URL your pi client will
   use.
3. Make sure the app has the user scopes your workflow needs.

The default redirect URL for this extension is:

- `http://127.0.0.1:8315/oauth/callback`

That URL must match the Slack app exactly.

You do not need a separate manual "Install App" step in the Slack app UI
for this extension. The actual user authorization happens when you run
`/slack-mcp` or `slack_mcp_connect`, which opens Slack's OAuth consent
screen. If your workspace requires app approval, Slack will stop you there
and ask for approval.

If Slack returns `App is not enabled for Slack MCP server access`, the
**Model Context Protocol** toggle is still off on the Slack app.

## Use

- `/slack-mcp`
- `slack_mcp_connect`
- `slack_mcp_status`
- `slack_mcp_disconnect`

After connecting, the extension discovers the full Slack MCP tool surface
and registers the server tools dynamically.

## Configuration

The extension supports these environment variables and matching pi flags:

- `SLACK_MCP_CLIENT_ID`
- `SLACK_MCP_CLIENT_SECRET`
- `SLACK_MCP_REDIRECT_URI`
- `SLACK_MCP_AUTH_FILE`

`SLACK_MCP_AUTH_FILE` defaults to `~/.pi/agent/slack-mcp-auth.json`.

## Development

- `npm test`
- `npm run lint`
- `npm run check`
