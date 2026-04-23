/**
 * Slack MCP Extension for pi
 *
 * Connects to Slack's official MCP server at https://mcp.slack.com/mcp using
 * Slack OAuth with PKCE. After connection, the extension discovers the full
 * Slack MCP tool surface and registers the server tools dynamically.
 */

import { exec } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";

// =============================================================================
// Constants
// =============================================================================

const SLACK_MCP_URL = "https://mcp.slack.com/mcp";
const SLACK_OAUTH_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize";
const SLACK_OAUTH_TOKEN_URL = "https://slack.com/api/oauth.v2.access";
const SLACK_AUTH_TEST_URL = "https://slack.com/api/auth.test";
const DEFAULT_REDIRECT_URI = "http://127.0.0.1:8315/oauth/callback";
const DEFAULT_AUTH_FILE = "~/.pi/agent/slack-mcp-auth.json";
const DEFAULT_TIMEOUT_MS = 300_000;
const MCP_PROTOCOL_VERSIONS = ["2025-03-26", "2024-11-05"] as const;
const SLACK_MCP_AUTH_FILE_ENV = "SLACK_MCP_AUTH_FILE";
const SLACK_MCP_CLIENT_ID_ENV = "SLACK_MCP_CLIENT_ID";
const SLACK_MCP_CLIENT_SECRET_ENV = "SLACK_MCP_CLIENT_SECRET";
const SLACK_MCP_REDIRECT_URI_ENV = "SLACK_MCP_REDIRECT_URI";

const SLACK_MCP_USER_SCOPES = [
  "search:read.public",
  "search:read.private",
  "search:read.mpim",
  "search:read.im",
  "search:read.files",
  "search:read.users",
  "chat:write",
  "channels:history",
  "groups:history",
  "mpim:history",
  "im:history",
  "canvases:read",
  "canvases:write",
  "users:read",
  "users:read.email",
] as const;

const numberFormatter = new Intl.NumberFormat("en-US");

// =============================================================================
// Types
// =============================================================================

type NotifyLevel = "info" | "warning" | "error";
type NotifyFn = (message: string, type?: NotifyLevel) => void;

type ToolExecutionResult = {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
  details: Record<string, unknown>;
};

interface MCPTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

interface MCPState {
  connected: boolean;
  authenticated: boolean;
  sessionId: string | null;
  mcpUrl: string;
  serverName: string | null;
  serverVersion: string | null;
  protocolVersion: string | null;
  teamName: string | null;
  teamId: string | null;
  userName: string | null;
  userId: string | null;
}

interface RuntimeOverrides {
  clientId?: string;
  clientSecret?: string;
  redirectUri?: string;
}

interface StoredConfig {
  clientId?: string;
  clientSecret?: string;
  redirectUri?: string;
  accessToken?: string;
  refreshToken?: string;
  expiresAt?: number;
  teamName?: string;
  teamId?: string;
  userName?: string;
  userId?: string;
}

interface OAuthCallbackResult {
  code?: string;
  error?: string;
  errorDescription?: string;
}

interface OAuthCallbackServerResult {
  result: Promise<OAuthCallbackResult>;
  close: () => void;
}

interface SlackTokenBundle {
  accessToken: string;
  refreshToken?: string;
  expiresAt?: number;
  teamName?: string;
  teamId?: string;
  userId?: string;
}

interface SlackIdentity {
  teamName?: string;
  teamId?: string;
  userName?: string;
  userId?: string;
}

interface RenderTheme {
  fg(token: string, text: string): string;
  bold(text: string): string;
}

interface ToolRenderOptions {
  expanded: boolean;
  isPartial: boolean;
}

interface ToolRenderContext {
  args?: unknown;
  isError?: boolean;
}

// =============================================================================
// General Utilities
// =============================================================================

function getHomeDir(): string {
  return process.env.HOME || homedir();
}

function resolveOptionalPath(path: string): string {
  const trimmed = path.trim();
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isNumericString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value));
}

function getStringValue(input: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = input[key];
    if (isNonEmptyString(value)) {
      return value.trim();
    }
  }
  return undefined;
}

function getNumberValue(input: Record<string, unknown>, ...keys: string[]): number | undefined {
  for (const key of keys) {
    const value = input[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (isNumericString(value)) {
      return Number(value);
    }
  }
  return undefined;
}

function getArrayLength(input: Record<string, unknown>, ...keys: string[]): number | undefined {
  for (const key of keys) {
    const value = input[key];
    if (Array.isArray(value)) {
      return value.length;
    }
  }
  return undefined;
}

function coercePropertyMap(properties: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(properties).map(([propName, propValue]) => [
      propName,
      isNumericString(propValue) ? Number(propValue) : coerceNumericProperties(propValue),
    ]),
  );
}

function coerceNumericProperties(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) return obj.map(coerceNumericProperties);
  if (!isRecord(obj)) return obj;

  return Object.fromEntries(
    Object.entries(obj).map(([key, value]) => [
      key,
      key === "properties" && isRecord(value) ? coercePropertyMap(value) : coerceNumericProperties(value),
    ]),
  );
}

function compactWhitespace(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function truncateDisplayText(text: string, maxLength = 88): string {
  const compact = compactWhitespace(text);
  return compact.length > maxLength ? `${compact.slice(0, maxLength - 1)}…` : compact;
}

function countOutputLines(text: string): number {
  if (!text.trim()) return 0;
  return text.split("\n").filter((line) => line.trim().length > 0).length;
}

function formatOutputCount(value: number): string {
  return numberFormatter.format(value);
}

function buildOutputStatsLabel(lineCount: number, characterCount: number): string {
  const parts: string[] = [];
  if (lineCount > 0) {
    parts.push(`${lineCount} line${lineCount === 1 ? "" : "s"}`);
  }
  if (characterCount > 0) {
    parts.push(`${formatOutputCount(characterCount)} char${characterCount === 1 ? "" : "s"}`);
  }
  return parts.join(", ");
}

function formatOutputStats(lineCount: number, characterCount: number): string {
  const label = buildOutputStatsLabel(lineCount, characterCount);
  return label ? ` (${label})` : "";
}

function getTextContent(content: Array<{ type: string; text?: string }> | undefined): string {
  return (content ?? [])
    .map((item) => (item.type === "text" ? item.text ?? "" : ""))
    .filter((item) => item.length > 0)
    .join("\n")
    .trim();
}

function buildPreviewLines(text: string, maxLines = 8): string[] {
  const lines = text
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.trim().length > 0);

  return lines.slice(0, maxLines).map((line) => truncateDisplayText(line, 120));
}

function humanizeWords(value: string): string {
  return value.replace(/[_-]+/g, " ").trim();
}

function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function normalizeToolPromptSnippet(description: string, toolName: string): string {
  if (isNonEmptyString(description)) {
    return truncateDisplayText(description, 120);
  }
  return `Use the Slack MCP tool ${toolName}.`;
}

