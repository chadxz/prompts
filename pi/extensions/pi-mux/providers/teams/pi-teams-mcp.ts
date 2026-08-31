/**
 * Microsoft Teams MCP provider for pi-mux.
 *
 * Authenticates the local user with Microsoft Entra authorization-code PKCE
 * and sends stateless bearer-authenticated requests to the hosted Teams MCP.
 */

import { execFile } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { createServer, type ServerResponse } from "node:http";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import type {
  ExtensionAPI,
  ExtensionContext,
} from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";

const DEFAULT_MCP_URL = "https://teams.mcp.convergint.tech/mcp";
const DEFAULT_CLIENT_ID = "01abdeb5-0a8a-4459-b513-54fc87eaa68b";
const DEFAULT_TENANT_ID = "2b4de1bd-251e-4878-bdb8-5180f7d15525";
const DEFAULT_CONFIG_FILE = "~/.pi/agent/teams-mcp-config.json";
const MCP_PROTOCOL_VERSION = "2026-07-28";
const MCP_TOOL_TIMEOUT_MS = 300_000;
const TOKEN_REFRESH_WINDOW_MS = 60_000;
const DEFAULT_TOKEN_LIFETIME_MS = 60 * 60 * 1000;
const TEAMS_MCP_CLIENT_ID_ENV = "TEAMS_MCP_CLIENT_ID";
const TEAMS_MCP_TENANT_ID_ENV = "TEAMS_MCP_TENANT_ID";
const TEAMS_MCP_URL_ENV = "TEAMS_MCP_URL";
const TEAMS_MCP_CONFIG_FILE_ENV = "TEAMS_MCP_PI_CONFIG_PATH";

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
type PersistedTeamsConfiguration = {
  clientId?: string;
  tenantId?: string;
  mcpUrl?: string;
  accessToken?: string;
  refreshToken?: string;
  expiresAt?: number;
};
type TeamsRuntimeOverrides = Pick<
  PersistedTeamsConfiguration,
  "clientId" | "tenantId" | "mcpUrl"
>;
type TeamsConfiguration = PersistedTeamsConfiguration & {
  clientId: string;
  tenantId: string;
  mcpUrl: string;
};
type TeamsTokenBundle = {
  accessToken: string;
  refreshToken?: string;
  expiresAt: number;
};
type OAuthCallback = {
  redirectUri: string;
  result: Promise<string>;
  close: () => void;
};
type TeamsMCPState = {
  connected: boolean;
  authenticated: boolean;
  account: string | null;
  protocolVersion: string;
  claimsChallenge: string | null;
};

/** Describes a Conditional Access claims challenge returned by the server. */
class ClaimsChallengeError extends Error {
  readonly claims: string;

  constructor(claims: string) {
    super("Microsoft requires an additional interactive authentication step.");
    this.name = "ClaimsChallengeError";
    this.claims = claims;
  }
}

/** Narrows an unknown value to an ordinary record. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Returns true when a value is a non-empty string. */
function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/** Returns one non-empty string property from a record. */
function getStringValue(
  input: Record<string, unknown>,
  ...keys: string[]
): string | undefined {
  for (const key of keys) {
    const value = input[key];
    if (isNonEmptyString(value)) {
      return value.trim();
    }
  }
  return undefined;
}

/** Converts a caught value into a stable user-facing message. */
function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

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
  return isAbsolute(trimmed) ? trimmed : resolve(process.cwd(), trimmed);
}

/** Safely serializes non-text MCP results. */
function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Extracts useful text from an MCP tool result. */
function formatMcpResult(result: unknown): string {
  if (!isRecord(result)) {
    return safeJsonStringify(result);
  }
  const content = Array.isArray(result.content) ? result.content : [];
  const text = content
    .filter(isRecord)
    .filter((item) => item.type === "text" && typeof item.text === "string")
    .map((item) => item.text as string)
    .join("\n")
    .trim();
  return text || safeJsonStringify(result.structuredContent ?? result);
}

