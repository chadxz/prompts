/**
 * Cloudflare MCP provider for pi-mux.
 *
 * Connects to Cloudflare's code-mode API server with OAuth, persists the OAuth
 * client and tokens locally, and exposes the server's compact tool catalog to
 * pi-mux.
 */

import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createServer, type Server } from "node:http";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { promisify } from "node:util";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import {
  type OAuthClientProvider,
  type OAuthDiscoveryState,
  UnauthorizedError,
} from "@modelcontextprotocol/sdk/client/auth.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type {
  OAuthClientInformationMixed,
  OAuthClientMetadata,
  OAuthTokens,
} from "@modelcontextprotocol/sdk/shared/auth.js";

const CLOUDFLARE_MCP_URL = "https://mcp.cloudflare.com/mcp";
const CLOUDFLARE_AUTH_HOST = "mcp.cloudflare.com";
const CLOUDFLARE_OAUTH_ISSUER = "https://mcp.cloudflare.com";
const CLOUDFLARE_MCP_AUTH_FILE_ENV = "CLOUDFLARE_MCP_AUTH_FILE";
const PI_CODING_AGENT_DIR_ENV = "PI_CODING_AGENT_DIR";
const DEFAULT_PI_AGENT_DIR = "~/.pi/agent";
const DEFAULT_AUTH_FILE_NAME = "cloudflare-mcp-auth.json";
const DEFAULT_CALLBACK_PORT = 8766;
const CALLBACK_PATH = "/oauth/callback";
const CALLBACK_TIMEOUT_MS = 300_000;
const MCP_TOOL_TIMEOUT_MS = 300_000;
const execFileAsync = promisify(execFile);

type NotifyLevel = "info" | "warning" | "error";
type NotifyFn = (message: string, type?: NotifyLevel) => void;

type ToolExecutionResult = {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
  details: Record<string, unknown>;
};

type MCPTool = {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
};

type StoredOAuthConfig = {
  clientInformation?: OAuthClientInformationMixed;
  tokens?: OAuthTokens;
  codeVerifier?: string;
  discoveryState?: OAuthDiscoveryState;
};

type CloudflareMCPState = {
  connected: boolean;
  sessionId: string | null;
  mcpUrl: string;
};

/** Returns the current user's home directory without mutating shell state. */
function getHomeDir(): string {
  return process.env.HOME || homedir();
}

/** Resolves a user-configurable path against the current process. */
function resolveOptionalPath(filePath: string): string {
  const trimmed = filePath.trim();
  if (trimmed.startsWith("~/")) {
    return join(getHomeDir(), trimmed.slice(2));
  }
  if (trimmed.startsWith("~")) {
    return join(getHomeDir(), trimmed.slice(1));
  }
  if (isAbsolute(trimmed)) {
    return trimmed;
  }
  return resolve(process.cwd(), trimmed);
}

/** Returns the default private file used for Cloudflare OAuth state. */
function getDefaultAuthFilePath(): string {
  const agentDir = resolveOptionalPath(
    process.env[PI_CODING_AGENT_DIR_ENV] || DEFAULT_PI_AGENT_DIR,
  );
  return join(agentDir, DEFAULT_AUTH_FILE_NAME);
}

/** Narrows unknown JSON values to ordinary records. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Converts a caught value into a stable user-facing error message. */
function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Safely serializes MCP results for the pi fallback text channel. */
function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Counts display lines in a tool result. */
function countOutputLines(text: string): number {
  return text.length === 0 ? 0 : text.split(/\r?\n/u).length;
}

/** Creates a successful pi tool result with mux-compatible raw details. */
function toolResult(
  tool: string,
  text: string,
  details: Record<string, unknown> = {},
): ToolExecutionResult {
  return {
    content: [{ type: "text", text }],
    details: {
      tool,
      lineCount: countOutputLines(text),
      characterCount: text.length,
      ...details,
    },
  };
}

/** Creates a failed pi tool result without throwing across the mux boundary. */
function toolError(
  tool: string,
  text: string,
  details: Record<string, unknown> = {},
): ToolExecutionResult {
  return {
    content: [{ type: "text", text }],
    isError: true,
    details: { tool, ...details },
  };
}

/**
 * Stores OAuth material in a user-readable file so Pi sessions can reconnect
 * without repeating browser authorization.
 */
class FileOAuthStorage {
  private readonly filePath: string;

