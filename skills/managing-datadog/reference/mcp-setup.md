# Datadog MCP Server Setup

The managing-datadog plugin handles push, pull, and list operations for
dashboards, SLOs, and monitors. For broader Datadog capabilities, set
up the Datadog MCP server.

## What the MCP server adds

The MCP server provides access to:

- **Core** — general Datadog queries
- **Alerting** — incident and alert management
- **APM** — application performance monitoring and traces
- **DBM** — database monitoring
- **Error tracking** — error group management
- **Onboarding** — setup guidance
- **Security** — security signals and findings
- **Software delivery** — CI/CD pipelines and deployments
- **Synthetics** — synthetic test management

## Setup

Run this command to add the Datadog MCP server to Claude Code:

```bash
claude mcp add --transport http datadog-mcp \
  'https://mcp.us3.datadoghq.com/api/unstable/mcp-server/mcp?toolsets=core,alerting,apm,dbm,error-tracking,onboarding,security,software-delivery,synthetics' \
  --scope user
```

The `us3` subdomain and the `toolsets` parameter are important — they
match the Convergint Datadog site and enable the full set of
capabilities.

## Documentation

Full MCP server documentation:
https://docs.datadoghq.com/bits_ai/mcp_server/