/** Creates a successful Pi result with mux-compatible raw details. */
function toolResult(
  tool: string,
  text: string,
  details: Record<string, unknown> = {},
): ToolExecutionResult {
  return {
    content: [{ type: "text", text }],
    details: {
      tool,
      lineCount: text.length === 0 ? 0 : text.split(/\r?\n/u).length,
      characterCount: text.length,
      ...details,
    },
  };
}

/** Creates a failed Pi result without throwing across the mux boundary. */
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

/** Resolves runtime values over persisted configuration and managed defaults. */
function resolveTeamsConfiguration(
  runtime: TeamsRuntimeOverrides,
  persisted: PersistedTeamsConfiguration,
): TeamsConfiguration {
  return {
    ...persisted,
    clientId: runtime.clientId ?? persisted.clientId ?? DEFAULT_CLIENT_ID,
    tenantId: runtime.tenantId ?? persisted.tenantId ?? DEFAULT_TENANT_ID,
    mcpUrl: runtime.mcpUrl ?? persisted.mcpUrl ?? DEFAULT_MCP_URL,
  };
}

/** Persists Pi's per-user OAuth tokens with owner-only permissions. */
class TeamsConfigStorage {
  private readonly filePath: string;

  constructor(filePath: string) {
    this.filePath = resolveOptionalPath(filePath);
  }

