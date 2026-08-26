/**
 * Codex-compatible stdio adapter for Cloudflare's official remote MCP server.
 *
 * Codex's native OAuth callback currently rejects Cloudflare's production
 * response because it omits an advertised issuer parameter. This adapter uses
 * the MCP TypeScript SDK, keeps an independent OAuth grant under ~/.codex, and
 * forwards the remote server's compact tool surface over stdio.
 */

import { homedir } from "node:os";
import { join } from "node:path";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import {
  CloudflareMCPClient,
  CloudflareOAuthProvider,
  FileOAuthStorage,
  performInteractiveOAuth,
} from "./pi-cloudflare-mcp.ts";

const CALLBACK_URL = "http://127.0.0.1:8766/oauth/callback";
const CODEX_AUTH_FILE_ENV = "CLOUDFLARE_CODEX_MCP_AUTH_FILE";
const DEFAULT_CODEX_AUTH_FILE = join(
  process.env.HOME || homedir(),
  ".codex",
  "cloudflare-mcp-auth.json",
);

/** Creates the OAuth provider and remote client used by both adapter modes. */
function createCloudflareConnection(): {
  client: CloudflareMCPClient;
  provider: CloudflareOAuthProvider;
} {
  const authFile = process.env[CODEX_AUTH_FILE_ENV] || DEFAULT_CODEX_AUTH_FILE;
  const storage = new FileOAuthStorage(authFile);
  return {
    client: new CloudflareMCPClient(),
    provider: new CloudflareOAuthProvider(storage, CALLBACK_URL),
  };
}

/** Runs the one-time browser authorization flow for the Codex adapter. */
async function authenticate(): Promise<void> {
  const { client, provider } = createCloudflareConnection();
  try {
    await performInteractiveOAuth(client, provider, (message) => {
      process.stderr.write(`${message}\n`);
    });
    process.stdout.write(
      `Authenticated with Cloudflare MCP (${client.getTools().length} tools).\n`,
    );
  } finally {
    await client.disconnect();
  }
}

/** Starts the local stdio server and forwards Cloudflare tool requests. */
async function serve(): Promise<void> {
  const { client, provider } = createCloudflareConnection();
  await client.connect(provider);

  const server = new Server(
    { name: "cloudflare-mcp-stdio", version: "1.0.0" },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: client.getTools(),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const result = await client.callTool(
      request.params.name,
      request.params.arguments ?? {},
    );
    return result as {
      content: Array<{ type: "text"; text: string }>;
      isError?: boolean;
      structuredContent?: Record<string, unknown>;
    };
  });

  server.onclose = async () => {
    await client.disconnect();
  };

  await server.connect(new StdioServerTransport());
}

/** Selects authentication or stdio serving based on the command-line mode. */
async function main(): Promise<void> {
  if (process.argv.includes("--authenticate")) {
    await authenticate();
    return;
  }
  await serve();
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`Cloudflare MCP adapter failed: ${message}\n`);
  process.exitCode = 1;
});