function createUiNotifier(ctx: ExtensionContext): NotifyFn {
  return (message, type = "info") => {
    ctx.ui.notify(message, type);
  };
}

function openBrowser(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const platform = process.platform;
    const command = platform === "darwin" ? "open" : platform === "win32" ? "start" : "xdg-open";
    exec(`${command} "${url}"`, (error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
}

function createPkceChallenge(): { codeVerifier: string; codeChallenge: string } {
  const codeVerifier = randomBytes(32).toString("base64url");
  const codeChallenge = createHash("sha256").update(codeVerifier).digest("base64url");
  return { codeVerifier, codeChallenge };
}

function buildAuthorizationUrl(clientId: string, redirectUri: string, codeChallenge: string, state: string): string {
  const authUrl = new URL(SLACK_OAUTH_AUTHORIZE_URL);
  authUrl.searchParams.set("client_id", clientId);
  authUrl.searchParams.set("scope", "");
  authUrl.searchParams.set("user_scope", SLACK_MCP_USER_SCOPES.join(","));
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("code_challenge", codeChallenge);
  authUrl.searchParams.set("code_challenge_method", "S256");
  return authUrl.toString();
}

function normalizeRedirectUri(redirectUri: string): URL {
  const parsed = new URL(redirectUri);
  if (parsed.protocol !== "http:") {
    throw new Error("Slack MCP redirect URI must use http:// and point to localhost or 127.0.0.1.");
  }
  if (!(parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost")) {
    throw new Error("Slack MCP redirect URI must use localhost or 127.0.0.1.");
  }
  if (!parsed.port) {
    throw new Error("Slack MCP redirect URI must include an explicit port.");
  }
  return parsed;
}

function buildHtmlResponse(statusCode: number, html: string): { statusCode: number; body: string } {
  return { statusCode, body: html };
}

function resolveCallbackResult(
  params: URLSearchParams,
  expectedState: string,
): {
  response: { statusCode: number; body: string };
  result: OAuthCallbackResult;
} {
  if (params.get("state") !== expectedState) {
    return {
      response: buildHtmlResponse(
        400,
        "<html><body><h1>State mismatch</h1><p>Please try again.</p></body></html>",
      ),
      result: { error: "State mismatch" },
    };
  }

  const error = params.get("error");
  if (error) {
    return {
      response: buildHtmlResponse(
        400,
        `<html><body><h1>Authorization failed</h1><p>Error: ${error}</p><p>${params.get("error_description") ?? ""}</p></body></html>`,
      ),
      result: {
        error,
        errorDescription: params.get("error_description") ?? undefined,
      },
    };
  }

  const code = params.get("code");
  if (!code) {
    return {
      response: buildHtmlResponse(
        400,
        "<html><body><h1>Authorization failed</h1><p>No code in callback.</p></body></html>",
      ),
      result: { error: "No authorization code received" },
    };
  }

  return {
    response: buildHtmlResponse(
      200,
      "<html><body><h1>Authorized!</h1><p>You can close this window.</p><script>window.close();</script></body></html>",
    ),
    result: { code },
  };
}

async function startOAuthCallbackServer(
  redirectUri: string,
  state: string,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<OAuthCallbackServerResult> {
  const parsed = normalizeRedirectUri(redirectUri);
  const callbackPath = parsed.pathname || "/";

  let closed = false;
  let timeout: NodeJS.Timeout | undefined;

  const server = createServer();
  const result = new Promise<OAuthCallbackResult>((resolve, reject) => {
    const closeServer = () => {
      if (closed) return;
      closed = true;
      if (timeout) clearTimeout(timeout);
      server.close();
    };

    timeout = setTimeout(() => {
      closeServer();
      reject(new Error("Slack OAuth callback timed out after 5 minutes."));
    }, timeoutMs);

    server.on("request", (request, response) => {
      const requestUrl = new URL(request.url ?? "/", parsed.origin);
      if (requestUrl.pathname !== callbackPath) {
        response.writeHead(404, { "Content-Type": "text/html" });
        response.end("<html><body><h1>Not found</h1></body></html>");
        return;
      }

      const { response: htmlResponse, result } = resolveCallbackResult(requestUrl.searchParams, state);
      response.writeHead(htmlResponse.statusCode, {
        "Content-Type": "text/html",
        "Content-Length": Buffer.byteLength(htmlResponse.body),
      });
      response.end(htmlResponse.body);
      closeServer();
      resolve(result);
    });

    server.on("error", (error) => {
      closeServer();
      reject(error);
    });
  });

  await new Promise<void>((resolve, reject) => {
    const onError = (error: Error) => {
      server.off("error", onError);
      reject(error);
    };

    server.once("error", onError);
    server.listen(Number(parsed.port), parsed.hostname, () => {
      server.off("error", onError);
      resolve();
    });
  });

  return {
    result,
    close() {
      if (closed) return;
      closed = true;
      if (timeout) clearTimeout(timeout);
      server.close();
    },
  };
}

// =============================================================================
// Stored Config
// =============================================================================

function getDefaultAuthFilePath(): string {
  const configuredPath = process.env[SLACK_MCP_AUTH_FILE_ENV];
  if (isNonEmptyString(configuredPath)) {
    return resolveOptionalPath(configuredPath);
  }
  return resolveOptionalPath(DEFAULT_AUTH_FILE);
}

class FileConfigStorage {
  private getPath(): string {
    return getDefaultAuthFilePath();
  }

  async load(): Promise<StoredConfig | null> {
    const path = this.getPath();
    if (!existsSync(path)) return null;
    try {
      return JSON.parse(readFileSync(path, "utf-8")) as StoredConfig;
    } catch {
      return null;
    }
  }

  async save(config: StoredConfig): Promise<void> {
    const path = this.getPath();
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, JSON.stringify(config, null, 2), "utf-8");
  }

  async clear(): Promise<void> {
    const path = this.getPath();
    if (!existsSync(path)) return;
    const { unlinkSync } = await import("node:fs");
    unlinkSync(path);
  }
}

function mergeRuntimeOverrides(config: StoredConfig | null, overrides: RuntimeOverrides): StoredConfig {
  return {
    ...config,
    ...(isNonEmptyString(overrides.clientId) ? { clientId: overrides.clientId } : {}),
    ...(typeof overrides.clientSecret === "string" ? { clientSecret: overrides.clientSecret } : {}),
    ...(isNonEmptyString(overrides.redirectUri) ? { redirectUri: overrides.redirectUri } : {}),
  };
}

function getRuntimeOverrides(pi: ExtensionAPI): RuntimeOverrides {
  const clientIdFlag = pi.getFlag("--slack-mcp-client-id");
  const clientSecretFlag = pi.getFlag("--slack-mcp-client-secret");
  const redirectUriFlag = pi.getFlag("--slack-mcp-redirect-uri");
  const authFileFlag = pi.getFlag("--slack-mcp-auth-file");

  if (isNonEmptyString(authFileFlag)) {
    process.env[SLACK_MCP_AUTH_FILE_ENV] = authFileFlag;
  }

  return {
    clientId: isNonEmptyString(clientIdFlag) ? clientIdFlag.trim() : process.env[SLACK_MCP_CLIENT_ID_ENV],
    clientSecret:
      typeof clientSecretFlag === "string" ? clientSecretFlag : process.env[SLACK_MCP_CLIENT_SECRET_ENV],
    redirectUri:
      isNonEmptyString(redirectUriFlag) ? redirectUriFlag.trim() : process.env[SLACK_MCP_REDIRECT_URI_ENV],
  };
}

function buildDisconnectedMessage(config: StoredConfig): string {
  const redirectUri = config.redirectUri ?? DEFAULT_REDIRECT_URI;
  const clientConfigured = isNonEmptyString(config.clientId) ? "Yes" : "No";
  return [
    "Slack MCP Status:",
    "- Connected: No",
    `- Client ID configured: ${clientConfigured}`,
    `- Redirect URI: ${redirectUri}`,
    "",
    isNonEmptyString(config.clientId)
      ? "Run /slack-mcp or use slack_mcp_connect to authorize."
      : "Run /slack-mcp to save your Slack app client ID and authorize.",
  ].join("\n");
}

// =============================================================================
// Slack OAuth
// =============================================================================

function parseSlackTokenBundle(data: unknown): SlackTokenBundle {
  if (!isRecord(data)) {
    throw new Error("Slack OAuth response was not an object.");
  }

  const authedUser = isRecord(data.authed_user) ? data.authed_user : undefined;
  const accessToken = getStringValue(authedUser ?? {}, "access_token") ?? getStringValue(data, "access_token");
  const refreshToken = getStringValue(authedUser ?? {}, "refresh_token") ?? getStringValue(data, "refresh_token");
  const expiresIn = getNumberValue(authedUser ?? {}, "expires_in") ?? getNumberValue(data, "expires_in");
  const teamRecord = isRecord(data.team) ? data.team : undefined;

  if (!accessToken) {
    const error = getStringValue(data, "error") ?? "No access token returned from Slack.";
    throw new Error(error);
  }

  return {
    accessToken,
    refreshToken,
    expiresAt: typeof expiresIn === "number" ? Date.now() + expiresIn * 1000 - 60_000 : undefined,
    teamName: teamRecord ? getStringValue(teamRecord, "name") : undefined,
    teamId: teamRecord ? getStringValue(teamRecord, "id") : undefined,
    userId: authedUser ? getStringValue(authedUser, "id") : undefined,
  };
}

async function exchangeCodeForTokens(
  clientId: string,
  clientSecret: string | undefined,
  redirectUri: string,
  code: string,
  codeVerifier: string,
): Promise<SlackTokenBundle> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: clientId,
    redirect_uri: redirectUri,
    code,
    code_verifier: codeVerifier,
  });

  if (typeof clientSecret === "string" && clientSecret.length > 0) {
    body.set("client_secret", clientSecret);
  }

  const response = await fetch(SLACK_OAUTH_TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  const payload = (await response.json()) as unknown;
  if (!response.ok || (isRecord(payload) && payload.ok === false)) {
    const message = isRecord(payload) ? getStringValue(payload, "error") ?? response.statusText : response.statusText;
    throw new Error(`Slack token exchange failed: ${message}`);
  }

  return parseSlackTokenBundle(payload);
}

async function refreshTokens(config: StoredConfig): Promise<SlackTokenBundle> {
  if (!isNonEmptyString(config.clientId)) {
    throw new Error("Slack client ID is required to refresh the access token.");
  }
  if (!isNonEmptyString(config.refreshToken)) {
    throw new Error("No Slack refresh token is stored. Reauthorize with /slack-mcp.");
  }

  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: config.clientId,
    refresh_token: config.refreshToken,
  });

  if (isNonEmptyString(config.clientSecret)) {
    body.set("client_secret", config.clientSecret);
  }

  const response = await fetch(SLACK_OAUTH_TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  const payload = (await response.json()) as unknown;
  if (!response.ok || (isRecord(payload) && payload.ok === false)) {
    const message = isRecord(payload) ? getStringValue(payload, "error") ?? response.statusText : response.statusText;
    throw new Error(`Slack token refresh failed: ${message}`);
  }

  return parseSlackTokenBundle(payload);
}