  /** Loads configuration, ignoring missing or malformed files. */
  load(): PersistedTeamsConfiguration {
    if (!existsSync(this.filePath)) {
      return {};
    }
    try {
      const parsed = JSON.parse(readFileSync(this.filePath, "utf8"));
      return isRecord(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }

  /** Saves OAuth state with owner-only directory and file permissions. */
  save(configuration: PersistedTeamsConfiguration): void {
    const directory = dirname(this.filePath);
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    chmodSync(directory, 0o700);
    writeFileSync(
      this.filePath,
      `${JSON.stringify(configuration, null, 2)}\n`,
      { encoding: "utf8", mode: 0o600 },
    );
    chmodSync(this.filePath, 0o600);
  }
}

/** Returns the resource scope exposed by the hosted MCP registration. */
function getAccessScope(configuration: TeamsConfiguration): string {
  return `${configuration.mcpUrl.replace(/\/$/u, "")}/access_as_user`;
}

/** Derives the S256 PKCE challenge sent to Microsoft Entra. */
function createCodeChallenge(codeVerifier: string): string {
  return createHash("sha256").update(codeVerifier).digest("base64url");
}

/** Builds the tenant-specific Microsoft Entra authorization URL. */
function buildAuthorizationUrl(
  configuration: TeamsConfiguration,
  redirectUri: string,
  state: string,
  codeChallenge: string,
  claims?: string,
): URL {
  const url = new URL(
    `https://login.microsoftonline.com/${configuration.tenantId}/oauth2/v2.0/authorize`,
  );
  url.search = new URLSearchParams({
    client_id: configuration.clientId,
    response_type: "code",
    redirect_uri: redirectUri,
    response_mode: "query",
    scope: `${getAccessScope(configuration)} openid profile offline_access`,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
    state,
    prompt: "select_account",
  }).toString();
  if (claims) {
    url.searchParams.set("claims", claims);
  }
  return url;
}

/** Opens a URL in the operating system's default browser. */
async function openBrowser(url: string): Promise<void> {
  const command =
    process.platform === "darwin"
      ? "open"
      : process.platform === "win32"
        ? "cmd"
        : "xdg-open";
  const args = process.platform === "win32" ? ["/c", "start", "", url] : [url];
  await new Promise<void>((resolvePromise, rejectPromise) => {
    execFile(command, args, (error) => {
      if (error) {
        rejectPromise(error);
      } else {
        resolvePromise();
      }
    });
  });
}

/** Escapes text before rendering it in the localhost callback page. */
function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/** Writes a small browser response for the loopback OAuth callback. */
function writeCallbackResponse(
  response: ServerResponse,
  statusCode: number,
  title: string,
  message: string,
): void {
  response.writeHead(statusCode, { "Content-Type": "text/html; charset=utf-8" });
  response.end(
    `<!doctype html><html><body><h1>${escapeHtml(title)}</h1><p>${escapeHtml(message)}</p></body></html>`,
  );
}

/** Starts a one-shot loopback callback on an ephemeral localhost port. */
async function startOAuthCallback(
  expectedState: string,
  timeoutMs = MCP_TOOL_TIMEOUT_MS,
): Promise<OAuthCallback> {
  let settle: ((code: string) => void) | undefined;
  let reject: ((error: Error) => void) | undefined;
  const result = new Promise<string>((resolvePromise, rejectPromise) => {
    settle = resolvePromise;
    reject = rejectPromise;
  });
  const server = createServer((request, response) => {
    const url = new URL(request.url ?? "/", "http://localhost");
    if (request.method !== "GET" || url.pathname !== "/") {
      writeCallbackResponse(response, 404, "Not found", "This callback is no longer active.");
      return;
    }
    if (url.searchParams.get("state") !== expectedState) {
      writeCallbackResponse(response, 400, "State mismatch", "Return to Pi and try again.");
      reject?.(new Error("Microsoft OAuth callback state did not match."));
      server.close();
      return;
    }
    const oauthError = url.searchParams.get("error");
    if (oauthError) {
      const description = url.searchParams.get("error_description") ?? oauthError;
      writeCallbackResponse(response, 400, "Authorization failed", description);
      reject?.(new Error(`Microsoft authorization failed: ${description}`));
      server.close();
      return;
    }
    const code = url.searchParams.get("code");
    if (!code) {
      writeCallbackResponse(response, 400, "Authorization failed", "No code was returned.");
      reject?.(new Error("Microsoft did not return an authorization code."));
      server.close();
      return;
    }
    writeCallbackResponse(response, 200, "Microsoft Teams connected", "You can close this window.");
    settle?.(code);
    server.close();
  });

  await new Promise<void>((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(0, "127.0.0.1", resolvePromise);
  });
  const address = server.address();
  if (!address || typeof address === "string") {
    server.close();
    throw new Error("Could not determine the Microsoft OAuth callback port.");
  }
  const timeout = setTimeout(() => {
    reject?.(new Error("Microsoft authorization timed out after five minutes."));
    server.close();
  }, timeoutMs);
  void result.finally(() => clearTimeout(timeout)).catch(() => undefined);
  return {
    redirectUri: `http://localhost:${address.port}`,
    result,
    close: () => server.close(),
  };
}

/** Extracts a useful OAuth failure description without exposing tokens. */
function getOAuthError(payload: unknown): string {
  return isRecord(payload)
    ? getStringValue(payload, "error_description", "error") ?? "unknown OAuth error"
    : "unknown OAuth error";
}

/** Parses a successful Entra token response into persisted OAuth state. */
function parseTokenBundle(
  payload: unknown,
  previousRefreshToken?: string,
): TeamsTokenBundle {
  if (!isRecord(payload)) {
    throw new Error("Microsoft returned an invalid OAuth token response.");
  }
  const accessToken = getStringValue(payload, "access_token");
  if (!accessToken) {
    throw new Error(getOAuthError(payload));
  }
  const expiresIn =
    typeof payload.expires_in === "number" && payload.expires_in > 0
      ? payload.expires_in * 1000
      : DEFAULT_TOKEN_LIFETIME_MS;
  return {
    accessToken,
    refreshToken: getStringValue(payload, "refresh_token") ?? previousRefreshToken,
    expiresAt: Date.now() + expiresIn,
  };
}

/** Sends one form-encoded request to the Entra token endpoint. */
async function requestTokens(
  configuration: TeamsConfiguration,
  form: URLSearchParams,
  previousRefreshToken?: string,
): Promise<TeamsTokenBundle> {
  const response = await fetch(
    `https://login.microsoftonline.com/${configuration.tenantId}/oauth2/v2.0/token`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    },
  );
  const payload = (await response.json()) as unknown;
  if (!response.ok) {
    throw new Error(`Microsoft token request failed: ${getOAuthError(payload)}`);
  }
  return parseTokenBundle(payload, previousRefreshToken);
}

/** Exchanges an authorization code for per-user access and refresh tokens. */
async function exchangeCodeForTokens(
  configuration: TeamsConfiguration,
  code: string,
  redirectUri: string,
  codeVerifier: string,
): Promise<TeamsTokenBundle> {
  return await requestTokens(
    configuration,
    new URLSearchParams({
      client_id: configuration.clientId,
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri,
      code_verifier: codeVerifier,
      scope: `${getAccessScope(configuration)} openid profile offline_access`,
    }),
  );
}

/** Refreshes a Pi user's access token without involving MCP server state. */
async function refreshTokens(
  configuration: TeamsConfiguration,
): Promise<TeamsTokenBundle> {
  if (!configuration.refreshToken) {
    throw new Error("No Microsoft refresh token is stored. Run /mux connect teams.");
  }
  return await requestTokens(
    configuration,
    new URLSearchParams({
      client_id: configuration.clientId,
      grant_type: "refresh_token",
      refresh_token: configuration.refreshToken,
      scope: `${getAccessScope(configuration)} openid profile offline_access`,
    }),
    configuration.refreshToken,
  );
}

/** Runs Entra authorization-code PKCE and returns fresh user tokens. */
async function authenticateInteractively(
  configuration: TeamsConfiguration,
  notify: NotifyFn,
  claims?: string,
): Promise<TeamsTokenBundle> {
  const state = randomBytes(24).toString("base64url");
  const codeVerifier = randomBytes(48).toString("base64url");
  const callback = await startOAuthCallback(state);
  const authorizeUrl = buildAuthorizationUrl(
    configuration,
    callback.redirectUri,
    state,
    createCodeChallenge(codeVerifier),
    claims,
  );
  try {
    notify("Opening Microsoft sign-in in your browser.");
    await openBrowser(authorizeUrl.toString());
    const code = await callback.result;
    notify("Microsoft sign-in completed; exchanging the authorization code.");
    return await exchangeCodeForTokens(
      configuration,
      code,
      callback.redirectUri,
      codeVerifier,
    );
  } finally {
    callback.close();
  }
}

/** Extracts a claims value from an RFC 6750 challenge header. */
function extractClaimsChallenge(header: string | null): string | undefined {
  if (!header || !/error="insufficient_claims"/iu.test(header)) {
    return undefined;
  }
  const match = header.match(/(?:^|,\s*)claims="((?:\\.|[^"])*)"/iu);
  if (!match?.[1]) {
    return undefined;
  }
  try {
    return JSON.parse(`"${match[1]}"`) as string;
  } catch {
    return match[1];
  }
}