  constructor(filePath = getDefaultAuthFilePath()) {
    this.filePath = resolveOptionalPath(filePath);
  }

  /** Loads previously persisted OAuth state, ignoring malformed files. */
  load(): StoredOAuthConfig {
    if (!existsSync(this.filePath)) {
      return {};
    }

    try {
      const parsed = JSON.parse(readFileSync(this.filePath, "utf8"));
      return isRecord(parsed) ? (parsed as StoredOAuthConfig) : {};
    } catch {
      return {};
    }
  }

  /** Persists OAuth state with owner-only permissions. */
  save(config: StoredOAuthConfig): void {
    mkdirSync(dirname(this.filePath), { recursive: true });
    writeFileSync(this.filePath, `${JSON.stringify(config, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    chmodSync(this.filePath, 0o600);
  }

  /** Removes all locally persisted OAuth state. */
  clear(): void {
    rmSync(this.filePath, { force: true });
  }
}

/**
 * Supplies the MCP SDK with durable Cloudflare OAuth state and captures the
 * authorization URL for Pi's browser handoff.
 */
class CloudflareOAuthProvider implements OAuthClientProvider {
  private config: StoredOAuthConfig;
  private currentState?: string;
  private readonly storage: FileOAuthStorage;
  pendingAuthorizationUrl?: URL;

  readonly redirectUrl: string;

  constructor(storage: FileOAuthStorage, redirectUrl: string) {
    this.storage = storage;
    this.redirectUrl = redirectUrl;
    this.config = storage.load();
  }

  /** Describes Pi as a native public OAuth client for dynamic registration. */
  get clientMetadata(): OAuthClientMetadata {
    return {
      client_name: "Pi Cloudflare MCP",
      redirect_uris: [this.redirectUrl],
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
      application_type: "native",
      token_endpoint_auth_method: "none",
    };
  }

  /** Generates and remembers the CSRF state value for the current flow. */
  state(): string {
    this.currentState = randomUUID();
    return this.currentState;
  }

  /** Exposes the expected OAuth state to the loopback callback validator. */
  get expectedState(): string | undefined {
    return this.currentState;
  }

  /** Reports whether locally stored tokens are available for reconnection. */
  get hasTokens(): boolean {
    return Boolean(this.config.tokens?.access_token);
  }

  /** Returns the registered OAuth client information for Cloudflare. */
  clientInformation(): OAuthClientInformationMixed | undefined {
    return this.config.clientInformation;
  }

  /** Persists dynamically registered OAuth client information. */
  saveClientInformation(clientInformation: OAuthClientInformationMixed): void {
    this.config.clientInformation = clientInformation;
    this.persist();
  }

  /** Returns the current access and refresh tokens. */
  tokens(): OAuthTokens | undefined {
    return this.config.tokens;
  }

  /** Persists refreshed or newly issued tokens. */
  saveTokens(tokens: OAuthTokens): void {
    this.config.tokens = tokens;
    this.persist();
  }

  /** Captures the SDK-generated authorization URL for a safe browser open. */
  redirectToAuthorization(authorizationUrl: URL): void {
    this.pendingAuthorizationUrl = authorizationUrl;
  }

  /** Persists the PKCE verifier needed to exchange the callback code. */
  saveCodeVerifier(codeVerifier: string): void {
    this.config.codeVerifier = codeVerifier;
    this.persist();
  }

  /** Returns the verifier for the pending OAuth authorization flow. */
  codeVerifier(): string {
    if (!this.config.codeVerifier) {
      throw new Error("Cloudflare OAuth code verifier is missing.");
    }
    return this.config.codeVerifier;
  }

  /** Persists the OAuth discovery result for later refreshes. */
  saveDiscoveryState(discoveryState: OAuthDiscoveryState): void {
    this.config.discoveryState = discoveryState;
    this.persist();
  }

  /** Returns cached OAuth protected-resource and issuer discovery state. */
  discoveryState(): OAuthDiscoveryState | undefined {
    return this.config.discoveryState;
  }

  /** Clears the credential subset the SDK reports as invalid. */
  invalidateCredentials(
    scope: "all" | "client" | "tokens" | "verifier" | "discovery",
  ): void {
    if (scope === "all" || scope === "client") {
      delete this.config.clientInformation;
    }
    if (scope === "all" || scope === "tokens") {
      delete this.config.tokens;
    }
    if (scope === "all" || scope === "verifier") {
      delete this.config.codeVerifier;
    }
    if (scope === "all" || scope === "discovery") {
      delete this.config.discoveryState;
    }
    this.persist();
  }

  /** Resets ephemeral state before beginning a fresh browser flow. */
  prepareAuthorization(): void {
    this.currentState = undefined;
    this.pendingAuthorizationUrl = undefined;
  }

  /** Clears every local OAuth artifact during an explicit disconnect. */
  clear(): void {
    this.config = {};
    this.currentState = undefined;
    this.pendingAuthorizationUrl = undefined;
    this.storage.clear();
  }

  /** Writes the current OAuth state to its private file. */
  private persist(): void {
    this.storage.save(this.config);
  }
}

/**
 * Receives the browser's OAuth redirect on a fixed loopback URL and validates
 * the state value before exposing the authorization code.
 */
class OAuthCallbackListener {
  readonly result: Promise<string>;

  private readonly provider: CloudflareOAuthProvider;
  private readonly server: Server;
  private settled = false;
  private timeout?: NodeJS.Timeout;

  private constructor(server: Server, provider: CloudflareOAuthProvider) {
    this.server = server;
    this.provider = provider;
    this.result = new Promise<string>((resolveResult, rejectResult) => {
      this.timeout = setTimeout(() => {
        this.finish(() => rejectResult(new Error("Cloudflare OAuth callback timed out.")));
      }, CALLBACK_TIMEOUT_MS);

      server.on("request", (request, response) => {
        const callbackUrl = new URL(request.url ?? "/", "http://127.0.0.1");
        if (callbackUrl.pathname !== CALLBACK_PATH) {
          response.writeHead(404).end();
          return;
        }

        const expectedState = this.provider.expectedState;
        if (!expectedState || callbackUrl.searchParams.get("state") !== expectedState) {
          response.writeHead(400, { "Content-Type": "text/html; charset=utf-8" });
          response.end("<h1>Authorization rejected</h1><p>OAuth state did not match.</p>");
          return;
        }

        if (!isExpectedAuthorizationIssuer(callbackUrl.searchParams.get("iss"))) {
          response.writeHead(400, { "Content-Type": "text/html; charset=utf-8" });
          response.end("<h1>Authorization rejected</h1><p>OAuth issuer did not match.</p>");
          return;
        }

        if (callbackUrl.searchParams.has("error")) {
          response.writeHead(400, { "Content-Type": "text/html; charset=utf-8" });
          response.end("<h1>Authorization was not completed</h1><p>You can close this window.</p>");
          this.finish(() => rejectResult(new Error("Cloudflare authorization was denied.")));
          return;
        }

        const code = callbackUrl.searchParams.get("code");
        if (!code) {
          response.writeHead(400, { "Content-Type": "text/html; charset=utf-8" });
          response.end("<h1>Authorization failed</h1><p>The callback did not include a code.</p>");
          return;
        }

        response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        response.end("<h1>Cloudflare connected</h1><p>You can close this window and return to Pi.</p>");
        this.finish(() => resolveResult(code));
      });

      server.on("error", (error) => {
        this.finish(() => rejectResult(error));
      });
    });
  }

  /** Opens the fixed loopback listener required by Cloudflare's OAuth client. */
  static async open(provider: CloudflareOAuthProvider): Promise<OAuthCallbackListener> {
    const server = createServer();
    const listener = new OAuthCallbackListener(server, provider);

    await new Promise<void>((resolveListen, rejectListen) => {
      const handleListenError = (error: Error) => rejectListen(error);
      server.once("error", handleListenError);
      server.listen(DEFAULT_CALLBACK_PORT, "127.0.0.1", () => {
        server.off("error", handleListenError);
        resolveListen();
      });
    });

    return listener;
  }

  /** Stops the callback listener when an OAuth attempt finishes or fails. */
  close(): void {
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = undefined;
    }
    if (this.server.listening) {
      this.server.close();
    }
  }

  /** Settles the result once and closes the callback listener. */
  private finish(settle: () => void): void {
    if (this.settled) {
      return;
    }
    this.settled = true;
    this.close();
    settle();
  }
}

/**
 * Owns the MCP SDK client and the live Cloudflare tool catalog for one Pi
 * process.
 */
class CloudflareMCPClient {
  readonly state: CloudflareMCPState = {
    connected: false,
    sessionId: null,
    mcpUrl: CLOUDFLARE_MCP_URL,
  };

  private client?: Client;
  private transport?: StreamableHTTPClientTransport;
  private pendingClient?: Client;
  private pendingTransport?: StreamableHTTPClientTransport;
  private tools: MCPTool[] = [];

  /** Connects with stored tokens or prepares the provider's OAuth redirect. */
  async connect(provider: CloudflareOAuthProvider): Promise<void> {
    if (this.state.connected) {
      return;
    }

    const client = new Client({ name: "pi-cloudflare-mcp", version: "1.0.0" });
    const transport = new StreamableHTTPClientTransport(
      new URL(CLOUDFLARE_MCP_URL),
      { authProvider: provider },
    );

    try {
      await client.connect(transport);
      const toolList = await client.listTools();
      this.client = client;
      this.transport = transport;
      this.pendingClient = undefined;
      this.pendingTransport = undefined;
      this.tools = toolList.tools.map((tool) => ({
        name: tool.name,
        description: tool.description ?? "",
        inputSchema: tool.inputSchema as Record<string, unknown>,
        outputSchema: isRecord(tool.outputSchema) ? tool.outputSchema : undefined,
      }));
      this.state.connected = true;
      this.state.sessionId = transport.sessionId ?? null;
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        this.pendingClient = client;
        this.pendingTransport = transport;
      } else {
        await client.close().catch(() => undefined);
      }
      throw error;
    }
  }

  /** Exchanges the browser callback code on the challenged transport. */
  async finishAuthorization(code: string): Promise<void> {
    if (!this.pendingTransport) {
      throw new Error("Cloudflare OAuth transport is not awaiting authorization.");
    }

    await this.pendingTransport.finishAuth(code);
    await this.pendingClient?.close().catch(() => undefined);
    this.pendingClient = undefined;
    this.pendingTransport = undefined;
  }

  /** Calls one Cloudflare MCP tool and preserves the upstream result. */
  async callTool(
    name: string,
    args: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<unknown> {
    if (!this.client || !this.state.connected) {
      throw new Error("Cloudflare MCP is not connected.");
    }

    return await this.client.callTool(
      { name, arguments: args },
      undefined,
      { signal, timeout: MCP_TOOL_TIMEOUT_MS },
    );
  }

  /** Returns the discovered compact Cloudflare tool catalog. */
  getTools(): MCPTool[] {
    return [...this.tools];
  }

  /** Closes active and challenged transports and clears in-memory state. */
  async disconnect(): Promise<void> {
    await this.client?.close().catch(() => undefined);
    await this.pendingClient?.close().catch(() => undefined);
    this.client = undefined;
    this.transport = undefined;
    this.pendingClient = undefined;
    this.pendingTransport = undefined;
    this.tools = [];
    this.state.connected = false;
    this.state.sessionId = null;
  }
}

/** Restricts SDK-discovered authorization URLs to Cloudflare over HTTPS. */
function isSafeAuthorizationUrl(authorizationUrl: URL): boolean {
  return authorizationUrl.protocol === "https:"
    && authorizationUrl.hostname === CLOUDFLARE_AUTH_HOST;
}

/** Accepts Cloudflare's issuer when present and tolerates its current omission. */
function isExpectedAuthorizationIssuer(issuer: string | null): boolean {
  return issuer === null || issuer === CLOUDFLARE_OAUTH_ISSUER;
}

/** Opens an authorization URL in the user's default macOS browser. */
async function openBrowser(authorizationUrl: URL): Promise<void> {
  if (!isSafeAuthorizationUrl(authorizationUrl)) {
    throw new Error(`Refusing unexpected OAuth URL: ${authorizationUrl.origin}`);
  }
  await execFileAsync("open", [authorizationUrl.toString()]);
}

/** Converts an MCP result into readable text while retaining its raw form. */
function formatMcpResult(rawResult: unknown): string {
  if (!isRecord(rawResult) || !Array.isArray(rawResult.content)) {
    return safeJsonStringify(rawResult);
  }

  const parts = rawResult.content.map((entry) => {
    if (isRecord(entry) && entry.type === "text" && typeof entry.text === "string") {
      return entry.text;
    }
    return safeJsonStringify(entry);
  });
  return parts.join("\n").trim();
}

/** Formats connection state for Pi and pi-mux status views. */
function getConnectionStatusText(client: CloudflareMCPClient): string {
  const tools = client.getTools();
  const session = client.state.sessionId
    ? `${client.state.sessionId.slice(0, 8)}...`
    : "None";
  return [
    "Cloudflare MCP Status:",
    `- Connected: ${client.state.connected ? "Yes" : "No"}`,
    `- URL: ${client.state.mcpUrl}`,
    `- Session: ${session}`,
    `- Tools: ${tools.length} available`,
    ...(!client.state.connected ? ["", "Run /mux connect cloudflare to connect."] : []),
  ].join("\n");
}

/** Tries a silent reconnect only when durable OAuth tokens already exist. */
async function connectWithSavedConfig(
  client: CloudflareMCPClient,
  provider: CloudflareOAuthProvider,
): Promise<boolean> {
  if (!provider.hasTokens) {
    return false;
  }

  try {
    await client.connect(provider);
    return true;
  } catch {
    await client.disconnect();
    return false;
  }
}

/** Runs OAuth in the browser, exchanges the code, and connects the MCP client. */
async function performInteractiveOAuth(
  client: CloudflareMCPClient,
  provider: CloudflareOAuthProvider,
  notify: NotifyFn,
): Promise<void> {
  await client.disconnect();
  provider.prepareAuthorization();
  const callback = await OAuthCallbackListener.open(provider);

  try {
    notify("Preparing Cloudflare authorization...");
    try {
      await client.connect(provider);
      callback.close();
      return;
    } catch (error) {
      if (!(error instanceof UnauthorizedError)) {
        throw error;
      }
    }

    const authorizationUrl = provider.pendingAuthorizationUrl;
    if (!authorizationUrl) {
      throw new Error("Cloudflare did not provide an OAuth authorization URL.");
    }

    notify("Opening Cloudflare authorization in your browser...");
    await openBrowser(authorizationUrl);
    notify("Waiting for the Cloudflare authorization callback...");
    const code = await callback.result;
    await client.finishAuthorization(code);
    await client.connect(provider);
  } finally {
    callback.close();
  }
}

/** Creates a Pi definition for one dynamically discovered Cloudflare tool. */
function createRegisteredToolDefinition(
  client: CloudflareMCPClient,
  tool: MCPTool,
) {
  return {
    name: tool.name,
    label: `Cloudflare: ${tool.name}`,
    description: tool.description || `Cloudflare MCP tool: ${tool.name}`,
    parameters: Type.Unsafe(tool.inputSchema),
    outputSchema: tool.outputSchema,
    async execute(
      _toolCallId: string,
      params: unknown,
      signal?: AbortSignal,
      onUpdate?: (payload: {
        content: Array<{ type: "text"; text: string }>;
        details?: Record<string, unknown>;
      }) => void,
    ): Promise<ToolExecutionResult> {
      if (!client.state.connected) {
        return toolError(
          tool.name,
          "Cloudflare MCP is unavailable. Run /mux connect cloudflare.",
        );
      }

      onUpdate?.({
        content: [{ type: "text", text: `Running Cloudflare ${tool.name}...` }],
        details: { tool: tool.name, phase: "running" },
      });

      try {
        const args = isRecord(params) ? params : {};
        const rawResult = await client.callTool(tool.name, args, signal);
        const text = formatMcpResult(rawResult);
        const result = toolResult(tool.name, text, { rawResult });
        if (isRecord(rawResult) && rawResult.isError === true) {
          result.isError = true;
        }
        return result;
      } catch (error) {
        const message = getErrorMessage(error);
        return toolError(tool.name, `Cloudflare MCP error: ${message}`, {
          error: message,
        });
      }
    },
  };
}

/** Registers newly discovered Cloudflare tools with Pi exactly once. */
function registerDiscoveredTools(
  pi: ExtensionAPI,
  client: CloudflareMCPClient,
): number {
  let registered = 0;
  const existing = new Set(pi.getAllTools().map((tool) => tool.name));
  for (const tool of client.getTools()) {
    if (existing.has(tool.name)) {
      continue;
    }
    pi.registerTool(createRegisteredToolDefinition(client, tool));
    existing.add(tool.name);
    registered += 1;
  }
  return registered;
}

/** Resolves an optional Pi flag or environment override for OAuth storage. */
function resolveAuthFilePath(pi: ExtensionAPI): string {
  const flag = pi.getFlag("--cloudflare-mcp-auth-file");
  if (typeof flag === "string" && flag.trim().length > 0) {
    return flag;
  }
  return process.env[CLOUDFLARE_MCP_AUTH_FILE_ENV] || getDefaultAuthFilePath();
}

/** Registers the Cloudflare provider, control command, and mux control tools. */
export default function cloudflareMcpExtension(pi: ExtensionAPI): void {
  pi.registerFlag("--cloudflare-mcp-auth-file", {
    description: "Path to the persisted Cloudflare MCP OAuth file.",
    type: "string",
  });

  const callbackUrl = `http://127.0.0.1:${DEFAULT_CALLBACK_PORT}${CALLBACK_PATH}`;
  const storage = new FileOAuthStorage(resolveAuthFilePath(pi));
  const provider = new CloudflareOAuthProvider(storage, callbackUrl);
  const client = new CloudflareMCPClient();

  pi.on("session_start", async () => {
    if (await connectWithSavedConfig(client, provider)) {
      registerDiscoveredTools(pi, client);
    }
  });

  pi.registerCommand("cloudflare-mcp", {
    description: "Connect to Cloudflare MCP with OAuth or disconnect",
    async handler(_args, ctx) {
      if (client.state.connected) {
        const choice = await ctx.ui.select(getConnectionStatusText(client), [
          "Disconnect",
          "Cancel",
        ]);
        if (choice !== "Disconnect") {
          return;
        }
        await client.disconnect();
        provider.clear();
        ctx.ui.notify("Disconnected from Cloudflare MCP and cleared local OAuth state.", "info");
        return;
      }

      const notify: NotifyFn = (message, level = "info") => {
        ctx.ui.notify(message, level);
      };
      try {
        await performInteractiveOAuth(client, provider, notify);
        const registered = registerDiscoveredTools(pi, client);
        ctx.ui.notify(
          `Connected to Cloudflare MCP (${client.getTools().length} tools, ${registered} newly registered).`,
          "info",
        );
      } catch (error) {
        ctx.ui.notify(`Cloudflare MCP connection failed: ${getErrorMessage(error)}`, "error");
      }
    },
  });

  pi.registerTool({
    name: "cloudflare_mcp_connect",
    label: "Cloudflare MCP Connect",
    description: "Connect to Cloudflare's official API MCP server using OAuth",
    parameters: Type.Object({}),
    async execute(): Promise<ToolExecutionResult> {
      if (!client.state.connected && await connectWithSavedConfig(client, provider)) {
        registerDiscoveredTools(pi, client);
      }

      if (!client.state.connected) {
        return toolError(
          "cloudflare_mcp_connect",
          "Cloudflare MCP requires interactive OAuth setup.",
          { connected: false, requiresInteractiveSetup: true },
        );
      }

      const tools = client.getTools();
      return toolResult(
        "cloudflare_mcp_connect",
        `Connected to Cloudflare MCP with ${tools.length} tools: ${tools.map((tool) => tool.name).join(", ")}`,
        {
          connected: true,
          sessionId: client.state.sessionId,
          mcpUrl: client.state.mcpUrl,
          toolCount: tools.length,
        },
      );
    },
  });

  pi.registerTool({
    name: "cloudflare_mcp_disconnect",
    label: "Cloudflare MCP Disconnect",
    description: "Disconnect from Cloudflare MCP and clear local OAuth state",
    parameters: Type.Object({}),
    async execute(): Promise<ToolExecutionResult> {
      await client.disconnect();
      provider.clear();
      return toolResult(
        "cloudflare_mcp_disconnect",
        "Disconnected from Cloudflare MCP and cleared local OAuth state.",
        { connected: false },
      );
    },
  });

  pi.registerTool({
    name: "cloudflare_mcp_status",
    label: "Cloudflare MCP Status",
    description: "Check the Cloudflare MCP connection state",
    parameters: Type.Object({}),
    async execute(): Promise<ToolExecutionResult> {
      return toolResult(
        "cloudflare_mcp_status",
        getConnectionStatusText(client),
        {
          connected: client.state.connected,
          sessionId: client.state.sessionId,
          mcpUrl: client.state.mcpUrl,
          toolCount: client.getTools().length,
        },
      );
    },
  });
}

export {
  CALLBACK_PATH,
  CLOUDFLARE_MCP_URL,
  CloudflareMCPClient,
  CloudflareOAuthProvider,
  FileOAuthStorage,
  getConnectionStatusText,
  getDefaultAuthFilePath,
  isExpectedAuthorizationIssuer,
  isSafeAuthorizationUrl,
  performInteractiveOAuth,
};