async function fetchSlackIdentity(accessToken: string): Promise<SlackIdentity> {
  const response = await fetch(SLACK_AUTH_TEST_URL, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  const payload = (await response.json()) as unknown;
  if (!response.ok || !isRecord(payload) || payload.ok !== true) {
    return {};
  }

  return {
    teamName: getStringValue(payload, "team"),
    teamId: getStringValue(payload, "team_id"),
    userName: getStringValue(payload, "user"),
    userId: getStringValue(payload, "user_id"),
  };
}

function buildMissingClientIdError(): string {
  return "Slack app client ID is not configured. Set SLACK_MCP_CLIENT_ID or run /slack-mcp to save it.";
}

// =============================================================================
// MCP Client
// =============================================================================

class SlackMCPClient {
  state: MCPState = {
    connected: false,
    authenticated: false,
    sessionId: null,
    mcpUrl: SLACK_MCP_URL,
    serverName: null,
    serverVersion: null,
    protocolVersion: null,
    teamName: null,
    teamId: null,
    userName: null,
    userId: null,
  };

  private messageId = 0;
  private sessionId: string | null = null;
  private tools: MCPTool[] = [];
  private readonly getAccessToken: () => Promise<string>;
  private readonly refreshAccessToken: () => Promise<string>;

  constructor(getAccessToken: () => Promise<string>, refreshAccessToken: () => Promise<string>) {
    this.getAccessToken = getAccessToken;
    this.refreshAccessToken = refreshAccessToken;
  }

  async connect(): Promise<void> {
    this.state.authenticated = true;

    let initializeResult: Record<string, unknown> | null = null;
    let lastError: Error | undefined;

    for (const protocolVersion of MCP_PROTOCOL_VERSIONS) {
      try {
        initializeResult = (await this.sendRequest(
          "initialize",
          {
            protocolVersion,
            capabilities: {},
            clientInfo: { name: "pi-slack-mcp", version: "1.0.0" },
          },
          protocolVersion,
        )) as Record<string, unknown>;
        this.state.protocolVersion = protocolVersion;
        break;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
      }
    }

    if (!initializeResult || !this.state.protocolVersion) {
      throw lastError ?? new Error("Slack MCP initialization failed.");
    }

    if (!this.sessionId) {
      this.sessionId = randomBytes(16).toString("hex");
      this.state.sessionId = this.sessionId;
    }

    this.state.serverName = isRecord(initializeResult.serverInfo)
      ? getStringValue(initializeResult.serverInfo, "name") ?? null
      : null;
    this.state.serverVersion = isRecord(initializeResult.serverInfo)
      ? getStringValue(initializeResult.serverInfo, "version") ?? null
      : null;

    await this.sendNotification("notifications/initialized", {});
    await this.discoverTools();

    this.state.connected = true;
  }

  async disconnect(): Promise<void> {
    if (this.sessionId) {
      try {
        await fetch(this.state.mcpUrl, {
          method: "DELETE",
          headers: await this.getHeaders(this.state.protocolVersion ?? undefined),
        });
      } catch {
        // Ignore disconnect errors.
      }
    }

    this.tools = [];
    this.sessionId = null;
    this.state = {
      ...this.state,
      connected: false,
      authenticated: false,
      sessionId: null,
      serverName: null,
      serverVersion: null,
      protocolVersion: null,
    };
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    const result = await this.sendRequest("tools/call", {
      name,
      arguments: coerceNumericProperties(args),
    });

    return normalizeMcpToolResult(result);
  }

  getTools(): MCPTool[] {
    return this.tools;
  }

  setIdentity(identity: SlackIdentity): void {
    this.state.teamName = identity.teamName ?? this.state.teamName;
    this.state.teamId = identity.teamId ?? this.state.teamId;
    this.state.userName = identity.userName ?? this.state.userName;
    this.state.userId = identity.userId ?? this.state.userId;
  }

  private async discoverTools(): Promise<void> {
    const result = await this.sendRequest("tools/list", {});
    const payload = isRecord(result) ? result : {};
    const tools = Array.isArray(payload.tools) ? payload.tools : [];

    this.tools = tools
      .filter((tool): tool is Record<string, unknown> => isRecord(tool))
      .map((tool) => ({
        name: getStringValue(tool, "name") ?? "unknown_tool",
        description: getStringValue(tool, "description") ?? "",
        inputSchema: isRecord(tool.inputSchema) ? tool.inputSchema : {},
      }));
  }

  private async sendNotification(method: string, params: Record<string, unknown>): Promise<void> {
    const response = await fetch(this.state.mcpUrl, {
      method: "POST",
      headers: await this.getHeaders(this.state.protocolVersion ?? undefined),
      body: JSON.stringify({ jsonrpc: "2.0", method, params }),
    });

    if (response.status === 401) {
      await response.body?.cancel();
      await this.refreshAccessToken();
      await fetch(this.state.mcpUrl, {
        method: "POST",
        headers: await this.getHeaders(this.state.protocolVersion ?? undefined),
        body: JSON.stringify({ jsonrpc: "2.0", method, params }),
      });
      return;
    }

    await response.body?.cancel();
  }

  private async sendRequest(
    method: string,
    params: Record<string, unknown>,
    protocolVersion?: string,
  ): Promise<unknown> {
    const requestId = ++this.messageId;
    const response = await fetch(this.state.mcpUrl, {
      method: "POST",
      headers: await this.getHeaders(protocolVersion),
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: requestId,
        method,
        params,
      }),
    });

    if (response.status === 401) {
      await response.body?.cancel();
      await this.refreshAccessToken();
      return this.sendRequest(method, params, protocolVersion);
    }

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    const sessionHeader = response.headers.get("mcp-session-id");
    if (sessionHeader) {
      this.sessionId = sessionHeader;
      this.state.sessionId = sessionHeader;
    }

    const contentType = response.headers.get("content-type") ?? "";
    const json = contentType.includes("text/event-stream")
      ? await parseSseResponse(response, requestId)
      : ((await response.json()) as unknown);

    if (!isRecord(json)) {
      throw new Error("Slack MCP returned a non-JSON response.");
    }
    if (isRecord(json.error)) {
      throw new Error(getStringValue(json.error, "message") ?? "Slack MCP request failed.");
    }
    return json.result;
  }

  private async getHeaders(protocolVersion?: string): Promise<Headers> {
    const headers = new Headers({
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      Authorization: `Bearer ${await this.getAccessToken()}`,
    });

    if (this.sessionId) {
      headers.set("mcp-session-id", this.sessionId);
    }
    if (protocolVersion) {
      headers.set("mcp-protocol-version", protocolVersion);
    }
    return headers;
  }
}