/** Parses one JSON-RPC response delivered as Server-Sent Events. */
async function parseSseResponse(
  response: Response,
  requestId: number,
): Promise<unknown> {
  const payloads: unknown[] = [];
  let currentData = "";
  for (const line of (await response.text()).split(/\r?\n/u)) {
    if (line.startsWith("data:")) {
      currentData += `${currentData ? "\n" : ""}${line.slice(5).trimStart()}`;
      continue;
    }
    if (line === "" && currentData) {
      try {
        const parsed = JSON.parse(currentData) as unknown;
        payloads.push(...(Array.isArray(parsed) ? parsed : [parsed]));
      } catch {
        // Ignore malformed events while looking for this request's response.
      }
      currentData = "";
    }
  }
  if (currentData) {
    try {
      const parsed = JSON.parse(currentData) as unknown;
      payloads.push(...(Array.isArray(parsed) ? parsed : [parsed]));
    } catch {
      // Ignore a malformed trailing event.
    }
  }
  const message =
    payloads.find((payload) => isRecord(payload) && payload.id === requestId) ??
    payloads.find(
      (payload) => isRecord(payload) && ("result" in payload || "error" in payload),
    );
  if (!message) {
    throw new Error("No JSON-RPC response was found in the Teams MCP event stream.");
  }
  return message;
}

