/**
 * Notion MCP Client Extension for pi
 *
 * Connects to the official Notion MCP server at https://mcp.notion.com/mcp
 * using OAuth authentication.
 *
 * Usage:
 *   /notion                    - Status, connect, or disconnect
 *   "Search my Notion for X"    - Natural language (tools auto-discovered after connect)
 */

import { createHash, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import { getPort as lookupPort } from "portfinder";
import { registerNotionGuardrails } from "./pi-notion.ts";

// =============================================================================
// Constants
// =============================================================================

const NOTION_MCP_URL = "https://mcp.notion.com/mcp";
const NOTION_MCP_TOKEN_URL = "https://mcp.notion.com/token";
const HTTP_REQUEST_COMPLETE_MARKER = "\r\n\r\n";
const CALLBACK_PATH_PREFIX = "GET /callback?";
const NOTION_MCP_AUTH_FILE_ENV = "NOTION_MCP_AUTH_FILE";
const NOTION_MCP_AUTH_FILE_LEGACY_ENV = "NOTION_MCP_AUTH";
const DEFAULT_TOKEN_LIFETIME_MS = 60 * 60 * 1000;
const TOKEN_REFRESH_WINDOW_MS = 5 * 60 * 1000;

function getHomeDir(): string {
  return process.env.HOME || homedir();
}

type NotifyLevel = "info" | "error";
type NotifyFn = (message: string, type?: NotifyLevel) => void;

type ToolExecutionResult = {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
  details: Record<string, unknown>;
};

// =============================================================================
// Types
// =============================================================================

interface MCPTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

interface MCPClientState {
  connected: boolean;
  authenticated: boolean;
  sessionId: string | null;
  accessToken: string | null;
  mcpUrl: string | null;
}

// =============================================================================
// OAuth Callback Server
// =============================================================================

interface OAuthCallbackResult {
  code?: string;
  accessToken?: string;
  error?: string;
  errorDescription?: string;
}

interface OAuthCallbackServerResult {
  port: number;
  result: Promise<OAuthCallbackResult>;
}

function buildHtmlResponse(statusLine: string, html: string): string {
  return `${statusLine}\r\nContent-Length: ${html.length}\r\nContent-Type: text/html\r\n\r\n${html}`;
}

function writeHtmlResponse(socket: NodeJS.WritableStream, statusLine: string, html: string): void {
  socket.write(buildHtmlResponse(statusLine, html));
}

function extractCallbackParams(buffer: string): URLSearchParams | null {
  if (!buffer.includes(HTTP_REQUEST_COMPLETE_MARKER)) return null;

  const requestLine = buffer.split("\r\n", 1)[0] ?? "";
  if (!requestLine.startsWith(CALLBACK_PATH_PREFIX)) return null;

  const queryString = requestLine.slice(CALLBACK_PATH_PREFIX.length).split(" ", 1)[0] ?? "";
  return new URLSearchParams(queryString);
}

function resolveCallbackResult(
  params: URLSearchParams,
  expectedState: string,
): {
  response: { statusLine: string; html: string };
  result: OAuthCallbackResult;
} {
  if (params.get("state") !== expectedState) {
    return {
      response: {
        statusLine: "HTTP/1.1 400 Bad Request",
        html: `<html><body><h1>State mismatch</h1><p>Please try again.</p></body></html>`,
      },
      result: { error: "State mismatch" },
    };
  }

  const error = params.get("error");
  if (error) {
    return {
      response: {
        statusLine: "HTTP/1.1 400 Bad Request",
        html: `<html><body><h1>Authorization failed</h1><p>Error: ${error}</p><p>${params.get("error_description") || ""}</p></body></html>`,
      },
      result: {
        error,
        errorDescription: params.get("error_description") || undefined,
      },
    };
  }

  const accessToken = params.get("access_token");
  if (accessToken) {
    return {
      response: {
        statusLine: "HTTP/1.1 200 OK",
        html: `<html><body><h1>Authorized!</h1><p>You can close this window.</p><script>window.close();</script></body></html>`,
      },
      result: { accessToken },
    };
  }

  const code = params.get("code");
  if (code) {
    return {
      response: {
        statusLine: "HTTP/1.1 200 OK",
        html: `<html><body><h1>Authorized!</h1><p>You can close this window.</p><script>window.close();</script></body></html>`,
      },
      result: { code },
    };
  }

  return {
    response: {
      statusLine: "HTTP/1.1 400 Bad Request",
      html: `<html><body><h1>Authorization failed</h1><p>No code or token in callback.</p></body></html>`,
    },
    result: { error: "No code or token in callback" },
  };
}

async function startOAuthCallbackServer(
  preferredPort: number,
  state: string,
  timeoutMs = 300000,
): Promise<OAuthCallbackServerResult> {
  const port = await lookupPort({ port: preferredPort });

  const resultPromise = new Promise<OAuthCallbackResult>((resolve, reject) => {
    const server = createServer();
    const finish = (result: OAuthCallbackResult) => {
      clearTimeout(timeout);
      server.close();
      resolve(result);
    };
    const timeout = setTimeout(() => {
      server.close();
      reject(new Error("OAuth callback timed out (5 minutes)"));
    }, timeoutMs);

    server.on("connection", (socket) => {
      let buffer = "";

      socket.on("data", (chunk) => {
        buffer += chunk.toString();
        const params = extractCallbackParams(buffer);
        if (!params) return;

        const { response, result } = resolveCallbackResult(params, state);
        writeHtmlResponse(socket, response.statusLine, response.html);
        socket.end();
        finish(result);
      });

      socket.on("error", () => {});
    });

    server.on("error", (err: NodeJS.ErrnoException) => {
      clearTimeout(timeout);
      reject(new Error(`Callback server error: ${err.message}`));
    });

    server.listen(port, "127.0.0.1", () => {});
  });

  return { port, result: resultPromise };
}

// =============================================================================
// Dynamic Client Registration (RFC 7591)
// =============================================================================

interface ClientRegistration {
  client_id: string;
  client_secret?: string;
}

interface OAuthTokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
}