function normalizeMcpToolResult(result: unknown): string {
  if (!isRecord(result)) {
    return safeJsonStringify(result);
  }

  const content = Array.isArray(result.content) ? result.content : [];
  if (content.length > 0) {
    const joined = content
      .map((item) => {
        if (!isRecord(item)) return safeJsonStringify(item);
        if (item.type === "text") {
          return typeof item.text === "string" ? item.text : "";
        }
        return safeJsonStringify(item);
      })
      .filter((item) => item.length > 0)
      .join("\n")
      .trim();

    if (joined.length > 0) {
      return joined;
    }
  }

  if ("structuredContent" in result) {
    return safeJsonStringify(result.structuredContent);
  }

  return safeJsonStringify(result);
}

async function parseSseResponse(response: Response, requestId: number): Promise<unknown> {
  const text = await response.text();
  const messages: unknown[] = [];
  let currentData = "";

  for (const rawLine of text.split(/\r?\n/)) {
    if (rawLine.startsWith("data:")) {
      currentData += `${currentData.length > 0 ? "\n" : ""}${rawLine.slice(5).trimStart()}`;
      continue;
    }

    if (rawLine === "") {
      if (currentData.length > 0) {
        try {
          messages.push(JSON.parse(currentData));
        } catch {
          // Ignore malformed SSE payloads.
        }
        currentData = "";
      }
    }
  }

  if (currentData.length > 0) {
    try {
      messages.push(JSON.parse(currentData));
    } catch {
      // Ignore malformed trailing payloads.
    }
  }

  const flattened = messages.flatMap((message) => (Array.isArray(message) ? message : [message]));
  const matching = flattened.find((message) => isRecord(message) && message.id === requestId);
  if (matching) return matching;

  const fallback = flattened.find((message) => isRecord(message) && ("result" in message || "error" in message));
  if (fallback) return fallback;

  throw new Error("No JSON-RPC response found in Slack MCP SSE stream.");
}

// =============================================================================
// TUI Rendering
// =============================================================================

function buildSlackCallSummary(toolName: string, args: unknown): { primary?: string; meta: string[] } {
  const input = isRecord(args) ? args : {};
  const meta: string[] = [];

  const query = getStringValue(input, "query", "search_query");
  const channel = getStringValue(input, "channel", "channel_id", "conversation_id", "channel_name");
  const thread = getStringValue(input, "thread_ts", "message_ts", "ts");
  const canvas = getStringValue(input, "canvas_id", "id");
  const user = getStringValue(input, "user_id", "email", "name");
  const message = getStringValue(input, "message", "text", "content");
  const limit = getNumberValue(input, "limit", "count", "page_size");
  const itemCount = getArrayLength(input, "channels", "channel_ids", "user_ids");

  if (channel) meta.push(`channel=${channel}`);
  if (thread) meta.push(`thread=${thread}`);
  if (typeof limit === "number") meta.push(`limit=${limit}`);
  if (typeof itemCount === "number") meta.push(`items=${itemCount}`);

  const lower = toolName.toLowerCase();
  if (lower.includes("search")) {
    return { primary: query ?? channel ?? user ?? canvas, meta };
  }
  if (lower.includes("send") || lower.includes("post") || lower.includes("draft")) {
    if (message) meta.push(`text=${truncateDisplayText(message, 48)}`);
    return { primary: channel ?? user ?? canvas ?? query, meta };
  }
  if (lower.includes("thread")) {
    return { primary: channel ?? thread ?? query, meta };
  }
  if (lower.includes("canvas")) {
    return { primary: canvas ?? channel ?? query, meta };
  }
  if (lower.includes("user")) {
    return { primary: user ?? query, meta };
  }
  if (lower.includes("channel")) {
    return { primary: channel ?? query, meta };
  }

  const primary =
    query ?? channel ?? thread ?? canvas ?? user ?? message ?? getStringValue(input, "url", "name", "title");
  return { primary: primary ? truncateDisplayText(primary, 64) : undefined, meta };
}