/** Calls the remote stateless MCP endpoint for one authenticated Pi user. */
class TeamsMCPClient {
  readonly state: TeamsMCPState = {
    connected: false,
    authenticated: false,
    account: null,
    protocolVersion: MCP_PROTOCOL_VERSION,
    claimsChallenge: null,
  };

  private messageId = 0;
  private tools: MCPTool[] = [];
  private readonly mcpUrl: string;
  private readonly getAccessToken: () => Promise<string>;
  private readonly refreshAccessToken: () => Promise<string>;

  constructor(
    mcpUrl = DEFAULT_MCP_URL,
    getAccessToken: () => Promise<string> = async () => {
      throw new Error("Microsoft Teams is not authorized.");
    },
    refreshAccessToken: () => Promise<string> = async () => {
      throw new Error("Microsoft Teams is not authorized.");
    },
  ) {
    this.mcpUrl = mcpUrl;
    this.getAccessToken = getAccessToken;
    this.refreshAccessToken = refreshAccessToken;
  }

  /** Authenticates a request, discovers tools, and resolves the signed-in user. */
  async connect(): Promise<void> {
    try {
      const toolList = await this.sendRequest("tools/list", {});
      const payload = isRecord(toolList) ? toolList : {};
      const tools = Array.isArray(payload.tools) ? payload.tools : [];
      this.tools = tools.filter(isRecord).map((tool) => ({
        name: getStringValue(tool, "name") ?? "unknown_tool",
        description: getStringValue(tool, "description") ?? "",
        inputSchema: isRecord(tool.inputSchema) ? tool.inputSchema : {},
        outputSchema: isRecord(tool.outputSchema) ? tool.outputSchema : undefined,
      }));
      const authResult = await this.sendRequest("tools/call", {
        name: "auth_status",
        arguments: {},
      });
      const authStatusText = formatMcpResult(authResult);
      this.state.connected = true;
      this.state.authenticated = true;
      this.state.account = authStatusText.includes("Authenticated as")
        ? authStatusText.replace(/^.*Authenticated as\s+/u, "").trim()
        : null;
      this.state.claimsChallenge = null;
    } catch (error) {
      this.state.connected = false;
      this.state.authenticated = false;
      throw error;
    }
  }