interface OAuthTokenResult {
  accessToken: string;
  refreshToken?: string;
  tokenType?: string;
  expiresAt: number;
}

async function registerClient(redirectUri: string): Promise<ClientRegistration> {
  const response = await fetch("https://mcp.notion.com/register", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      redirect_uris: [redirectUri],
      token_endpoint_auth_method: "client_secret_post",
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
      client_name: "pi-notion",
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Client registration failed: ${response.status} - ${error}`);
  }

  return (await response.json()) as ClientRegistration;
}

// =============================================================================
// Token Exchange
// =============================================================================

function buildOAuthTokenResult(data: OAuthTokenResponse): OAuthTokenResult {
  const expiresInMs =
    typeof data.expires_in === "number" && data.expires_in > 0
      ? data.expires_in * 1000
      : DEFAULT_TOKEN_LIFETIME_MS;

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    tokenType: data.token_type,
    expiresAt: Date.now() + expiresInMs,
  };
}

async function exchangeCodeForToken(
  code: string,
  redirectUri: string,
  codeVerifier: string,
  clientId: string,
  clientSecret?: string,
): Promise<OAuthTokenResult> {
  const params: Record<string, string> = {
    grant_type: "authorization_code",
    client_id: clientId,
    code,
    redirect_uri: redirectUri,
    code_verifier: codeVerifier,
  };
  if (clientSecret) {
    params.client_secret = clientSecret;
  }
  const body = new URLSearchParams(params);
  const response = await fetch(NOTION_MCP_TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Token exchange failed: ${response.status} - ${error}`);
  }

  const data = (await response.json()) as OAuthTokenResponse;
  return buildOAuthTokenResult(data);
}