function getSlackPendingLabel(toolName: string): string {
  const lower = toolName.toLowerCase();
  if (toolName === "slack_mcp_connect") return "Connecting to Slack MCP...";
  if (toolName === "slack_mcp_disconnect") return "Disconnecting from Slack MCP...";
  if (toolName === "slack_mcp_status") return "Checking Slack MCP status...";
  if (lower.includes("search")) return "Searching Slack...";
  if (lower.includes("send") || lower.includes("post") || lower.includes("draft")) {
    return "Working on a Slack message...";
  }
  if (lower.includes("canvas")) return "Working with a Slack canvas...";
  if (lower.includes("thread")) return "Reading a Slack thread...";
  if (lower.includes("channel")) return "Reading Slack channels...";
  if (lower.includes("user")) return "Looking up Slack users...";
  return "Working with Slack...";
}

function getSlackSuccessLabel(toolName: string, details: Record<string, unknown>): string {
  if (toolName === "slack_mcp_connect") {
    const toolCount = typeof details.toolCount === "number" ? details.toolCount : undefined;
    return typeof toolCount === "number"
      ? `Connected (${toolCount} tool${toolCount === 1 ? "" : "s"})`
      : "Connected";
  }

  if (toolName === "slack_mcp_disconnect") return "Disconnected";
  if (toolName === "slack_mcp_status") {
    return details.connected === true ? "Connected" : "Not connected";
  }

  const lower = toolName.toLowerCase();
  if (lower.includes("search")) return "Search complete";
  if (lower.includes("send") || lower.includes("post")) return "Message sent";
  if (lower.includes("draft")) return "Draft prepared";
  if (lower.includes("read") || lower.includes("get") || lower.includes("fetch")) return "Content fetched";
  if (lower.includes("create")) return "Created";
  if (lower.includes("update")) return "Updated";
  if (lower.includes("canvas")) return "Canvas updated";
  return "Completed";
}

function buildSlackExpandedMeta(toolName: string, args: unknown, details: Record<string, unknown>): string[] {
  const summary = buildSlackCallSummary(toolName, args);
  const meta: string[] = [];

  if (summary.primary) {
    meta.push(`target: ${truncateDisplayText(summary.primary, 120)}`);
  }
  for (const item of summary.meta) {
    meta.push(item.replace("=", ": "));
  }

  if (toolName.startsWith("slack_mcp_")) {
    if (typeof details.teamName === "string" && details.teamName.trim().length > 0) {
      meta.push(`workspace: ${details.teamName}`);
    }
    if (typeof details.userName === "string" && details.userName.trim().length > 0) {
      meta.push(`user: ${details.userName}`);
    }
    if (typeof details.sessionId === "string" && details.sessionId.trim().length > 0) {
      meta.push(`session: ${details.sessionId.slice(0, 8)}...`);
    }
    if (typeof details.toolCount === "number") {
      meta.push(`tools: ${details.toolCount}`);
    }
  }

  const lineCount = typeof details.lineCount === "number" ? details.lineCount : undefined;
  const characterCount = typeof details.characterCount === "number" ? details.characterCount : undefined;
  if (typeof lineCount === "number" && typeof characterCount === "number") {
    const outputStats = buildOutputStatsLabel(lineCount, characterCount);
    if (outputStats) {
      meta.push(`output: ${outputStats}`);
    }
  }

  return meta;
}

function renderSlackToolCall(toolName: string, args: unknown, theme: RenderTheme) {
  const summary = buildSlackCallSummary(toolName, args);
  let text = theme.fg("toolTitle", theme.bold(toolName));
  if (summary.primary) {
    text += ` ${theme.fg("accent", truncateDisplayText(summary.primary))}`;
  }
  if (summary.meta.length > 0) {
    text += theme.fg("dim", ` (${summary.meta.join(", ")})`);
  }
  return new Text(text, 0, 0);
}

function renderSlackToolResult(
  toolName: string,
  args: unknown,
  result: ToolExecutionResult,
  options: ToolRenderOptions,
  theme: RenderTheme,
  context: ToolRenderContext,
) {
  if (options.isPartial) {
    return new Text(theme.fg("warning", getSlackPendingLabel(toolName)), 0, 0);
  }

  const details = result.details ?? {};
  const textContent = getTextContent(result.content);

  if (context.isError) {
    const errorText = truncateDisplayText(textContent || "Slack MCP request failed", 140);
    return new Text(theme.fg("error", errorText), 0, 0);
  }

  const lineCount = typeof details.lineCount === "number" ? details.lineCount : countOutputLines(textContent);
  const characterCount =
    typeof details.characterCount === "number" ? details.characterCount : textContent.length;

  let text = theme.fg("success", getSlackSuccessLabel(toolName, details));
  text += theme.fg("muted", formatOutputStats(lineCount, characterCount));

  if (options.expanded) {
    const meta = buildSlackExpandedMeta(toolName, args, details);
    if (meta.length > 0) {
      text += `\n${theme.fg("dim", meta.join("\n"))}`;
    }

    const preview = buildPreviewLines(textContent, 10);
    if (preview.length > 0) {
      text += `\n${theme.fg("muted", "preview:")}`;
      text += `\n${preview.map((line) => theme.fg("muted", `  ${line}`)).join("\n")}`;
      const hidden = Math.max(0, lineCount - preview.length);
      if (hidden > 0) {
        text += `\n${theme.fg("dim", `  … ${hidden} more line${hidden === 1 ? "" : "s"}`)}`;
      }
    }
  }

  return new Text(text, 0, 0);
}

function createSlackToolRenderer(toolName: string) {
  return {
    renderCall(args: unknown, theme: RenderTheme) {
      return renderSlackToolCall(toolName, args, theme);
    },
    renderResult(
      result: ToolExecutionResult,
      options: ToolRenderOptions,
      theme: RenderTheme,
      context: ToolRenderContext,
    ) {
      return renderSlackToolResult(toolName, context.args, result, options, theme, context);
    },
  };
}