  /** Calls a dynamically discovered Teams MCP tool. */
  async callTool(
    name: string,
    args: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<unknown> {
    if (!this.state.connected || !this.state.authenticated) {
      throw new Error("Teams MCP is not connected.");
    }
    return await this.sendRequest(
      "tools/call",
      { name, arguments: args },
      false,
      signal,
    );
  }

  /** Returns the current tool catalog. */
  getTools(): MCPTool[] {
    return [...this.tools];
  }

  /** Clears process-local connection state while retaining stored OAuth tokens. */
  async disconnect(): Promise<void> {
    this.tools = [];
    this.state.connected = false;
    this.state.authenticated = false;
    this.state.account = null;
  }

  /** Sends one JSON-RPC request and retries once after token refresh. */
  private async sendRequest(
    method: string,
    params: Record<string, unknown>,
    refreshed = false,
    signal?: AbortSignal,
  ): Promise<unknown> {
    const requestId = ++this.messageId;
    const timeoutSignal = AbortSignal.timeout(MCP_TOOL_TIMEOUT_MS);
    const requestSignal = signal
      ? AbortSignal.any([signal, timeoutSignal])
      : timeoutSignal;
    const response = await fetch(this.mcpUrl, {
      method: "POST",
      headers: {
        Accept: "application/json, text/event-stream",
        Authorization: `Bearer ${await this.getAccessToken()}`,
        "Content-Type": "application/json",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
      },
      body: JSON.stringify({ jsonrpc: "2.0", id: requestId, method, params }),
      signal: requestSignal,
    });
    if (response.status === 401) {
      const claims = extractClaimsChallenge(response.headers.get("www-authenticate"));
      await response.body?.cancel();
      if (claims) {
        this.state.claimsChallenge = claims;
        this.state.authenticated = false;
        throw new ClaimsChallengeError(claims);
      }
      if (!refreshed) {
        await this.refreshAccessToken();
        return await this.sendRequest(method, params, true, signal);
      }
    }
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Teams MCP HTTP ${response.status}: ${text}`);
    }
    const contentType = response.headers.get("content-type") ?? "";
    const message = contentType.includes("text/event-stream")
      ? await parseSseResponse(response, requestId)
      : ((await response.json()) as unknown);
    if (!isRecord(message)) {
      throw new Error("Teams MCP returned a non-JSON response.");
    }
    if (isRecord(message.error)) {
      throw new Error(
        getStringValue(message.error, "message") ?? "Teams MCP request failed.",
      );
    }
    return message.result;
  }
}

/** Returns a human-readable remote connection and authentication status. */
function getConnectionStatusText(client: TeamsMCPClient): string {
  const lines = [
    "Microsoft Teams MCP",
    `- Remote connection: ${client.state.connected ? "Ready" : "Not connected"}`,
    `- Authenticated: ${client.state.authenticated ? "Yes" : "No"}`,
    `- Account: ${client.state.account ?? "Unknown"}`,
    `- Protocol: ${client.state.protocolVersion}`,
    `- Tools discovered: ${client.getTools().length}`,
  ];
  if (client.state.claimsChallenge) {
    lines.push("Microsoft requires another interactive sign-in for Conditional Access.");
  } else if (!client.state.authenticated) {
    lines.push("Run /mux connect teams to authenticate and connect.");
  }
  return lines.join("\n");
}

/** Creates a Pi definition for one dynamically discovered Teams tool. */
function createRegisteredToolDefinition(
  client: TeamsMCPClient,
  tool: MCPTool,
) {
  return {
    name: tool.name,
    label: `Teams: ${tool.name.replace(/_/gu, " ")}`,
    description: tool.description || `Microsoft Teams MCP tool: ${tool.name}`,
    promptSnippet: tool.description || `Use the Teams MCP tool ${tool.name}.`,
    parameters: Type.Unsafe(tool.inputSchema),
    outputSchema: tool.outputSchema,
    /** Calls the corresponding tool on the remote Teams MCP server. */
    async execute(
      _toolCallId: string,
      params: unknown,
      signal?: AbortSignal,
      onUpdate?: (payload: {
        content: Array<{ type: "text"; text: string }>;
        details?: Record<string, unknown>;
      }) => void,
    ): Promise<ToolExecutionResult> {
      if (!client.state.authenticated) {
        return toolError(tool.name, "Teams MCP is unavailable. Run /mux connect teams.", {
          connected: false,
        });
      }
      onUpdate?.({
        content: [{ type: "text", text: `Running Teams ${tool.name}...` }],
        details: { tool: tool.name, phase: "running" },
      });
      try {
        const rawResult = await client.callTool(
          tool.name,
          isRecord(params) ? params : {},
          signal,
        );
        const text = formatMcpResult(rawResult);
        const result = toolResult(tool.name, text, { rawResult });
        if (isRecord(rawResult) && rawResult.isError === true) {
          result.isError = true;
        }
        return result;
      } catch (error) {
        const message = getErrorMessage(error);
        return toolError(tool.name, `Teams MCP error: ${message}`, { error: message });
      }
    },
  };
}

/** Registers newly discovered Teams tools with Pi exactly once. */
function registerDiscoveredTools(
  pi: ExtensionAPI,
  client: TeamsMCPClient,
): number {
  let registered = 0;
  const existing = new Set(pi.getAllTools().map((tool) => tool.name));
  for (const tool of client.getTools()) {
    if (!existing.has(tool.name)) {
      pi.registerTool(createRegisteredToolDefinition(client, tool));
      existing.add(tool.name);
      registered += 1;
    }
  }
  return registered;
}

/** Resolves Pi flags and environment variables for the hosted Teams MCP. */
function getRuntimeOverrides(pi: ExtensionAPI): TeamsRuntimeOverrides {
  /** Returns one non-empty Pi flag value. */
  const flagValue = (name: string): string | undefined => {
    const value = pi.getFlag(name);
    return isNonEmptyString(value) ? value.trim() : undefined;
  };
  return {
    clientId: flagValue("--teams-mcp-client-id") ?? process.env[TEAMS_MCP_CLIENT_ID_ENV],
    tenantId: flagValue("--teams-mcp-tenant-id") ?? process.env[TEAMS_MCP_TENANT_ID_ENV],
    mcpUrl: flagValue("--teams-mcp-url") ?? process.env[TEAMS_MCP_URL_ENV],
  };
}

/** Resolves the private Pi OAuth configuration path. */
function getConfigFilePath(pi: ExtensionAPI): string {
  const flag = pi.getFlag("--teams-mcp-config");
  return isNonEmptyString(flag)
    ? flag
    : process.env[TEAMS_MCP_CONFIG_FILE_ENV] || DEFAULT_CONFIG_FILE;
}

/** Registers the Teams provider, control command, and mux control tools. */
export default function teamsMcpExtension(pi: ExtensionAPI): void {
  pi.registerFlag("--teams-mcp-client-id", {
    description: "Optional override for the managed Teams MCP native client ID.",
    type: "string",
  });
  pi.registerFlag("--teams-mcp-tenant-id", {
    description: "Optional override for the managed Microsoft Entra tenant ID.",
    type: "string",
  });
  pi.registerFlag("--teams-mcp-url", {
    description: "Optional override for the hosted Teams MCP endpoint.",
    type: "string",
  });
  pi.registerFlag("--teams-mcp-config", {
    description: "Path to Pi's private Teams MCP OAuth configuration.",
    type: "string",
  });

  const runtime = getRuntimeOverrides(pi);
  const storage = new TeamsConfigStorage(getConfigFilePath(pi));
  /** Returns the latest effective Teams configuration. */
  const getConfiguration = (): TeamsConfiguration =>
    resolveTeamsConfiguration(runtime, storage.load());
  /** Persists a refreshed token bundle without changing endpoint settings. */
  const saveTokens = (bundle: TeamsTokenBundle): void => {
    storage.save({
      ...storage.load(),
      accessToken: bundle.accessToken,
      refreshToken: bundle.refreshToken,
      expiresAt: bundle.expiresAt,
    });
  };
  /** Returns a valid user token, refreshing it before expiry when possible. */
  const getAccessToken = async (): Promise<string> => {
    const configuration = getConfiguration();
    if (
      configuration.accessToken &&
      typeof configuration.expiresAt === "number" &&
      configuration.expiresAt > Date.now() + TOKEN_REFRESH_WINDOW_MS
    ) {
      return configuration.accessToken;
    }
    const bundle = await refreshTokens(configuration);
    saveTokens(bundle);
    return bundle.accessToken;
  };
  /** Forces an Entra refresh after a remote bearer challenge. */
  const refreshAccessToken = async (): Promise<string> => {
    const bundle = await refreshTokens(getConfiguration());
    saveTokens(bundle);
    return bundle.accessToken;
  };
  const client = new TeamsMCPClient(
    getConfiguration().mcpUrl,
    getAccessToken,
    refreshAccessToken,
  );

  pi.on("session_start", async () => {
    try {
      await client.connect();
      registerDiscoveredTools(pi, client);
    } catch {
      await client.disconnect();
    }
  });

  pi.registerCommand("teams-mcp", {
    description: "Authenticate, connect, or disconnect Microsoft Teams MCP",
    /** Runs the human-facing per-user Teams authorization flow. */
    async handler(_args, ctx: ExtensionContext) {
      if (client.state.authenticated) {
        const choice = await ctx.ui.select(getConnectionStatusText(client), [
          "Disconnect",
          "Cancel",
        ]);
        if (choice === "Disconnect") {
          await client.disconnect();
          ctx.ui.notify("Disconnected from Teams MCP. Your OAuth grant was preserved.", "info");
        }
        return;
      }
      const notify: NotifyFn = (message, level = "info") => {
        ctx.ui.notify(message, level);
      };
      try {
        const bundle = await authenticateInteractively(
          getConfiguration(),
          notify,
          client.state.claimsChallenge ?? undefined,
        );
        saveTokens(bundle);
        await client.connect();
        const registered = registerDiscoveredTools(pi, client);
        ctx.ui.notify(
          `Connected to Microsoft Teams (${client.getTools().length} tools, ${registered} newly registered).`,
          "info",
        );
      } catch (error) {
        ctx.ui.notify(`Teams MCP connection failed: ${getErrorMessage(error)}`, "error");
      }
    },
  });

  pi.registerTool({
    name: "teams_mcp_connect",
    label: "Teams MCP Connect",
    description: "Connect to the hosted Teams MCP using Pi's saved user grant",
    promptSnippet: "Connect to Teams MCP when Teams tools are needed but not authorized.",
    parameters: Type.Object({}),
    /** Reuses an existing per-user OAuth grant without opening browser UI. */
    async execute(): Promise<ToolExecutionResult> {
      try {
        await client.connect();
        registerDiscoveredTools(pi, client);
      } catch (error) {
        const message = getErrorMessage(error);
        return toolError(
          "teams_mcp_connect",
          `Connection failed: ${message} Run /mux connect teams for interactive sign-in.`,
          { connected: false, requiresInteractiveSetup: true, error: message },
        );
      }
      return toolResult(
        "teams_mcp_connect",
        `Connected to Microsoft Teams with ${client.getTools().length} tools.`,
        {
          connected: true,
          account: client.state.account,
          protocolVersion: client.state.protocolVersion,
          toolCount: client.getTools().length,
        },
      );
    },
  });

  pi.registerTool({
    name: "teams_mcp_disconnect",
    label: "Teams MCP Disconnect",
    description: "Disconnect Pi from Teams MCP without deleting its OAuth grant",
    parameters: Type.Object({}),
    /** Clears only process-local connection state. */
    async execute(): Promise<ToolExecutionResult> {
      await client.disconnect();
      return toolResult(
        "teams_mcp_disconnect",
        "Disconnected Pi from Teams MCP. Your OAuth grant was preserved.",
        { connected: false },
      );
    },
  });

  pi.registerTool({
    name: "teams_mcp_status",
    label: "Teams MCP Status",
    description: "Check Pi's hosted Teams MCP authentication state",
    parameters: Type.Object({}),
    /** Reports whether the remote MCP is ready for this user. */
    async execute(): Promise<ToolExecutionResult> {
      return toolResult("teams_mcp_status", getConnectionStatusText(client), {
        connected: client.state.connected && client.state.authenticated,
        authenticated: client.state.authenticated,
        account: client.state.account,
        protocolVersion: client.state.protocolVersion,
        toolCount: client.getTools().length,
      });
    },
  });
}

export {
  buildAuthorizationUrl,
  ClaimsChallengeError,
  createCodeChallenge,
  DEFAULT_CLIENT_ID,
  DEFAULT_CONFIG_FILE,
  DEFAULT_MCP_URL,
  DEFAULT_TENANT_ID,
  extractClaimsChallenge,
  getConnectionStatusText,
  parseTokenBundle,
  refreshTokens,
  resolveTeamsConfiguration,
  TeamsConfigStorage,
  TeamsMCPClient,
};