async function refreshAccessToken(
  refreshToken: string,
  clientId: string,
  clientSecret?: string,
): Promise<OAuthTokenResult> {
  const params: Record<string, string> = {
    grant_type: "refresh_token",
    refresh_token: refreshToken,
    client_id: clientId,
  };
  if (clientSecret) {
    params.client_secret = clientSecret;
  }

  const body = new URLSearchParams(params);
  const response = await fetch(NOTION_MCP_TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Token refresh failed: ${response.status} - ${error}`);
  }

  const data = (await response.json()) as OAuthTokenResponse;
  return buildOAuthTokenResult(data);
}

function createPkceChallenge(): { codeVerifier: string; codeChallenge: string } {
  const codeVerifier = randomBytes(32).toString("base64url");
  const codeChallenge = createHash("sha256").update(codeVerifier).digest("base64url");
  return { codeVerifier, codeChallenge };
}

function buildAuthorizationUrl(
  registration: ClientRegistration,
  callbackUrl: string,
  codeChallenge: string,
  state: string,
): string {
  const authUrl = new URL("https://mcp.notion.com/authorize");
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("client_id", registration.client_id);
  authUrl.searchParams.set("redirect_uri", callbackUrl);
  authUrl.searchParams.set("code_challenge", codeChallenge);
  authUrl.searchParams.set("code_challenge_method", "S256");
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("prompt", "consent");
  return authUrl.toString();
}

async function resolveAccessToken(
  callbackResult: OAuthCallbackResult,
  callbackUrl: string,
  codeVerifier: string,
  registration: ClientRegistration,
  notify: NotifyFn,
): Promise<OAuthTokenResult> {
  if (callbackResult.error) {
    throw new Error(`Authorization failed: ${callbackResult.error}`);
  }

  if (callbackResult.accessToken) {
    return {
      accessToken: callbackResult.accessToken,
      expiresAt: Date.now() + DEFAULT_TOKEN_LIFETIME_MS,
    };
  }

  if (!callbackResult.code) {
    throw new Error("No authorization code received");
  }

  notify("Exchanging authorization code for token...");
  return await exchangeCodeForToken(
    callbackResult.code,
    callbackUrl,
    codeVerifier,
    registration.client_id,
    registration.client_secret,
  );
}

// =============================================================================
// MCP Client
// =============================================================================

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNumericString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value));
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

class NotionMCPClient {
  state: MCPClientState = {
    connected: false,
    authenticated: false,
    sessionId: null,
    accessToken: null,
    mcpUrl: null,
  };

  private messageId = 0;
  private sessionId: string | null = null;
  private _accessToken: string | null = null;
  private _tools: MCPTool[] = [];
  private storedConfig: StoredConfig | null = null;
  private refreshPromise: Promise<StoredConfig> | null = null;

  async connect(mcpUrl: string, accessToken: string, storedConfig?: StoredConfig): Promise<void> {
    this.storedConfig = storedConfig
      ? { ...storedConfig, mcpUrl, accessToken: storedConfig.accessToken || accessToken }
      : { ...this.storedConfig, mcpUrl, accessToken };

    await this.ensureFreshAccessToken();

    this._accessToken = this.storedConfig?.accessToken ?? accessToken;
    this.state.accessToken = this._accessToken;
    this.state.mcpUrl = mcpUrl;
    this.state.authenticated = true;

    // Initialize MCP connection (session ID captured from response header in sendRequest)
    await this.sendRequest(mcpUrl, "initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "pi-notion", version: "1.0.0" },
    });

    // If server didn't return a session ID, generate one locally
    if (!this.sessionId) {
      this.sessionId = randomBytes(16).toString("hex");
      this.state.sessionId = this.sessionId;
    }
    this.state.connected = true;

    // Discover tools
    await this.discoverTools(mcpUrl);

    // Send initialized notification
    await this.sendNotification(mcpUrl, "initialized", {});
  }

  async disconnect(): Promise<void> {
    if (this.sessionId && this.state.mcpUrl) {
      try {
        await fetch(`${this.state.mcpUrl}/${this.sessionId}`, {
          method: "DELETE",
          headers: {
            "Content-Type": "application/json",
            Authorization: this._accessToken ? `Bearer ${this._accessToken}` : "",
          },
        });
      } catch {
        // Ignore errors on disconnect
      }
    }
    this.state = {
      connected: false,
      authenticated: false,
      sessionId: null,
      accessToken: null,
      mcpUrl: null,
    };
    this.sessionId = null;
    this._accessToken = null;
    this._tools = [];
    this.storedConfig = null;
    this.refreshPromise = null;
  }

  getTools(): MCPTool[] {
    return this._tools;
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    };
    if (this.sessionId) {
      headers["MCP-Session-Id"] = this.sessionId;
    }
    if (this._accessToken) {
      headers.Authorization = `Bearer ${this._accessToken}`;
    }
    return headers;
  }

  private hasRefreshCredentials(
    config: StoredConfig | null,
  ): config is StoredConfig & { refreshToken: string; clientId: string } {
    return Boolean(
      config &&
        typeof config.refreshToken === "string" &&
        config.refreshToken.trim().length > 0 &&
        typeof config.clientId === "string" &&
        config.clientId.trim().length > 0,
    );
  }

  private isTokenExpiring(config: StoredConfig | null): boolean {
    return typeof config?.expiresAt === "number" && Date.now() >= config.expiresAt - TOKEN_REFRESH_WINDOW_MS;
  }

  private isInvalidTokenMessage(message: string): boolean {
    const normalized = message.toLowerCase();
    return (
      normalized.includes("invalid_token") ||
      normalized.includes("token expired") ||
      normalized.includes("expired token") ||
      (normalized.includes("token") && normalized.includes("expired")) ||
      normalized.includes("unauthorized")
    );
  }

  private shouldClearStoredAuth(message: string): boolean {
    const normalized = message.toLowerCase();
    return (
      normalized.includes("invalid_grant") ||
      normalized.includes("invalid refresh") ||
      normalized.includes("invalid refresh token") ||
      normalized.includes("unauthorized_client")
    );
  }

  private async ensureFreshAccessToken(): Promise<void> {
    if (!this.isTokenExpiring(this.storedConfig)) return;
    await this.refreshStoredToken();
  }

  private async refreshStoredToken(): Promise<StoredConfig> {
    if (!this.hasRefreshCredentials(this.storedConfig)) {
      throw new Error("Saved Notion MCP credentials cannot be refreshed; reconnect to Notion.");
    }

    if (this.refreshPromise) {
      return await this.refreshPromise;
    }

    this.refreshPromise = (async () => {
      const current = this.storedConfig;
      if (!this.hasRefreshCredentials(current)) {
        throw new Error("Saved Notion MCP credentials cannot be refreshed; reconnect to Notion.");
      }

      const refreshed = await refreshAccessToken(current.refreshToken, current.clientId, current.clientSecret);
      const nextConfig: StoredConfig = {
        ...current,
        accessToken: refreshed.accessToken,
        refreshToken: refreshed.refreshToken ?? current.refreshToken,
        tokenType: refreshed.tokenType ?? current.tokenType,
        expiresAt: refreshed.expiresAt,
      };

      this.storedConfig = nextConfig;
      this._accessToken = nextConfig.accessToken;
      this.state.accessToken = nextConfig.accessToken;
      await storage.save(nextConfig);
      return nextConfig;
    })();

    try {
      return await this.refreshPromise;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (this.shouldClearStoredAuth(message)) {
        await storage.clear();
        this.storedConfig = null;
      }
      throw error;
    } finally {
      this.refreshPromise = null;
    }
  }

  private async tryRefreshAfterUnauthorized(): Promise<boolean> {
    if (!this.hasRefreshCredentials(this.storedConfig)) {
      return false;
    }

    try {
      await this.refreshStoredToken();
      return true;
    } catch {
      return false;
    }
  }

  private async tryRefreshAfterMcpError(message: string): Promise<boolean> {
    if (!this.isInvalidTokenMessage(message) || !this.hasRefreshCredentials(this.storedConfig)) {
      return false;
    }

    try {
      await this.refreshStoredToken();
      return true;
    } catch {
      return false;
    }
  }

  private captureSessionId(response: Response): void {
    const sessionHeader = response.headers.get("mcp-session-id");
    if (sessionHeader) {
      this.sessionId = sessionHeader;
      this.state.sessionId = sessionHeader;
    }
  }

  private async postWithAuth(mcpUrl: string, body: string, allowRefreshRetry = true): Promise<Response> {
    await this.ensureFreshAccessToken();

    const response = await fetch(mcpUrl, {
      method: "POST",
      headers: this.getHeaders(),
      body,
    });

    this.captureSessionId(response);

    if (response.status === 401 && allowRefreshRetry && (await this.tryRefreshAfterUnauthorized())) {
      return await this.postWithAuth(mcpUrl, body, false);
    }

    return response;
  }

  private async sendRequest(mcpUrl: string, method: string, params: Record<string, unknown>): Promise<unknown> {
    return await this.sendRequestInternal(mcpUrl, method, params, true);
  }

  private async sendRequestInternal(
    mcpUrl: string,
    method: string,
    params: Record<string, unknown>,
    allowRefreshRetry: boolean,
  ): Promise<unknown> {
    const id = ++this.messageId;
    const request = { jsonrpc: "2.0", id, method, params };
    const response = await this.postWithAuth(mcpUrl, JSON.stringify(request), allowRefreshRetry);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const contentType = response.headers.get("content-type") || "";
    const data: { result?: unknown; error?: { message: string } } = contentType.includes("text/event-stream")
      ? await this.parseSSEResponse(response)
      : await response.json();

    if (data.error) {
      if (allowRefreshRetry && (await this.tryRefreshAfterMcpError(data.error.message))) {
        return await this.sendRequestInternal(mcpUrl, method, params, false);
      }
      throw new Error(`MCP Error: ${data.error.message}`);
    }
    return data.result;
  }

  private async parseSSEResponse(response: Response): Promise<{ result?: unknown; error?: { message: string } }> {
    const text = await response.text();
    const lines = text.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const jsonStr = line.slice(6).trim();
        if (jsonStr) {
          return JSON.parse(jsonStr);
        }
      }
    }
    throw new Error("No data found in SSE response");
  }

  private async sendNotification(mcpUrl: string, method: string, params: Record<string, unknown>): Promise<void> {
    const notification = { jsonrpc: "2.0", method, params };
    await this.postWithAuth(mcpUrl, JSON.stringify(notification));
  }

  private async discoverTools(mcpUrl: string): Promise<void> {
    try {
      const result = await this.sendRequest(mcpUrl, "tools/list", {});
      const tools = (result as { tools?: MCPTool[] })?.tools || [];
      this._tools = tools.map((tool) => ({
        name: tool.name,
        description: tool.description || "",
        inputSchema: (tool.inputSchema as Record<string, unknown>) || {},
        outputSchema: isRecord(tool.outputSchema) ? tool.outputSchema : undefined,
      }));
    } catch {
      this._tools = [];
    }
  }

  async callToolRaw(mcpUrl: string, name: string, args: Record<string, unknown>): Promise<unknown> {
    const coerced = coerceNumericProperties(args);
    return await this.sendRequest(mcpUrl, "tools/call", { name, arguments: coerced });
  }

  async callTool(mcpUrl: string, name: string, args: Record<string, unknown>): Promise<string> {
    const result = await this.callToolRaw(mcpUrl, name, args);
    const content = (result as { content?: Array<{ type: string; text?: string }> })?.content;
    if (content && Array.isArray(content)) {
      return content.map((c) => (c.type === "text" ? c.text : JSON.stringify(c))).join("\n");
    }
    return JSON.stringify(result);
  }
}

// =============================================================================
// Token Storage
// =============================================================================

interface StoredConfig {
  mcpUrl: string;
  accessToken: string;
  refreshToken?: string;
  tokenType?: string;
  expiresAt?: number;
  clientId?: string;
  clientSecret?: string;
}

function resolveAuthFilePath(path: string): string {
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

function getLegacyAuthFilePath(): string {
  const configDir = join(getHomeDir(), ".pi", "agent", "extensions");
  return join(configDir, "notion-mcp.json");
}

function getDefaultAuthFilePath(): string {
  const configuredPath = process.env[NOTION_MCP_AUTH_FILE_ENV];
  if (typeof configuredPath === "string" && configuredPath.trim().length > 0) {
    return resolveAuthFilePath(configuredPath);
  }

  const legacyConfiguredPath = process.env[NOTION_MCP_AUTH_FILE_LEGACY_ENV];
  if (typeof legacyConfiguredPath === "string" && legacyConfiguredPath.trim().length > 0) {
    console.warn("[pi-notion] NOTION_MCP_AUTH is deprecated; use NOTION_MCP_AUTH_FILE.");
    return resolveAuthFilePath(legacyConfiguredPath);
  }

  const agentDir = join(getHomeDir(), ".pi", "agent");
  const legacyDir = join(agentDir, "extensions");
  const nextPath = join(agentDir, "notion-mcp-auth.json");
  const legacyPaths = [join(legacyDir, "notion-mcp-auth.json"), getLegacyAuthFilePath()];

  for (const legacyPath of legacyPaths) {
    if (!existsSync(nextPath) && existsSync(legacyPath)) {
      try {
        mkdirSync(agentDir, { recursive: true });
        renameSync(legacyPath, nextPath);
        console.warn(`[pi-notion] Migrated legacy MCP auth file from ${legacyPath} to ${nextPath}.`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.warn(`[pi-notion] Failed to migrate legacy MCP auth file ${legacyPath}: ${message}`);
      }
    }
  }

  return nextPath;
}

class FileTokenStorage {
  private path: string;

  constructor() {
    this.path = getDefaultAuthFilePath();
  }

  async save(config: StoredConfig): Promise<void> {
    try {
      mkdirSync(dirname(this.path), { recursive: true });
      writeFileSync(this.path, JSON.stringify(config, null, 2), "utf-8");
    } catch (error) {
      console.error("Failed to save config:", error);
    }
  }

  async load(): Promise<StoredConfig | null> {
    if (!existsSync(this.path)) {
      return null;
    }
    try {
      return JSON.parse(readFileSync(this.path, "utf-8")) as StoredConfig;
    } catch {
      return null;
    }
  }

  async clear(): Promise<void> {
    if (existsSync(this.path)) {
      try {
        const { unlinkSync } = await import("node:fs");
        unlinkSync(this.path);
      } catch {
        // Ignore
      }
    }
  }
}

// =============================================================================
// Extension Entry Point
// =============================================================================

let mcpClient: NotionMCPClient | null = null;
const storage = new FileTokenStorage();

async function openBrowser(url: string): Promise<void> {
  const { exec } = await import("node:child_process");
  const platform = process.platform;
  const cmd = platform === "darwin" ? "open" : platform === "win32" ? "start" : "xdg-open";
  exec(`${cmd} "${url}"`);
}

function createUiNotifier(pi: ExtensionAPI): NotifyFn {
  return (message, type = "info") => {
    try {
      pi.events.emit("ui:notify", { message, type });
    } catch {
      console.log(`[pi-notion] ${message}`);
    }
  };
}

const numberFormatter = new Intl.NumberFormat("en-US");

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

function compactWhitespace(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function truncateDisplayText(text: string, maxLength = 84): string {
  const compact = compactWhitespace(text);
  return compact.length > maxLength ? `${compact.slice(0, maxLength - 1)}…` : compact;
}

function countOutputLines(text: string): number {
  if (!text.trim()) return 0;
  return text.split("\n").filter((line) => line.trim().length > 0).length;
}

function getTextContent(content: Array<{ type: string; text?: string }> | undefined): string {
  return (content ?? [])
    .map((item) => (item.type === "text" ? item.text ?? "" : ""))
    .filter((item) => item.length > 0)
    .join("\n")
    .trim();
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

function getStringValue(input: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = input[key];
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (trimmed.length > 0) return trimmed;
    }
  }
  return undefined;
}

function getNumberValue(input: Record<string, unknown>, key: string): number | undefined {
  const value = input[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
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

function getParentType(input: Record<string, unknown>): string | undefined {
  const parent = input.parent;
  return isRecord(parent) ? getStringValue(parent, "type") : undefined;
}

function buildNotionCallSummary(toolName: string, args: unknown): { primary?: string; meta: string[] } {
  const input = isRecord(args) ? args : {};

  switch (toolName) {
    case "notion-search": {
      const meta: string[] = [];
      const mode = getStringValue(input, "content_search_mode");
      const queryType = getStringValue(input, "query_type");
      if (mode) meta.push(`mode=${mode}`);
      if (queryType) meta.push(`type=${queryType}`);
      return {
        primary: getStringValue(input, "query"),
        meta,
      };
    }
    case "notion-fetch": {
      const meta: string[] = [];
      if (input.include_discussions === true) meta.push("discussions");
      if (input.include_transcript === true) meta.push("transcript");
      return {
        primary: getStringValue(input, "id"),
        meta,
      };
    }
    case "notion-query-database-view": {
      return {
        primary: getStringValue(input, "view_url"),
        meta: [],
      };
    }
    case "notion-create-pages": {
      const meta: string[] = [];
      const pageCount = getArrayLength(input, "pages");
      const parentType = getParentType(input);
      if (parentType) meta.push(`parent=${parentType}`);
      return {
        primary: typeof pageCount === "number" ? `${pageCount} page${pageCount === 1 ? "" : "s"}` : undefined,
        meta,
      };
    }
    case "notion-update-page": {
      const meta: string[] = [];
      const command = getStringValue(input, "command");
      if (command) meta.push(`command=${command}`);
      return {
        primary: getStringValue(input, "page_id"),
        meta,
      };
    }
    case "notion-move-pages": {
      const itemCount = getArrayLength(input, "page_or_database_ids");
      return {
        primary: typeof itemCount === "number" ? `${itemCount} item${itemCount === 1 ? "" : "s"}` : undefined,
        meta: [],
      };
    }
    case "notion-get-users": {
      return {
        primary: getStringValue(input, "query", "user_id") ?? "users",
        meta: [],
      };
    }
    case "notion-get-teams": {
      return {
        primary: getStringValue(input, "query") ?? "teamspaces",
        meta: [],
      };
    }
    default: {
      const pageSize = getNumberValue(input, "page_size");
      const meta = typeof pageSize === "number" ? [`page_size=${pageSize}`] : [];
      const primary =
        getStringValue(
          input,
          "query",
          "id",
          "url",
          "page_url",
          "view_url",
          "page_id",
          "database_id",
          "data_source_id",
          "teamspace_id",
          "user_id",
          "discussion_id",
        ) ??
        ((): string | undefined => {
          const itemCount = getArrayLength(input, "pages", "page_or_database_ids", "user_ids");
          return typeof itemCount === "number"
            ? `${itemCount} item${itemCount === 1 ? "" : "s"}`
            : undefined;
        })();
      return { primary, meta };
    }
  }
}

function shouldShowOutputStats(toolName: string): boolean {
  return !toolName.startsWith("notion_mcp_");
}

function getNotionPendingLabel(toolName: string): string {
  switch (toolName) {
    case "notion-search":
      return "Searching Notion...";
    case "notion-fetch":
      return "Fetching Notion content...";
    case "notion-query-database-view":
      return "Querying Notion view...";
    case "notion_mcp_connect":
      return "Connecting to Notion...";
    case "notion_mcp_disconnect":
      return "Disconnecting from Notion...";
    case "notion_mcp_status":
      return "Checking Notion status...";
    default:
      return "Working with Notion...";
  }
}

function humanizeWords(value: string): string {
  return value.replace(/[-_]+/g, " ").trim();
}

function getNotionSuccessLabel(toolName: string, args: unknown, details: Record<string, unknown>): string {
  if (toolName === "notion_mcp_connect") {
    const toolCount = typeof details.toolCount === "number" ? details.toolCount : undefined;
    return typeof toolCount === "number"
      ? `Connected (${toolCount} tool${toolCount === 1 ? "" : "s"})`
      : "Connected";
  }

  if (toolName === "notion_mcp_disconnect") {
    return "Disconnected";
  }

  if (toolName === "notion_mcp_status") {
    const connected = details.connected === true;
    const toolCount = typeof details.toolCount === "number" ? details.toolCount : 0;
    return connected
      ? `Connected (${toolCount} tool${toolCount === 1 ? "" : "s"})`
      : "Not connected";
  }

  if (toolName === "notion-search") return "Search complete";
  if (toolName === "notion-fetch") return "Content fetched";
  if (toolName === "notion-create-pages") {
    const pageCount = isRecord(args) ? getArrayLength(args, "pages") : undefined;
    return typeof pageCount === "number"
      ? `Created ${pageCount} page${pageCount === 1 ? "" : "s"}`
      : "Pages created";
  }
  if (toolName === "notion-move-pages") {
    const itemCount = isRecord(args) ? getArrayLength(args, "page_or_database_ids") : undefined;
    return typeof itemCount === "number"
      ? `Moved ${itemCount} item${itemCount === 1 ? "" : "s"}`
      : "Pages moved";
  }

  const normalized = toolName.replace(/^notion[-_]?/, "");
  const [action, ...rest] = normalized.split(/[-_]+/);
  const noun = humanizeWords(rest.join(" "));

  switch (action) {
    case "query":
      return noun ? `Queried ${noun}` : "Query complete";
    case "get":
      return noun ? `Fetched ${noun}` : "Fetched";
    case "create":
      return noun ? `Created ${noun}` : "Created";
    case "update":
      return noun ? `Updated ${noun}` : "Updated";
    case "move":
      return noun ? `Moved ${noun}` : "Moved";
    case "duplicate":
      return noun ? `Duplicated ${noun}` : "Duplicated";
    case "delete":
      return noun ? `Deleted ${noun}` : "Deleted";
    case "search":
      return "Search complete";
    case "fetch":
      return "Content fetched";
    default:
      return "Completed";
  }
}

function getExpandedPrimaryLabel(toolName: string): string {
  switch (toolName) {
    case "notion-search":
      return "query";
    case "notion-query-database-view":
      return "view";
    case "notion-create-pages":
      return "request";
    default:
      return "target";
  }
}

function buildNotionExpandedMeta(toolName: string, args: unknown, details: Record<string, unknown>): string[] {
  const input = isRecord(args) ? args : {};
  const meta: string[] = [];

  if (toolName.startsWith("notion_mcp_")) {
    if (typeof details.mcpUrl === "string" && details.mcpUrl.trim().length > 0) {
      meta.push(`url: ${truncateDisplayText(details.mcpUrl, 120)}`);
    }
    if (typeof details.sessionId === "string" && details.sessionId.trim().length > 0) {
      meta.push(`session: ${details.sessionId.slice(0, 8)}...`);
    }
    if (typeof details.toolCount === "number") {
      meta.push(`tools: ${details.toolCount}`);
    }
    return meta;
  }

  const summary = buildNotionCallSummary(toolName, args);
  if (summary.primary) {
    meta.push(`${getExpandedPrimaryLabel(toolName)}: ${truncateDisplayText(summary.primary, 120)}`);
  }

  for (const item of summary.meta) {
    meta.push(item.replace("=", ": "));
  }

  if (toolName === "notion-search") {
    const pageSize = getNumberValue(input, "page_size");
    if (typeof pageSize === "number") {
      meta.push(`page size: ${pageSize}`);
    }
  }

  const lineCount = typeof details.lineCount === "number" ? details.lineCount : 0;
  const characterCount = typeof details.characterCount === "number" ? details.characterCount : 0;
  const outputStats = buildOutputStatsLabel(lineCount, characterCount);
  if (shouldShowOutputStats(toolName) && outputStats) {
    meta.push(`output: ${outputStats}`);
  }

  return meta;
}

function renderNotionToolCall(toolName: string, args: unknown, theme: RenderTheme) {
  const summary = buildNotionCallSummary(toolName, args);
  let text = theme.fg("toolTitle", theme.bold(toolName));
  if (summary.primary) {
    text += ` ${theme.fg("accent", truncateDisplayText(summary.primary))}`;
  }
  if (summary.meta.length > 0) {
    text += theme.fg("dim", ` (${summary.meta.join(", ")})`);
  }
  return new Text(text, 0, 0);
}

function renderNotionToolResult(
  toolName: string,
  args: unknown,
  result: ToolExecutionResult,
  options: ToolRenderOptions,
  theme: RenderTheme,
  context: ToolRenderContext,
) {
  if (options.isPartial) {
    return new Text(theme.fg("warning", getNotionPendingLabel(toolName)), 0, 0);
  }

  const details = result.details ?? {};
  const textContent = getTextContent(result.content);

  if (context.isError) {
    const errorText = truncateDisplayText(textContent || "Notion request failed", 120);
    return new Text(theme.fg("error", errorText), 0, 0);
  }

  const lineCount = typeof details.lineCount === "number" ? details.lineCount : countOutputLines(textContent);
  const characterCount =
    typeof details.characterCount === "number" ? details.characterCount : textContent.length;
  let text = theme.fg("success", getNotionSuccessLabel(toolName, args, details));

  if (shouldShowOutputStats(toolName)) {
    text += theme.fg("muted", formatOutputStats(lineCount, characterCount));
  }

  if (options.expanded) {
    const meta = buildNotionExpandedMeta(toolName, args, details);
    if (meta.length > 0) {
      text += `\n${theme.fg("dim", meta.join("\n"))}`;
    }
  }

  return new Text(text, 0, 0);
}

function createNotionToolRenderer(toolName: string) {
  return {
    renderCall(args: unknown, theme: RenderTheme) {
      return renderNotionToolCall(toolName, args, theme);
    },
    renderResult(
      result: ToolExecutionResult,
      options: ToolRenderOptions,
      theme: RenderTheme,
      context: ToolRenderContext,
    ) {
      return renderNotionToolResult(toolName, context.args, result, options, theme, context);
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

function getConnectionStatusText(client: NotionMCPClient): string {
  const { connected, sessionId, mcpUrl } = client.state;
  const tools = client.getTools();
  const toolList = tools.length > 0 ? `\n\nAvailable tools:\n${tools.map((t) => `- ${t.name}`).join("\n")}` : "";

  return `Notion MCP Status:
- Connected: ${connected ? "Yes" : "No"}
- URL: ${mcpUrl || "None"}
- Session: ${sessionId ? `${sessionId.slice(0, 8)}...` : "None"}
- Tools: ${tools.length} available${toolList}
${!connected ? "\nRun /notion to connect." : ""}`;
}

function getConnectedStatusMessage(client: NotionMCPClient): string {
  const { sessionId, mcpUrl } = client.state;
  const tools = client.getTools();
  return `Connected to Notion MCP
URL: ${mcpUrl}
Session: ${sessionId?.slice(0, 8)}...
Tools: ${tools.length} available`;
}

function applyToolDefaults(toolName: string, params: unknown): Record<string, unknown> {
  const input = isRecord(params) ? { ...params } : {};

  if (toolName === "notion-search") {
    const queryType = getStringValue(input, "query_type");
    const isUserSearch = queryType === "user";

    if (!isUserSearch && !getStringValue(input, "content_search_mode")) {
      input.content_search_mode = "workspace_search";
    }
  }

  return input;
}

function createRegisteredToolExecutor(
  client: NotionMCPClient,
  mcpUrl: string,
  tool: MCPTool,
): (
  _toolCallId: string,
  params: unknown,
  _signal: AbortSignal,
  _onUpdate: unknown,
  _ctx: unknown,
) => Promise<ToolExecutionResult> {
  return async (_toolCallId, params, _signal, onUpdate) => {
    const update =
      typeof onUpdate === "function"
        ? (onUpdate as (payload: { content: Array<{ type: "text"; text: string }>; details?: Record<string, unknown> }) => void)
        : undefined;

    if (!client.state.connected) {
      return toolError(tool.name, "Not connected to Notion MCP. Run /notion to connect.", { tool: tool.name });
    }

    update?.({
      content: [{ type: "text", text: `Running ${tool.name}...` }],
      details: { tool: tool.name, phase: "running" },
    });

    try {
      const normalizedParams = applyToolDefaults(tool.name, params);
      const rawResult = await client.callToolRaw(
        mcpUrl,
        tool.name,
        normalizedParams,
      );
      const content = (rawResult as { content?: Array<{ type: string; text?: string }> })?.content;
      const result = content && Array.isArray(content)
        ? content.map((entry) => (entry.type === "text" ? entry.text : JSON.stringify(entry))).join("\n")
        : JSON.stringify(rawResult);
      return toolResult(tool.name, result || "", { tool: tool.name, rawResult });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return toolError(tool.name, `Error: ${message}`, { tool: tool.name, error: message });
    }
  };
}

function createRegisteredToolDefinition(client: NotionMCPClient, mcpUrl: string, tool: MCPTool) {
  const promptGuidelines =
    tool.name === "notion-search"
      ? [
          "Use notion-search with content_search_mode set to workspace_search unless the user explicitly asks for ai_search or connected-source search.",
        ]
      : undefined;

  return {
    name: tool.name,
    label: `Notion: ${tool.name.replace(/_/g, " ")}`,
    description: tool.description || `Notion MCP tool: ${tool.name}`,
    promptGuidelines,
    parameters: Type.Unsafe(tool.inputSchema),
    outputSchema: tool.outputSchema,
    execute: createRegisteredToolExecutor(client, mcpUrl, tool),
    ...createNotionToolRenderer(tool.name),
  };
}

interface OAuthConnectionData {
  tokens: OAuthTokenResult;
  registration: ClientRegistration;
}

function shouldClearSavedConfig(message: string): boolean {
  const normalized = message.toLowerCase();
  return (
    normalized.includes("invalid_token") ||
    normalized.includes("invalid_grant") ||
    normalized.includes("401") ||
    normalized.includes("cannot be refreshed") ||
    normalized.includes("unauthorized")
  );
}

async function connectWithSavedConfig(client: NotionMCPClient, notify?: NotifyFn): Promise<boolean> {
  const savedConfig = await storage.load();
  if (!savedConfig) return false;

  notify?.("Connecting to saved Notion MCP...");
  try {
    await client.connect(savedConfig.mcpUrl, savedConfig.accessToken, savedConfig);
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    notify?.(`Connection failed: ${message}`, "error");
    if (shouldClearSavedConfig(message)) {
      await storage.clear();
    }
    return false;
  }
}

async function performOAuthConnection(notify: NotifyFn): Promise<OAuthConnectionData> {
  const state = randomBytes(16).toString("hex");
  const callbackServer = await startOAuthCallbackServer(3000, state);
  const callbackUrl = `http://localhost:${callbackServer.port}/callback`;

  notify("Registering OAuth client...");
  const registration = await registerClient(callbackUrl);
  const { codeVerifier, codeChallenge } = createPkceChallenge();
  const authUrl = buildAuthorizationUrl(registration, callbackUrl, codeChallenge, state);

  notify("Opening Notion authorization page...");
  await openBrowser(authUrl);
  notify("Waiting for authorization callback...");

  const callbackResult = await callbackServer.result;
  const tokens = await resolveAccessToken(callbackResult, callbackUrl, codeVerifier, registration, notify);
  return { tokens, registration };
}

async function finalizeConnection(
  client: NotionMCPClient,
  registration: ClientRegistration | null,
  tokens: OAuthTokenResult,
  registerMCPTools: () => void,
  notify: NotifyFn,
): Promise<void> {
  const storedConfig: StoredConfig = {
    mcpUrl: NOTION_MCP_URL,
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken,
    tokenType: tokens.tokenType,
    expiresAt: tokens.expiresAt,
    clientId: registration?.client_id,
    clientSecret: registration?.client_secret,
  };

  notify("Connecting to MCP server...");
  await client.connect(NOTION_MCP_URL, storedConfig.accessToken, storedConfig);
  await storage.save(storedConfig);
  registerMCPTools();
}

async function ensureConnected(
  client: NotionMCPClient,
  registerMCPTools: () => void,
  notify: NotifyFn,
): Promise<{ reusedSavedConfig: boolean }> {
  const connectedFromSavedConfig = await connectWithSavedConfig(client, notify);
  if (connectedFromSavedConfig) {
    registerMCPTools();
    return { reusedSavedConfig: true };
  }

  const { tokens, registration } = await performOAuthConnection(notify);
  await finalizeConnection(client, registration, tokens, registerMCPTools, notify);
  return { reusedSavedConfig: false };
}

async function disconnectClient(client: NotionMCPClient): Promise<void> {
  await client.disconnect();
  await storage.clear();
}

export {
  buildAuthorizationUrl,
  buildHtmlResponse,
  coerceNumericProperties,
  coercePropertyMap,
  connectWithSavedConfig,
  createPkceChallenge,
  createNotionToolRenderer,
  createRegisteredToolDefinition,
  createRegisteredToolExecutor,
  createUiNotifier,
  disconnectClient,
  ensureConnected,
  FileTokenStorage,
  finalizeConnection,
  getConnectedStatusMessage,
  countOutputLines,
  getConnectionStatusText,
  getDefaultAuthFilePath,
  isNumericString,
  isRecord,
  NotionMCPClient,
  renderNotionToolCall,
  renderNotionToolResult,
  resolveAccessToken,
  resolveCallbackResult,
  applyToolDefaults,
  startOAuthCallbackServer,
  storage,
  toolError,
  toolResult,
  truncateDisplayText,
};

export default function notionMCPClientExtension(pi: ExtensionAPI) {
  pi.registerFlag("--notion-mcp-auth-file", {
    description: "Path to the persisted Notion MCP auth file.",
    type: "string",
  });
  pi.registerFlag("--notion-mcp-auth", {
    description: "Deprecated alias for --notion-mcp-auth-file.",
    type: "string",
  });

  const authFileFlag = pi.getFlag("--notion-mcp-auth-file");
  const legacyAuthFileFlag = pi.getFlag("--notion-mcp-auth");
  if (typeof authFileFlag === "string" && authFileFlag.trim().length > 0) {
    process.env.NOTION_MCP_AUTH_FILE = authFileFlag;
  } else if (typeof legacyAuthFileFlag === "string" && legacyAuthFileFlag.trim().length > 0) {
    console.warn("[pi-notion] --notion-mcp-auth is deprecated; use --notion-mcp-auth-file.");
    process.env.NOTION_MCP_AUTH_FILE = legacyAuthFileFlag;
  }

  mcpClient = new NotionMCPClient();
  const notify = createUiNotifier(pi);
  registerNotionGuardrails(pi);

  // Register dynamic MCP tools after connection
  const registerMCPTools = ({ notifyRegistration = true }: { notifyRegistration?: boolean } = {}) => {
    if (!mcpClient?.state.mcpUrl) return;

    const tools = mcpClient.getTools();
    const mcpUrl = mcpClient.state.mcpUrl;

    for (const tool of tools) {
      if (pi.getAllTools().find((t) => t.name === tool.name)) continue;

      pi.registerTool(createRegisteredToolDefinition(mcpClient, mcpUrl, tool));
    }

    if (notifyRegistration && tools.length > 0) {
      notify(`Registered ${tools.length} Notion MCP tools!`);
    }
  };

  pi.on("session_start", async () => {
    if (!mcpClient || mcpClient.state.connected) return;

    const connected = await connectWithSavedConfig(mcpClient);
    if (connected) {
      registerMCPTools({ notifyRegistration: false });
    }
  });

  // /notion command
  pi.registerCommand("notion", {
    description: "Connect to Notion MCP, show status, or disconnect",
    async handler(_args, ctx) {
      if (!mcpClient) {
        ctx.ui.notify("Notion MCP not initialized", "error");
        return;
      }

      if (!mcpClient.state.connected) {
        const uiNotify: NotifyFn = (message, type = "info") => ctx.ui.notify(message, type);
        try {
          await ensureConnected(mcpClient, registerMCPTools, uiNotify);
          ctx.ui.notify(`Connected! Session: ${mcpClient.state.sessionId?.slice(0, 8)}...`, "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          ctx.ui.notify(`Connection failed: ${message}`, "error");
        }
        return;
      }

      const choice = await ctx.ui.select(getConnectedStatusMessage(mcpClient), ["Disconnect", "Cancel"]);
      if (choice === "Disconnect") {
        await disconnectClient(mcpClient);
        ctx.ui.notify("Disconnected from Notion MCP", "info");
      }
    },
  });

  // Connect tool
  pi.registerTool({
    name: "notion_mcp_connect",
    label: "Notion MCP Connect",
    description: "Connect to Notion via the official MCP server using OAuth",
    parameters: Type.Object({}),
    ...createNotionToolRenderer("notion_mcp_connect"),
    async execute(_toolCallId, _params, _signal, _onUpdate, _ctx) {
      if (!mcpClient) {
        return toolError("notion_mcp_connect", "MCP client not initialized");
      }

      if (mcpClient.state.connected) {
        const tools = mcpClient.getTools();
        return toolResult(
          "notion_mcp_connect",
          `Already connected to Notion MCP!\n\n${tools.length} tools available: ${tools.map((t) => t.name).join(", ")}`,
          {
            connected: true,
            toolCount: tools.length,
            sessionId: mcpClient.state.sessionId,
            mcpUrl: mcpClient.state.mcpUrl,
          },
        );
      }

      try {
        await ensureConnected(mcpClient, registerMCPTools, notify);
        const tools = mcpClient.getTools();
        return toolResult(
          "notion_mcp_connect",
          `Connected to Notion MCP!\n\n${tools.length} tools available.\n\nYou can now ask things like:\n- "Search my Notion for meeting notes"\n- "Get page abc123"\n- "Create a page in my workspace"`,
          {
            connected: true,
            toolCount: tools.length,
            sessionId: mcpClient.state.sessionId,
            mcpUrl: mcpClient.state.mcpUrl,
          },
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return toolError("notion_mcp_connect", `Connection failed: ${message}`, { error: message });
      }
    },
  });

  // Disconnect tool
  pi.registerTool({
    name: "notion_mcp_disconnect",
    label: "Notion MCP Disconnect",
    description: "Disconnect from Notion MCP server and clear stored config",
    parameters: Type.Object({}),
    ...createNotionToolRenderer("notion_mcp_disconnect"),
    async execute(_toolCallId, _params, _signal, _onUpdate, _ctx) {
      if (!mcpClient) {
        return toolError("notion_mcp_disconnect", "MCP client not initialized");
      }

      await disconnectClient(mcpClient);
      return toolResult("notion_mcp_disconnect", "Disconnected from Notion MCP and cleared config", {
        connected: false,
      });
    },
  });

  // Status tool
  pi.registerTool({
    name: "notion_mcp_status",
    label: "Notion MCP Status",
    description: "Check connection status to Notion MCP",
    parameters: Type.Object({}),
    ...createNotionToolRenderer("notion_mcp_status"),
    async execute(_toolCallId, _params, _signal, _onUpdate, _ctx) {
      if (!mcpClient) {
        return toolError("notion_mcp_status", "MCP client not initialized");
      }

      const { connected, sessionId, mcpUrl } = mcpClient.state;
      return toolResult("notion_mcp_status", getConnectionStatusText(mcpClient), {
        connected,
        sessionId,
        mcpUrl,
        toolCount: mcpClient.getTools().length,
      });
    },
  });
}