function toolResult(tool: string, text: string, details: Record<string, unknown> = {}): ToolExecutionResult {
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

function toolError(tool: string, text: string, details: Record<string, unknown> = {}): ToolExecutionResult {
  return {
    content: [{ type: "text", text }],
    isError: true,
    details: { tool, ...details },
  };
}

// =============================================================================
// Status Helpers
// =============================================================================

function buildConnectedStatusMessage(client: SlackMCPClient): string {
  const tools = client.getTools();
  const preview = tools.slice(0, 12).map((tool) => `- ${tool.name}`).join("\n");
  const hidden = Math.max(0, tools.length - 12);
  const toolList = tools.length > 0
    ? `\n\nAvailable tools:\n${preview}${hidden > 0 ? `\n- ... ${hidden} more` : ""}`
    : "";

  return [
    "Slack MCP Status:",
    "- Connected: Yes",
    `- Workspace: ${client.state.teamName ?? "Unknown"}`,
    `- User: ${client.state.userName ?? client.state.userId ?? "Unknown"}`,
    `- Session: ${client.state.sessionId ? `${client.state.sessionId.slice(0, 8)}...` : "None"}`,
    `- Protocol: ${client.state.protocolVersion ?? "Unknown"}`,
    `- Tools: ${tools.length}`,
    toolList,
  ].join("\n");
}

function applyStatus(ctx: ExtensionContext, _client: SlackMCPClient | null, _config: StoredConfig | null): void {
  ctx.ui.setStatus("slack-mcp", undefined);
}

// =============================================================================
// Connection Management
// =============================================================================

let mcpClient: SlackMCPClient | null = null;
let persistedConfig: StoredConfig | null = null;
let runtimeOverrides: RuntimeOverrides = {};
let registeredToolNames = new Set<string>();
const storage = new FileConfigStorage();

function getEffectiveConfig(): StoredConfig {
  return mergeRuntimeOverrides(persistedConfig, runtimeOverrides);
}

async function savePersistedConfig(next: StoredConfig): Promise<void> {
  persistedConfig = next;
  await storage.save(next);
}

async function updatePersistedTokens(next: Partial<StoredConfig>): Promise<void> {
  const current = persistedConfig ?? {};
  await savePersistedConfig({ ...current, ...next });
}

async function clearStoredTokens(): Promise<void> {
  const current = persistedConfig ?? {};
  await savePersistedConfig({
    ...current,
    accessToken: undefined,
    refreshToken: undefined,
    expiresAt: undefined,
    teamName: undefined,
    teamId: undefined,
    userName: undefined,
    userId: undefined,
  });
}

async function refreshAccessTokenAndPersist(): Promise<string> {
  const config = getEffectiveConfig();
  const bundle = await refreshTokens(config);
  const identity = await fetchSlackIdentity(bundle.accessToken);

  await updatePersistedTokens({
    accessToken: bundle.accessToken,
    refreshToken: bundle.refreshToken,
    expiresAt: bundle.expiresAt,
    teamName: identity.teamName ?? bundle.teamName,
    teamId: identity.teamId ?? bundle.teamId,
    userName: identity.userName,
    userId: identity.userId ?? bundle.userId,
  });

  if (mcpClient) {
    mcpClient.setIdentity(identity);
  }

  return bundle.accessToken;
}

async function getAccessTokenForRequests(): Promise<string> {
  const config = getEffectiveConfig();
  if (!isNonEmptyString(config.accessToken)) {
    throw new Error("No Slack access token is stored. Connect with /slack-mcp first.");
  }

  if (typeof config.expiresAt === "number" && config.expiresAt <= Date.now()) {
    return refreshAccessTokenAndPersist();
  }

  return config.accessToken;
}

function getConnectionSummaryText(client: SlackMCPClient | null): string {
  if (!client?.state.connected) {
    return buildDisconnectedMessage(getEffectiveConfig());
  }
  return buildConnectedStatusMessage(client);
}

async function connectWithSavedConfig(client: SlackMCPClient, notify?: NotifyFn): Promise<boolean> {
  const config = getEffectiveConfig();
  if (!isNonEmptyString(config.accessToken)) return false;

  notify?.("Connecting to saved Slack MCP session...");
  try {
    const identity = await fetchSlackIdentity(config.accessToken);
    client.setIdentity(identity);
    await client.connect();
    return true;
  } catch (error) {
    try {
      const refreshedAccessToken = await refreshAccessTokenAndPersist();
      const identity = await fetchSlackIdentity(refreshedAccessToken);
      client.setIdentity(identity);
      await client.connect();
      return true;
    } catch {
      await clearStoredTokens();
      const message = error instanceof Error ? error.message : String(error);
      notify?.(`Saved Slack credentials are no longer valid: ${message}`, "warning");
      return false;
    }
  }
}

async function performInteractiveOAuth(config: StoredConfig, notify: NotifyFn): Promise<void> {
  if (!isNonEmptyString(config.clientId)) {
    throw new Error(buildMissingClientIdError());
  }

  const redirectUri = config.redirectUri ?? DEFAULT_REDIRECT_URI;
  const state = randomBytes(16).toString("hex");
  const { codeVerifier, codeChallenge } = createPkceChallenge();
  const authUrl = buildAuthorizationUrl(config.clientId, redirectUri, codeChallenge, state);
  const callbackServer = await startOAuthCallbackServer(redirectUri, state);

  try {
    notify("Opening Slack authorization page...");
    await openBrowser(authUrl);
    notify("Waiting for Slack authorization callback...");

    const callbackResult = await callbackServer.result;
    if (callbackResult.error) {
      throw new Error(callbackResult.errorDescription ?? callbackResult.error);
    }
    if (!callbackResult.code) {
      throw new Error("Slack did not return an authorization code.");
    }

    notify("Exchanging Slack authorization code for tokens...");
    const bundle = await exchangeCodeForTokens(
      config.clientId,
      config.clientSecret,
      redirectUri,
      callbackResult.code,
      codeVerifier,
    );
    const identity = await fetchSlackIdentity(bundle.accessToken);

    await updatePersistedTokens({
      accessToken: bundle.accessToken,
      refreshToken: bundle.refreshToken,
      expiresAt: bundle.expiresAt,
      teamName: identity.teamName ?? bundle.teamName,
      teamId: identity.teamId ?? bundle.teamId,
      userName: identity.userName,
      userId: identity.userId ?? bundle.userId,
    });
  } finally {
    callbackServer.close();
  }
}

async function ensureClientIdConfigured(ctx: ExtensionContext): Promise<boolean> {
  const current = getEffectiveConfig();
  if (isNonEmptyString(current.clientId)) {
    return true;
  }

  const clientId = await ctx.ui.input(
    "Slack MCP Client ID",
    "1234567890.1234567890",
  );
  if (!isNonEmptyString(clientId)) {
    ctx.ui.notify("Slack MCP connection cancelled.", "warning");
    return false;
  }

  await savePersistedConfig({
    ...persistedConfig,
    clientId: clientId.trim(),
    redirectUri: (persistedConfig?.redirectUri ?? runtimeOverrides.redirectUri ?? DEFAULT_REDIRECT_URI).trim(),
  });
  return true;
}

function buildRegisteredToolName(originName: string, pi: ExtensionAPI): string {
  const existingTool = pi.getAllTools().find((tool) => tool.name === originName);
  if (!existingTool) return originName;
  if (registeredToolNames.has(originName)) return originName;
  return `slack_mcp__${originName}`;
}

function createRegisteredToolDefinition(client: SlackMCPClient, tool: MCPTool, pi: ExtensionAPI) {
  const registeredName = buildRegisteredToolName(tool.name, pi);
  return {
    name: registeredName,
    label: `Slack: ${humanizeWords(tool.name)}`,
    description: tool.description || `Slack MCP tool: ${tool.name}`,
    promptSnippet: normalizeToolPromptSnippet(tool.description, tool.name),
    parameters: Type.Unsafe(isRecord(tool.inputSchema) ? tool.inputSchema : Type.Object({})),
    ...createSlackToolRenderer(registeredName),
    async execute(
      _toolCallId: string,
      params: unknown,
      _signal: AbortSignal,
      onUpdate?: (
        payload: { content: Array<{ type: "text"; text: string }>; details?: Record<string, unknown> },
      ) => void,
      _ctx?: ExtensionContext,
    ): Promise<ToolExecutionResult> {
      if (!client.state.connected) {
        return toolError(
          registeredName,
          "Slack MCP is not connected. Run /slack-mcp or use slack_mcp_connect first.",
          { connected: false },
        );
      }

      onUpdate?.({
        content: [{ type: "text", text: `Running ${registeredName}...` }],
        details: { tool: registeredName, phase: "running" },
      });

      try {
        const result = await client.callTool(tool.name, params as Record<string, unknown>);
        return toolResult(registeredName, result, { connected: true });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return toolError(registeredName, `Error: ${message}`, { error: message, connected: client.state.connected });
      }
    },
  };
}

function registerDiscoveredTools(pi: ExtensionAPI, client: SlackMCPClient): number {
  let registeredCount = 0;
  for (const tool of client.getTools()) {
    const registeredName = buildRegisteredToolName(tool.name, pi);
    if (registeredToolNames.has(registeredName)) continue;
    if (pi.getAllTools().find((entry) => entry.name === registeredName)) continue;

    pi.registerTool(createRegisteredToolDefinition(client, tool, pi));
    registeredToolNames.add(registeredName);
    registeredCount += 1;
  }
  return registeredCount;
}

async function connectAndRegister(pi: ExtensionAPI, client: SlackMCPClient): Promise<number> {
  await client.connect();
  const registeredCount = registerDiscoveredTools(pi, client);
  return registeredCount;
}

async function disconnectAndForgetTokens(client: SlackMCPClient | null): Promise<void> {
  if (client) {
    await client.disconnect();
  }
  await clearStoredTokens();
}

// =============================================================================
// Extension Entry Point
// =============================================================================

export {
  buildAuthorizationUrl,
  buildConnectedStatusMessage,
  buildDisconnectedMessage,
  buildPreviewLines,
  buildSlackCallSummary,
  coerceNumericProperties,
  countOutputLines,
  createPkceChallenge,
  getEffectiveConfig,
  normalizeMcpToolResult,
  parseSlackTokenBundle,
  refreshTokens,
  resolveCallbackResult,
  startOAuthCallbackServer,
  truncateDisplayText,
};

export default function slackMcpExtension(pi: ExtensionAPI) {
  pi.registerFlag("--slack-mcp-auth-file", {
    description: "Path to the persisted Slack MCP auth file.",
    type: "string",
  });
  pi.registerFlag("--slack-mcp-client-id", {
    description: "Slack app client ID used for Slack MCP OAuth.",
    type: "string",
  });
  pi.registerFlag("--slack-mcp-client-secret", {
    description: "Optional Slack app client secret used for Slack MCP OAuth refresh.",
    type: "string",
  });
  pi.registerFlag("--slack-mcp-redirect-uri", {
    description: "Redirect URI registered on the Slack app for Slack MCP OAuth.",
    type: "string",
  });

  runtimeOverrides = getRuntimeOverrides(pi);
  registeredToolNames = new Set<string>();
  mcpClient = new SlackMCPClient(getAccessTokenForRequests, refreshAccessTokenAndPersist);

  const registerToolsFromClient = () => {
    if (!mcpClient) return 0;
    return registerDiscoveredTools(pi, mcpClient);
  };

  async function ensureConnected(notify: NotifyFn): Promise<void> {
    if (!mcpClient) {
      throw new Error("Slack MCP client is not initialized.");
    }

    if (mcpClient.state.connected) {
      return;
    }

    const config = getEffectiveConfig();
    if (!isNonEmptyString(config.clientId)) {
      throw new Error(buildMissingClientIdError());
    }

    const reusedSavedConfig = await connectWithSavedConfig(mcpClient, notify);
    if (!reusedSavedConfig) {
      await performInteractiveOAuth(config, notify);
      const refreshedConfig = getEffectiveConfig();
      const accessToken = refreshedConfig.accessToken;
      if (!isNonEmptyString(accessToken)) {
        throw new Error("Slack OAuth completed without storing an access token.");
      }

      const identity = await fetchSlackIdentity(accessToken);
      mcpClient.setIdentity(identity);
      await connectAndRegister(pi, mcpClient);
      return;
    }

    registerToolsFromClient();
  }

  pi.on("session_start", async (_event, ctx) => {
    persistedConfig = await storage.load();
    applyStatus(ctx, mcpClient, getEffectiveConfig());

    if (!mcpClient) return;

    const config = getEffectiveConfig();
    if (!isNonEmptyString(config.accessToken)) {
      applyStatus(ctx, mcpClient, config);
      return;
    }

    const connected = await connectWithSavedConfig(mcpClient);
    if (connected) {
      registerToolsFromClient();
    }
    applyStatus(ctx, mcpClient, getEffectiveConfig());
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    ctx.ui.setStatus("slack-mcp", undefined);
  });

  pi.registerCommand("slack-mcp", {
    description: "Connect to Slack MCP, show status, or disconnect",
    async handler(args, ctx) {
      if (!mcpClient) {
        ctx.ui.notify("Slack MCP client is not initialized.", "error");
        return;
      }

      const command = args.trim();
      if (command === "status") {
        ctx.ui.notify(getConnectionSummaryText(mcpClient), "info");
        applyStatus(ctx, mcpClient, getEffectiveConfig());
        return;
      }

      if (command === "disconnect") {
        await disconnectAndForgetTokens(mcpClient);
        applyStatus(ctx, mcpClient, getEffectiveConfig());
        ctx.ui.notify("Disconnected from Slack MCP.", "info");
        return;
      }

      if (command === "forget") {
        await storage.clear();
        persistedConfig = null;
        if (mcpClient.state.connected) {
          await mcpClient.disconnect();
        }
        applyStatus(ctx, mcpClient, getEffectiveConfig());
        ctx.ui.notify("Cleared all saved Slack MCP configuration.", "info");
        return;
      }

      if (command.startsWith("client-id ")) {
        const clientId = command.slice("client-id ".length).trim();
        if (!isNonEmptyString(clientId)) {
          ctx.ui.notify("Usage: /slack-mcp client-id <value>", "warning");
          return;
        }
        await savePersistedConfig({
          ...persistedConfig,
          clientId,
          redirectUri: persistedConfig?.redirectUri ?? runtimeOverrides.redirectUri ?? DEFAULT_REDIRECT_URI,
        });
        applyStatus(ctx, mcpClient, getEffectiveConfig());
        ctx.ui.notify("Saved Slack MCP client ID.", "info");
        return;
      }

      if (command.startsWith("redirect-uri ")) {
        const redirectUri = command.slice("redirect-uri ".length).trim();
        try {
          normalizeRedirectUri(redirectUri);
        } catch (error) {
          ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
          return;
        }
        await savePersistedConfig({ ...persistedConfig, redirectUri });
        applyStatus(ctx, mcpClient, getEffectiveConfig());
        ctx.ui.notify("Saved Slack MCP redirect URI.", "info");
        return;
      }

      if (!mcpClient.state.connected) {
        const configured = await ensureClientIdConfigured(ctx);
        if (!configured) return;

        const notify = createUiNotifier(ctx);
        try {
          await ensureConnected(notify);
          const registered = registerToolsFromClient();
          applyStatus(ctx, mcpClient, getEffectiveConfig());
          const workspace = mcpClient.state.teamName ?? "Slack";
          const tools = mcpClient.getTools().length;
          const message =
            registered > 0
              ? `Connected to Slack MCP for ${workspace}. Registered ${registered} new tool${registered === 1 ? "" : "s"}.`
              : `Connected to Slack MCP for ${workspace}. ${tools} tool${tools === 1 ? "" : "s"} available.`;
          ctx.ui.notify(message, "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          applyStatus(ctx, mcpClient, getEffectiveConfig());
          ctx.ui.notify(`Slack MCP connection failed: ${message}`, "error");
        }
        return;
      }

      const choice = await ctx.ui.select(getConnectionSummaryText(mcpClient), [
        "Reconnect",
        "Disconnect",
        "Cancel",
      ]);

      if (choice === "Reconnect") {
        try {
          await disconnectAndForgetTokens(mcpClient);
          const configured = await ensureClientIdConfigured(ctx);
          if (!configured) return;
          await ensureConnected(createUiNotifier(ctx));
          registerToolsFromClient();
          applyStatus(ctx, mcpClient, getEffectiveConfig());
          ctx.ui.notify("Reconnected to Slack MCP.", "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          applyStatus(ctx, mcpClient, getEffectiveConfig());
          ctx.ui.notify(`Slack MCP reconnection failed: ${message}`, "error");
        }
        return;
      }

      if (choice === "Disconnect") {
        const confirmed = await ctx.ui.confirm(
          "Disconnect Slack MCP",
          "Clear the saved Slack access token and disconnect from Slack MCP?",
        );
        if (!confirmed) return;
        await disconnectAndForgetTokens(mcpClient);
        applyStatus(ctx, mcpClient, getEffectiveConfig());
        ctx.ui.notify("Disconnected from Slack MCP.", "info");
      }
    },
  });

  pi.registerTool({
    name: "slack_mcp_connect",
    label: "Slack MCP Connect",
    description: "Connect to Slack via Slack's official MCP server using OAuth",
    promptSnippet: "Connect to Slack MCP when Slack tools are needed but not yet authorized.",
    parameters: Type.Object({}),
    ...createSlackToolRenderer("slack_mcp_connect"),
    async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
      if (!mcpClient) {
        return toolError("slack_mcp_connect", "Slack MCP client is not initialized.");
      }

      const config = getEffectiveConfig();
      if (!isNonEmptyString(config.clientId)) {
        return toolError("slack_mcp_connect", buildMissingClientIdError(), { connected: false });
      }

      if (mcpClient.state.connected) {
        return toolResult("slack_mcp_connect", buildConnectedStatusMessage(mcpClient), {
          connected: true,
          teamName: mcpClient.state.teamName,
          userName: mcpClient.state.userName,
          sessionId: mcpClient.state.sessionId,
          toolCount: mcpClient.getTools().length,
        });
      }

      try {
        const notify = ctx ? createUiNotifier(ctx) : undefined;
        await ensureConnected(notify ?? (() => undefined));
        const registered = registerToolsFromClient();
        if (ctx) applyStatus(ctx, mcpClient, getEffectiveConfig());
        return toolResult(
          "slack_mcp_connect",
          `${buildConnectedStatusMessage(mcpClient)}\n\nRegistered ${registered} new tool${registered === 1 ? "" : "s"}.`,
          {
            connected: true,
            teamName: mcpClient.state.teamName,
            userName: mcpClient.state.userName,
            sessionId: mcpClient.state.sessionId,
            toolCount: mcpClient.getTools().length,
          },
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (ctx) applyStatus(ctx, mcpClient, getEffectiveConfig());
        return toolError("slack_mcp_connect", `Connection failed: ${message}`, { error: message });
      }
    },
  });

  pi.registerTool({
    name: "slack_mcp_disconnect",
    label: "Slack MCP Disconnect",
    description: "Disconnect from Slack MCP and clear the stored Slack access token",
    promptSnippet: "Disconnect from Slack MCP when the user wants Slack access removed.",
    parameters: Type.Object({}),
    ...createSlackToolRenderer("slack_mcp_disconnect"),
    async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
      await disconnectAndForgetTokens(mcpClient);
      if (ctx && mcpClient) applyStatus(ctx, mcpClient, getEffectiveConfig());
      return toolResult(
        "slack_mcp_disconnect",
        "Disconnected from Slack MCP and cleared the stored Slack access token.",
        { connected: false },
      );
    },
  });

  pi.registerTool({
    name: "slack_mcp_status",
    label: "Slack MCP Status",
    description: "Check the current Slack MCP connection status",
    promptSnippet: "Check whether Slack MCP is already connected before trying Slack tools.",
    parameters: Type.Object({}),
    ...createSlackToolRenderer("slack_mcp_status"),
    async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
      if (ctx && mcpClient) applyStatus(ctx, mcpClient, getEffectiveConfig());

      if (!mcpClient?.state.connected) {
        return toolResult("slack_mcp_status", buildDisconnectedMessage(getEffectiveConfig()), {
          connected: false,
          toolCount: 0,
        });
      }

      return toolResult("slack_mcp_status", buildConnectedStatusMessage(mcpClient), {
        connected: true,
        teamName: mcpClient.state.teamName,
        userName: mcpClient.state.userName,
        sessionId: mcpClient.state.sessionId,
        toolCount: mcpClient.getTools().length,
      });
    },
  });
}
