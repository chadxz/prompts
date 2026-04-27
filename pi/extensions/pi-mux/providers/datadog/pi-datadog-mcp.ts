/**
 * Datadog MCP Extension for pi
 *
 * Connects pi to Datadog's managed MCP server, discovers the available
 * tools after authentication, and keeps tool output compact in the TUI.
 *
 * Authentication supports both of Datadog's documented paths:
 * - OAuth 2.1 with PKCE and dynamic client registration
 * - API key + application key header auth
 */

import { execFile } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";

// =============================================================================
// Constants
// =============================================================================

const DATADOG_MCP_PATH = "/api/unstable/mcp-server/mcp";
const DEFAULT_SITE = "us3";
const DEFAULT_AUTH_FILE = "~/.pi/agent/datadog-mcp-auth.json";
const DEFAULT_REDIRECT_URI = "http://127.0.0.1:8563/oauth/callback";
const DEFAULT_TIMEOUT_MS = 300_000;
const TOKEN_REFRESH_WINDOW_MS = 60_000;
const MCP_PROTOCOL_VERSIONS = ["2025-03-26", "2024-11-05"] as const;

const DATADOG_MCP_AUTH_FILE_ENV = "DATADOG_MCP_AUTH_FILE";
const DATADOG_MCP_SITE_ENV = "DATADOG_MCP_SITE";
const DATADOG_MCP_URL_ENV = "DATADOG_MCP_URL";
const DATADOG_MCP_TOOLSETS_ENV = "DATADOG_MCP_TOOLSETS";
const DATADOG_MCP_REDIRECT_URI_ENV = "DATADOG_MCP_REDIRECT_URI";
const DD_SITE_ENV = "DD_SITE";
const DD_API_KEY_ENV = "DD_API_KEY";
const DD_APPLICATION_KEY_ENV = "DD_APPLICATION_KEY";

const SITE_TO_HOST: Record<string, string> = {
  us1: "mcp.datadoghq.com",
  us3: "mcp.us3.datadoghq.com",
  us5: "mcp.us5.datadoghq.com",
  eu: "mcp.datadoghq.eu",
  ap1: "mcp.ap1.datadoghq.com",
  ap2: "mcp.ap2.datadoghq.com",
  "us1-fed": "mcp.ddog-gov.com",
};

const DOMAIN_TO_SITE: Record<string, string> = {
  "datadoghq.com": "us1",
  "us3.datadoghq.com": "us3",
  "us5.datadoghq.com": "us5",
  "datadoghq.eu": "eu",
  "ap1.datadoghq.com": "ap1",
  "ap2.datadoghq.com": "ap2",
  "ddog-gov.com": "us1-fed",
};

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

type AuthMode = "oauth" | "headers";

interface MCPTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

interface RuntimeOverrides {
  site?: string;
  mcpUrl?: string;
  toolsets?: string[];
  redirectUri?: string;
  apiKey?: string;
  applicationKey?: string;
}

interface StoredConfig {
  authMode?: AuthMode;
  site?: string;
  mcpUrl?: string;
  toolsets?: string[];
  redirectUri?: string;
  apiKey?: string;
  applicationKey?: string;
  accessToken?: string;
  refreshToken?: string;
  expiresAt?: number;
  oauthClientId?: string;
  oauthClientSecret?: string;
  tokenEndpointAuthMethod?: "none" | "client_secret_post" | "client_secret_basic";
  authorizationServer?: string;
  authorizationEndpoint?: string;
  tokenEndpoint?: string;
  registrationEndpoint?: string;
  resource?: string;
}

interface EffectiveConfig {
  authMode: AuthMode;
  site: string;
  mcpUrl: string;
  toolsets: string[];
  redirectUri: string;
  apiKey?: string;
  applicationKey?: string;
  accessToken?: string;
  refreshToken?: string;
  expiresAt?: number;
  oauthClientId?: string;
  oauthClientSecret?: string;
  tokenEndpointAuthMethod?: "none" | "client_secret_post" | "client_secret_basic";
  authorizationServer?: string;
  authorizationEndpoint?: string;
  tokenEndpoint?: string;
  registrationEndpoint?: string;
  resource?: string;
}

interface MCPState {
  connected: boolean;
  authenticated: boolean;
  sessionId: string | null;
  mcpUrl: string;
  site: string | null;
  protocolVersion: string | null;
  serverName: string | null;
  serverVersion: string | null;
  toolsets: string[];
  authMode: AuthMode | null;
}

interface ProtectedResourceMetadata {
  resource: string;
  authorizationServers: string[];
}

interface AuthorizationServerMetadata {
  issuer: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  registrationEndpoint?: string;
  tokenEndpointAuthMethodsSupported: string[];
}

interface OAuthRegistration {
  clientId: string;
  clientSecret?: string;
  tokenEndpointAuthMethod: "none" | "client_secret_post" | "client_secret_basic";
}

interface OAuthTokenBundle {
  accessToken: string;
  refreshToken?: string;
  expiresAt: number;
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

interface AuthContext {
  resource: string;
  authorizationServer: string;
  metadata: AuthorizationServerMetadata;
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
// General utilities
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

function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
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

function buildPreviewLines(text: string, maxLines = 8): string[] {
  return text
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.trim().length > 0)
    .slice(0, maxLines)
    .map((line) => truncateDisplayText(line, 120));
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

function humanizeWords(value: string): string {
  return value.replace(/[_-]+/g, " ").trim();
}

function parseToolsets(value: unknown): string[] {
  if (!isNonEmptyString(value)) return [];
  return Array.from(
    new Set(
      value
        .split(",")
        .map((item) => item.trim().toLowerCase())
        .filter((item) => item.length > 0),
    ),
  );
}

function normalizeDatadogSite(value: string | undefined): string {
  const raw = (value ?? "").trim().toLowerCase();
  if (!raw) return DEFAULT_SITE;

  if (raw in SITE_TO_HOST) {
    return raw;
  }

  if (raw in DOMAIN_TO_SITE) {
    return DOMAIN_TO_SITE[raw] ?? DEFAULT_SITE;
  }

  if (raw === "us1_fed" || raw === "us1fed") {
    return "us1-fed";
  }

  throw new Error(
    `Unsupported Datadog site '${value}'. Use one of: ${Object.keys(SITE_TO_HOST).join(", ")}.`,
  );
}

function buildDatadogMcpUrl(site: string, mcpUrl: string | undefined, toolsets: string[]): string {
  const resolved = isNonEmptyString(mcpUrl)
    ? new URL(mcpUrl.trim())
    : new URL(`https://${SITE_TO_HOST[normalizeDatadogSite(site)] ?? SITE_TO_HOST[DEFAULT_SITE]}${DATADOG_MCP_PATH}`);

  if (toolsets.length > 0) {
    resolved.searchParams.set("toolsets", toolsets.join(","));
  } else {
    resolved.searchParams.delete("toolsets");
  }

  return resolved.toString();
}

function createUiNotifier(ctx: ExtensionContext): NotifyFn {
  return (message, type = "info") => {
    ctx.ui.notify(message, type);
  };
}

function openBrowser(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    let command: string;
    let args: string[];

    switch (process.platform) {
      case "darwin":
        command = "open";
        args = [url];
        break;
      case "win32":
        command = "cmd";
        args = ["/c", "start", "", url];
        break;
      default:
        command = "xdg-open";
        args = [url];
        break;
    }

    execFile(command, args, (error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
}

// =============================================================================
// OAuth helpers
// =============================================================================

function normalizeRedirectUri(redirectUri: string): URL {
  const parsed = new URL(redirectUri);
  if (parsed.protocol !== "http:") {
    throw new Error("Datadog MCP redirect URI must use http:// and point to localhost or 127.0.0.1.");
  }
  if (!(parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost")) {
    throw new Error("Datadog MCP redirect URI must use localhost or 127.0.0.1.");
  }
  if (!parsed.port) {
    throw new Error("Datadog MCP redirect URI must include an explicit port.");
  }
  return parsed;
}

function assertHttpsUrl(value: string, label: string): string {
  const parsed = new URL(value);
  if (parsed.protocol !== "https:") {
    throw new Error(`Datadog ${label} must use https.`);
  }
  return parsed.toString();
}

function buildSavedAuthContext(config: EffectiveConfig): AuthContext | null {
  if (!(config.authorizationServer && config.authorizationEndpoint && config.tokenEndpoint)) {
    return null;
  }

  const authorizationServer = assertHttpsUrl(config.authorizationServer, "authorization server URL");
  const registrationEndpoint = isNonEmptyString(config.registrationEndpoint)
    ? assertHttpsUrl(config.registrationEndpoint, "registration endpoint")
    : undefined;

  return {
    resource: config.resource ?? new URL(config.mcpUrl).origin,
    authorizationServer,
    metadata: {
      issuer: authorizationServer,
      authorizationEndpoint: assertHttpsUrl(config.authorizationEndpoint, "authorization endpoint"),
      tokenEndpoint: assertHttpsUrl(config.tokenEndpoint, "token endpoint"),
      registrationEndpoint,
      tokenEndpointAuthMethodsSupported: config.tokenEndpointAuthMethod ? [config.tokenEndpointAuthMethod] : [],
    },
  };
}

function createPkceChallenge(): { codeVerifier: string; codeChallenge: string } {
  const codeVerifier = randomBytes(32).toString("base64url");
  const codeChallenge = createHash("sha256").update(codeVerifier).digest("base64url");
  return { codeVerifier, codeChallenge };
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
      response: {
        statusCode: 400,
        body: "<html><body><h1>State mismatch</h1><p>Please try again.</p></body></html>",
      },
      result: { error: "State mismatch" },
    };
  }

  const error = params.get("error");
  if (error) {
    return {
      response: {
        statusCode: 400,
        body: `<html><body><h1>Authorization failed</h1><p>Error: ${error}</p><p>${params.get("error_description") ?? ""}</p></body></html>`,
      },
      result: {
        error,
        errorDescription: params.get("error_description") ?? undefined,
      },
    };
  }

  const code = params.get("code");
  if (!code) {
    return {
      response: {
        statusCode: 400,
        body: "<html><body><h1>Authorization failed</h1><p>No code in callback.</p></body></html>",
      },
      result: { error: "No authorization code received" },
    };
  }

  return {
    response: {
      statusCode: 200,
      body: "<html><body><h1>Authorized!</h1><p>You can close this window.</p><script>window.close();</script></body></html>",
    },
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
      reject(new Error("Datadog OAuth callback timed out after 5 minutes."));
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

async function fetchJson(url: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return (await response.json()) as unknown;
}

async function fetchProtectedResourceMetadata(mcpUrl: string): Promise<ProtectedResourceMetadata> {
  const origin = new URL(mcpUrl).origin;
  const metadataUrl = new URL("/.well-known/oauth-protected-resource", origin).toString();
  const json = await fetchJson(metadataUrl);
  if (!isRecord(json)) {
    throw new Error("Datadog protected resource metadata response was not an object.");
  }

  const authorizationServers = Array.isArray(json.authorization_servers)
    ? json.authorization_servers
        .filter((value): value is string => isNonEmptyString(value))
        .map((value) => assertHttpsUrl(value, "authorization server URL"))
    : [];
  const resource = getStringValue(json, "resource") ?? origin;

  return {
    resource,
    authorizationServers,
  };
}

async function fetchAuthorizationServerMetadata(authorizationServer: string): Promise<AuthorizationServerMetadata> {
  const normalizedAuthorizationServer = assertHttpsUrl(authorizationServer, "authorization server URL");
  const metadataUrl = new URL("/.well-known/oauth-authorization-server", normalizedAuthorizationServer).toString();
  const json = await fetchJson(metadataUrl);
  if (!isRecord(json)) {
    throw new Error("Datadog authorization server metadata response was not an object.");
  }

  const issuer = getStringValue(json, "issuer") ?? normalizedAuthorizationServer;
  const authorizationEndpoint = getStringValue(json, "authorization_endpoint");
  const tokenEndpoint = getStringValue(json, "token_endpoint");
  if (!authorizationEndpoint || !tokenEndpoint) {
    throw new Error("Datadog authorization server metadata is missing required endpoints.");
  }

  const tokenEndpointAuthMethodsSupported = Array.isArray(json.token_endpoint_auth_methods_supported)
    ? json.token_endpoint_auth_methods_supported.filter((value): value is string => isNonEmptyString(value))
    : [];
  const registrationEndpoint = getStringValue(json, "registration_endpoint");

  return {
    issuer,
    authorizationEndpoint: assertHttpsUrl(authorizationEndpoint, "authorization endpoint"),
    tokenEndpoint: assertHttpsUrl(tokenEndpoint, "token endpoint"),
    registrationEndpoint: isNonEmptyString(registrationEndpoint)
      ? assertHttpsUrl(registrationEndpoint, "registration endpoint")
      : undefined,
    tokenEndpointAuthMethodsSupported,
  };
}

async function discoverAuthContext(config: EffectiveConfig): Promise<AuthContext> {
  const protectedMetadata = await fetchProtectedResourceMetadata(config.mcpUrl);
  const authorizationServer =
    protectedMetadata.authorizationServers[0] ?? config.authorizationServer ?? new URL(config.mcpUrl).origin;
  const metadata = await fetchAuthorizationServerMetadata(authorizationServer);

  return {
    resource: protectedMetadata.resource,
    authorizationServer,
    metadata,
  };
}

function pickTokenEndpointAuthMethod(
  supported: string[],
): "none" | "client_secret_post" | "client_secret_basic" {
  if (supported.includes("client_secret_post")) return "client_secret_post";
  if (supported.includes("none")) return "none";
  if (supported.includes("client_secret_basic")) return "client_secret_basic";
  return "none";
}

async function registerOAuthClient(
  metadata: AuthorizationServerMetadata,
  redirectUri: string,
): Promise<OAuthRegistration> {
  if (!isNonEmptyString(metadata.registrationEndpoint)) {
    throw new Error("Datadog MCP authorization server does not expose a registration endpoint.");
  }

  const tokenEndpointAuthMethod = pickTokenEndpointAuthMethod(metadata.tokenEndpointAuthMethodsSupported);
  const json = await fetchJson(metadata.registrationEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_name: "pi-datadog-mcp",
      redirect_uris: [redirectUri],
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
      token_endpoint_auth_method: tokenEndpointAuthMethod,
    }),
  });

  if (!isRecord(json)) {
    throw new Error("Datadog MCP client registration response was not an object.");
  }

  const clientId = getStringValue(json, "client_id");
  if (!clientId) {
    throw new Error("Datadog MCP client registration did not return a client_id.");
  }

  return {
    clientId,
    clientSecret: getStringValue(json, "client_secret"),
    tokenEndpointAuthMethod,
  };
}

function buildAuthorizationUrl(
  authorizationEndpoint: string,
  clientId: string,
  redirectUri: string,
  codeChallenge: string,
  state: string,
  resource: string,
): string {
  const authUrl = new URL(authorizationEndpoint);
  authUrl.searchParams.set("client_id", clientId);
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("code_challenge", codeChallenge);
  authUrl.searchParams.set("code_challenge_method", "S256");
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("resource", resource);
  return authUrl.toString();
}

function buildTokenRequestBody(
  grantType: "authorization_code" | "refresh_token",
  registration: OAuthRegistration,
  redirectUri: string | undefined,
  resource: string,
  extras: Record<string, string>,
): URLSearchParams {
  const params = new URLSearchParams({
    grant_type: grantType,
    client_id: registration.clientId,
    resource,
    ...extras,
  });

  if (grantType === "authorization_code" && isNonEmptyString(redirectUri)) {
    params.set("redirect_uri", redirectUri);
  }

  if (
    registration.tokenEndpointAuthMethod === "client_secret_post" &&
    isNonEmptyString(registration.clientSecret)
  ) {
    params.set("client_secret", registration.clientSecret);
  }

  return params;
}

function buildTokenRequestHeaders(registration: OAuthRegistration): Headers {
  const headers = new Headers({
    "Content-Type": "application/x-www-form-urlencoded",
    Accept: "application/json",
  });

  if (
    registration.tokenEndpointAuthMethod === "client_secret_basic" &&
    isNonEmptyString(registration.clientSecret)
  ) {
    headers.set(
      "Authorization",
      `Basic ${Buffer.from(`${registration.clientId}:${registration.clientSecret}`).toString("base64")}`,
    );
  }

  return headers;
}

async function parseOAuthTokenResponse(response: Response, existingRefreshToken?: string): Promise<OAuthTokenBundle> {
  const payload = (await response.json()) as unknown;
  if (!response.ok || !isRecord(payload)) {
    const message = isRecord(payload) ? getStringValue(payload, "error", "message") : response.statusText;
    throw new Error(`Datadog token request failed: ${message ?? response.statusText}`);
  }

  const accessToken = getStringValue(payload, "access_token");
  if (!accessToken) {
    throw new Error("Datadog token response did not include an access token.");
  }

  const expiresIn = getNumberValue(payload, "expires_in") ?? 3600;
  return {
    accessToken,
    refreshToken: getStringValue(payload, "refresh_token") ?? existingRefreshToken,
    expiresAt: Date.now() + expiresIn * 1000 - TOKEN_REFRESH_WINDOW_MS,
  };
}

async function exchangeCodeForTokens(
  tokenEndpoint: string,
  registration: OAuthRegistration,
  redirectUri: string,
  code: string,
  codeVerifier: string,
  resource: string,
): Promise<OAuthTokenBundle> {
  const body = buildTokenRequestBody("authorization_code", registration, redirectUri, resource, {
    code,
    code_verifier: codeVerifier,
  });

  const response = await fetch(tokenEndpoint, {
    method: "POST",
    headers: buildTokenRequestHeaders(registration),
    body: body.toString(),
  });

  return await parseOAuthTokenResponse(response);
}

async function refreshOAuthTokens(
  tokenEndpoint: string,
  registration: OAuthRegistration,
  refreshToken: string,
  resource: string,
): Promise<OAuthTokenBundle> {
  const body = buildTokenRequestBody("refresh_token", registration, undefined, resource, {
    refresh_token: refreshToken,
  });

  const response = await fetch(tokenEndpoint, {
    method: "POST",
    headers: buildTokenRequestHeaders(registration),
    body: body.toString(),
  });

  return await parseOAuthTokenResponse(response, refreshToken);
}

// =============================================================================
// Config storage and auth state
// =============================================================================

function getDefaultAuthFilePath(): string {
  const configuredPath = process.env[DATADOG_MCP_AUTH_FILE_ENV];
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
    const parent = dirname(path);
    mkdirSync(parent, { recursive: true, mode: 0o700 });
    try {
      chmodSync(parent, 0o700);
    } catch {
      // Ignore chmod errors on existing directories.
    }
    writeFileSync(path, JSON.stringify(config, null, 2), {
      encoding: "utf-8",
      mode: 0o600,
    });
    try {
      chmodSync(path, 0o600);
    } catch {
      // Ignore chmod errors after write.
    }
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
    ...(isNonEmptyString(overrides.site) ? { site: overrides.site } : {}),
    ...(isNonEmptyString(overrides.mcpUrl) ? { mcpUrl: overrides.mcpUrl } : {}),
    ...(overrides.toolsets ? { toolsets: overrides.toolsets } : {}),
    ...(isNonEmptyString(overrides.redirectUri) ? { redirectUri: overrides.redirectUri } : {}),
    ...(isNonEmptyString(overrides.apiKey) ? { apiKey: overrides.apiKey } : {}),
    ...(isNonEmptyString(overrides.applicationKey) ? { applicationKey: overrides.applicationKey } : {}),
  };
}

function mergePersistableRuntimeOverrides(config: StoredConfig | null, overrides: RuntimeOverrides): StoredConfig {
  return {
    ...config,
    ...(isNonEmptyString(overrides.site) ? { site: overrides.site } : {}),
    ...(isNonEmptyString(overrides.mcpUrl) ? { mcpUrl: overrides.mcpUrl } : {}),
    ...(overrides.toolsets ? { toolsets: overrides.toolsets } : {}),
    ...(isNonEmptyString(overrides.redirectUri) ? { redirectUri: overrides.redirectUri } : {}),
  };
}

function normalizeDdSiteEnv(value: string | undefined): string | undefined {
  if (!isNonEmptyString(value)) return undefined;
  return normalizeDatadogSite(value.trim());
}

function getRuntimeOverrides(pi: ExtensionAPI): RuntimeOverrides {
  const authFileFlag = pi.getFlag("--datadog-mcp-auth-file");
  if (isNonEmptyString(authFileFlag)) {
    process.env[DATADOG_MCP_AUTH_FILE_ENV] = authFileFlag;
  }

  const siteFlag = pi.getFlag("--datadog-mcp-site");
  const urlFlag = pi.getFlag("--datadog-mcp-url");
  const toolsetsFlag = pi.getFlag("--datadog-mcp-toolsets");
  const redirectUriFlag = pi.getFlag("--datadog-mcp-redirect-uri");
  const apiKeyFlag = pi.getFlag("--datadog-api-key");
  const applicationKeyFlag = pi.getFlag("--datadog-application-key");

  return {
    site: isNonEmptyString(siteFlag)
      ? normalizeDatadogSite(siteFlag.trim())
      : normalizeDdSiteEnv(process.env[DATADOG_MCP_SITE_ENV]) ?? normalizeDdSiteEnv(process.env[DD_SITE_ENV]),
    mcpUrl: isNonEmptyString(urlFlag) ? urlFlag.trim() : process.env[DATADOG_MCP_URL_ENV],
    toolsets: isNonEmptyString(toolsetsFlag)
      ? parseToolsets(toolsetsFlag)
      : parseToolsets(process.env[DATADOG_MCP_TOOLSETS_ENV]),
    redirectUri: isNonEmptyString(redirectUriFlag)
      ? redirectUriFlag.trim()
      : process.env[DATADOG_MCP_REDIRECT_URI_ENV],
    apiKey: isNonEmptyString(apiKeyFlag) ? apiKeyFlag.trim() : process.env[DD_API_KEY_ENV],
    applicationKey: isNonEmptyString(applicationKeyFlag)
      ? applicationKeyFlag.trim()
      : process.env[DD_APPLICATION_KEY_ENV],
  };
}

function resolveAuthMode(config: StoredConfig): AuthMode {
  if (config.authMode) return config.authMode;
  if (isNonEmptyString(config.apiKey) && isNonEmptyString(config.applicationKey)) {
    return "headers";
  }
  return "oauth";
}

function getEffectiveConfig(config: StoredConfig | null, overrides: RuntimeOverrides): EffectiveConfig {
  const merged = mergeRuntimeOverrides(config, overrides);
  const site = normalizeDatadogSite(merged.site);
  const toolsets = Array.isArray(merged.toolsets) ? merged.toolsets : [];

  return {
    authMode: resolveAuthMode(merged),
    site,
    toolsets,
    mcpUrl: buildDatadogMcpUrl(site, merged.mcpUrl, toolsets),
    redirectUri: merged.redirectUri ?? DEFAULT_REDIRECT_URI,
    apiKey: merged.apiKey,
    applicationKey: merged.applicationKey,
    accessToken: merged.accessToken,
    refreshToken: merged.refreshToken,
    expiresAt: merged.expiresAt,
    oauthClientId: merged.oauthClientId,
    oauthClientSecret: merged.oauthClientSecret,
    tokenEndpointAuthMethod: merged.tokenEndpointAuthMethod,
    authorizationServer: merged.authorizationServer,
    authorizationEndpoint: merged.authorizationEndpoint,
    tokenEndpoint: merged.tokenEndpoint,
    registrationEndpoint: merged.registrationEndpoint,
    resource: merged.resource,
  };
}

function hasHeaderCredentials(config: EffectiveConfig): boolean {
  return isNonEmptyString(config.apiKey) && isNonEmptyString(config.applicationKey);
}

function hasStoredOAuthCredentials(config: EffectiveConfig): boolean {
  return isNonEmptyString(config.oauthClientId) && isNonEmptyString(config.refreshToken);
}

function hasUsableOAuthAccess(config: EffectiveConfig): boolean {
  return config.authMode === "oauth" && isNonEmptyString(config.accessToken);
}

function shouldRefreshOAuthToken(config: EffectiveConfig): boolean {
  return (
    config.authMode === "oauth" &&
    hasStoredOAuthCredentials(config) &&
    (!isNonEmptyString(config.accessToken) ||
      typeof config.expiresAt !== "number" ||
      Date.now() >= config.expiresAt - TOKEN_REFRESH_WINDOW_MS)
  );
}

function hasUsableAuth(config: EffectiveConfig): boolean {
  if (config.authMode === "headers") {
    return hasHeaderCredentials(config);
  }
  return hasUsableOAuthAccess(config) || hasStoredOAuthCredentials(config);
}

function buildDisconnectedMessage(config: EffectiveConfig): string {
  const toolsets = config.toolsets.length > 0 ? config.toolsets.join(",") : "core (server default)";
  return [
    "Datadog MCP Status:",
    "- Connected: No",
    `- Auth mode: ${config.authMode}`,
    `- Site: ${config.site}`,
    `- URL: ${config.mcpUrl}`,
    `- Toolsets: ${toolsets}`,
    `- OAuth configured: ${hasStoredOAuthCredentials(config) || hasUsableOAuthAccess(config) ? "Yes" : "No"}`,
    `- API key configured: ${isNonEmptyString(config.apiKey) ? "Yes" : "No"}`,
    `- Application key configured: ${isNonEmptyString(config.applicationKey) ? "Yes" : "No"}`,
    "",
    "Run /datadog-mcp or use datadog_mcp_connect to connect.",
  ].join("\n");
}

// =============================================================================
// MCP transport
// =============================================================================

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
          // Ignore malformed payloads.
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

  throw new Error("No JSON-RPC response found in Datadog MCP SSE stream.");
}

class DatadogMCPClient {
  state: MCPState = {
    connected: false,
    authenticated: false,
    sessionId: null,
    mcpUrl: "",
    site: DEFAULT_SITE,
    protocolVersion: null,
    serverName: null,
    serverVersion: null,
    toolsets: [],
    authMode: null,
  };

  private messageId = 0;
  private sessionId: string | null = null;
  private tools: MCPTool[] = [];
  private readonly getConfig: () => EffectiveConfig;
  private readonly refreshOAuthAccessToken?: () => Promise<boolean>;

  constructor(getConfig: () => EffectiveConfig, refreshOAuthAccessToken?: () => Promise<boolean>) {
    this.getConfig = getConfig;
    this.refreshOAuthAccessToken = refreshOAuthAccessToken;
  }

  async connect(): Promise<void> {
    let config = this.getConfig();

    if (shouldRefreshOAuthToken(config) && this.refreshOAuthAccessToken) {
      await this.refreshOAuthAccessToken();
      config = this.getConfig();
    }

    if (!hasUsableAuth(config)) {
      throw new Error("Datadog MCP credentials are not configured. Run /datadog-mcp or datadog_mcp_connect.");
    }

    this.state.authenticated = true;
    this.state.mcpUrl = config.mcpUrl;
    this.state.site = config.site;
    this.state.toolsets = config.toolsets;
    this.state.authMode = config.authMode;

    let initializeResult: Record<string, unknown> | null = null;
    let lastError: Error | undefined;

    for (const protocolVersion of MCP_PROTOCOL_VERSIONS) {
      try {
        initializeResult = (await this.sendRequest(
          "initialize",
          {
            protocolVersion,
            capabilities: {},
            clientInfo: { name: "pi-datadog-mcp", version: "1.0.0" },
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
      throw lastError ?? new Error("Datadog MCP initialization failed.");
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
          headers: this.getHeaders(this.state.protocolVersion ?? undefined),
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
      protocolVersion: null,
      serverName: null,
      serverVersion: null,
      authMode: null,
    };
  }

  getTools(): MCPTool[] {
    return this.tools;
  }

  async callToolRaw(name: string, args: Record<string, unknown>): Promise<unknown> {
    return await this.sendRequest("tools/call", {
      name,
      arguments: args,
    });
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    return normalizeMcpToolResult(await this.callToolRaw(name, args));
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
        outputSchema: isRecord(tool.outputSchema) ? tool.outputSchema : undefined,
      }));
  }

  private async sendNotification(method: string, params: Record<string, unknown>): Promise<void> {
    const response = await fetch(this.state.mcpUrl, {
      method: "POST",
      headers: this.getHeaders(this.state.protocolVersion ?? undefined),
      body: JSON.stringify({ jsonrpc: "2.0", method, params }),
    });

    if (response.status === 401 && this.refreshOAuthAccessToken) {
      const refreshed = await this.refreshOAuthAccessToken();
      if (refreshed) {
        await response.body?.cancel();
        await fetch(this.state.mcpUrl, {
          method: "POST",
          headers: this.getHeaders(this.state.protocolVersion ?? undefined),
          body: JSON.stringify({ jsonrpc: "2.0", method, params }),
        });
        return;
      }
    }

    await response.body?.cancel();
  }

  private async sendRequest(
    method: string,
    params: Record<string, unknown>,
    protocolVersion?: string,
    allowRefreshRetry = true,
  ): Promise<unknown> {
    const requestId = ++this.messageId;
    const response = await fetch(this.state.mcpUrl, {
      method: "POST",
      headers: this.getHeaders(protocolVersion),
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: requestId,
        method,
        params,
      }),
    });

    if (response.status === 401 && allowRefreshRetry && this.refreshOAuthAccessToken) {
      const refreshed = await this.refreshOAuthAccessToken();
      if (refreshed) {
        await response.body?.cancel();
        return await this.sendRequest(method, params, protocolVersion, false);
      }
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
      throw new Error("Datadog MCP returned a non-JSON response.");
    }
    if (isRecord(json.error)) {
      throw new Error(getStringValue(json.error, "message") ?? "Datadog MCP request failed.");
    }

    return json.result;
  }

  private getHeaders(protocolVersion?: string): Headers {
    const config = this.getConfig();
    const headers = new Headers({
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    });

    if (config.authMode === "oauth" && isNonEmptyString(config.accessToken)) {
      headers.set("Authorization", `Bearer ${config.accessToken}`);
    } else if (config.authMode === "headers") {
      if (isNonEmptyString(config.apiKey)) {
        headers.set("DD-API-KEY", config.apiKey);
      }
      if (isNonEmptyString(config.applicationKey)) {
        headers.set("DD-APPLICATION-KEY", config.applicationKey);
      }
    }

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

// =============================================================================
// TUI rendering
// =============================================================================

function buildDatadogCallSummary(toolName: string, args: unknown): { primary?: string; meta: string[] } {
  const input = isRecord(args) ? args : {};
  const meta: string[] = [];

  const query = getStringValue(input, "query", "q", "search", "raw_query");
  const target = getStringValue(
    input,
    "id",
    "dashboard_id",
    "monitor_id",
    "incident_id",
    "notebook_id",
    "trace_id",
    "workflow_id",
    "case_id",
    "flag_key",
    "service",
    "name",
    "title",
  );
  const limit = getNumberValue(input, "limit", "page_size", "max_results", "count", "max_tokens");
  const toolsets = getStringValue(input, "toolsets");
  const from = getStringValue(input, "from", "from_ts", "start", "start_time");
  const to = getStringValue(input, "to", "to_ts", "end", "end_time");
  const itemCount = getArrayLength(input, "ids", "widgets", "items", "services", "metrics");

  if (typeof limit === "number") meta.push(`limit=${limit}`);
  if (toolsets) meta.push(`toolsets=${truncateDisplayText(toolsets, 36)}`);
  if (from && to) meta.push(`${truncateDisplayText(from, 18)}..${truncateDisplayText(to, 18)}`);
  if (typeof itemCount === "number") meta.push(`items=${itemCount}`);

  const lower = toolName.toLowerCase();
  if (toolName.startsWith("datadog_mcp_")) {
    return { primary: target ?? query, meta };
  }
  if (lower.includes("search") || lower.includes("list") || lower.includes("analyze")) {
    return { primary: query ?? target, meta };
  }
  if (lower.includes("get") || lower.includes("fetch")) {
    return { primary: target ?? query, meta };
  }
  if (lower.includes("create") || lower.includes("update") || lower.includes("delete") || lower.includes("execute")) {
    return { primary: target ?? query, meta };
  }

  return {
    primary: target ?? query ?? getStringValue(input, "url", "resource", "kind"),
    meta,
  };
}

function getDatadogPendingLabel(toolName: string): string {
  const lower = toolName.toLowerCase();
  if (toolName === "datadog_mcp_connect") return "Connecting to Datadog MCP...";
  if (toolName === "datadog_mcp_disconnect") return "Disconnecting from Datadog MCP...";
  if (toolName === "datadog_mcp_status") return "Checking Datadog MCP status...";
  if (lower.includes("search") || lower.includes("list")) return "Searching Datadog...";
  if (lower.includes("analyze")) return "Analyzing Datadog data...";
  if (lower.includes("create") || lower.includes("update") || lower.includes("delete")) {
    return "Updating Datadog resources...";
  }
  if (lower.includes("get") || lower.includes("fetch")) return "Fetching Datadog data...";
  return "Working with Datadog...";
}

function getDatadogSuccessLabel(toolName: string, details: Record<string, unknown>): string {
  if (toolName === "datadog_mcp_connect") {
    const toolCount = typeof details.toolCount === "number" ? details.toolCount : undefined;
    return typeof toolCount === "number"
      ? `Connected (${toolCount} tool${toolCount === 1 ? "" : "s"})`
      : "Connected";
  }
  if (toolName === "datadog_mcp_disconnect") return "Disconnected";
  if (toolName === "datadog_mcp_status") {
    return details.connected === true ? "Connected" : "Not connected";
  }

  const lower = toolName.toLowerCase();
  if (lower.includes("search") || lower.includes("list")) return "Search complete";
  if (lower.includes("analyze")) return "Analysis complete";
  if (lower.includes("get") || lower.includes("fetch")) return "Content fetched";
  if (lower.includes("create")) return "Created";
  if (lower.includes("update") || lower.includes("edit")) return "Updated";
  if (lower.includes("delete")) return "Deleted";
  if (lower.includes("execute")) return "Executed";
  return "Completed";
}

function buildDatadogExpandedMeta(toolName: string, args: unknown, details: Record<string, unknown>): string[] {
  const summary = buildDatadogCallSummary(toolName, args);
  const meta: string[] = [];

  if (summary.primary) {
    meta.push(`target: ${truncateDisplayText(summary.primary, 120)}`);
  }
  for (const item of summary.meta) {
    meta.push(item.replace("=", ": "));
  }

  if (toolName.startsWith("datadog_mcp_")) {
    if (typeof details.authMode === "string" && details.authMode.trim().length > 0) {
      meta.push(`auth: ${details.authMode}`);
    }
    if (typeof details.site === "string" && details.site.trim().length > 0) {
      meta.push(`site: ${details.site}`);
    }
    if (typeof details.mcpUrl === "string" && details.mcpUrl.trim().length > 0) {
      meta.push(`url: ${truncateDisplayText(details.mcpUrl, 120)}`);
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

function renderDatadogToolCall(toolName: string, args: unknown, theme: RenderTheme) {
  const summary = buildDatadogCallSummary(toolName, args);
  let text = theme.fg("toolTitle", theme.bold(toolName));
  if (summary.primary) {
    text += ` ${theme.fg("accent", truncateDisplayText(summary.primary))}`;
  }
  if (summary.meta.length > 0) {
    text += theme.fg("dim", ` (${summary.meta.join(", ")})`);
  }
  return new Text(text, 0, 0);
}

function renderDatadogToolResult(
  toolName: string,
  args: unknown,
  result: ToolExecutionResult,
  options: ToolRenderOptions,
  theme: RenderTheme,
  context: ToolRenderContext,
) {
  if (options.isPartial) {
    return new Text(theme.fg("warning", getDatadogPendingLabel(toolName)), 0, 0);
  }

  const details = result.details ?? {};
  const textContent = getTextContent(result.content);

  if (context.isError) {
    const errorText = truncateDisplayText(textContent || "Datadog MCP request failed", 140);
    return new Text(theme.fg("error", errorText), 0, 0);
  }

  const lineCount = typeof details.lineCount === "number" ? details.lineCount : countOutputLines(textContent);
  const characterCount = typeof details.characterCount === "number" ? details.characterCount : textContent.length;
  let text = theme.fg(
    "success",
    `${getDatadogSuccessLabel(toolName, details)}${formatOutputStats(lineCount, characterCount)}`,
  );

  if (options.expanded) {
    const metaLines = buildDatadogExpandedMeta(toolName, args, details);
    for (const line of metaLines) {
      text += `\n${theme.fg("dim", line)}`;
    }

    const previewLines = buildPreviewLines(textContent);
    if (previewLines.length > 0) {
      text += `\n${theme.fg("muted", "preview:")}`;
      for (const line of previewLines) {
        text += `\n${theme.fg("dim", line)}`;
      }
    }
  }

  return new Text(text, 0, 0);
}

function createDatadogToolRenderer(toolName: string) {
  return {
    renderCall(args: unknown, theme: RenderTheme) {
      return renderDatadogToolCall(toolName, args, theme);
    },
    renderResult(
      result: ToolExecutionResult,
      options: ToolRenderOptions,
      theme: RenderTheme,
      context: ToolRenderContext,
    ) {
      return renderDatadogToolResult(toolName, context.args, result, options, theme, context);
    },
  };
}

// =============================================================================
// Tool result helpers
// =============================================================================

function toolResult(toolName: string, text: string, details: Record<string, unknown> = {}): ToolExecutionResult {
  return {
    content: [{ type: "text", text }],
    details: {
      tool: toolName,
      lineCount: countOutputLines(text),
      characterCount: text.length,
      ...details,
    },
  };
}

function toolError(toolName: string, text: string, details: Record<string, unknown> = {}): ToolExecutionResult {
  return {
    content: [{ type: "text", text }],
    isError: true,
    details: {
      tool: toolName,
      ...details,
    },
  };
}

// =============================================================================
// Extension wiring
// =============================================================================

const storage = new FileConfigStorage();
let persistedConfig: StoredConfig | null = null;
let runtimeOverrides: RuntimeOverrides = {};
let mcpClient: DatadogMCPClient | null = null;
let registeredToolNames = new Set<string>();

async function savePersistedConfig(config: StoredConfig): Promise<void> {
  persistedConfig = config;
  await storage.save(config);
}

async function clearPersistedConfig(): Promise<void> {
  persistedConfig = null;
  await storage.clear();
}

function getCurrentConfig(): EffectiveConfig {
  return getEffectiveConfig(persistedConfig, runtimeOverrides);
}

function buildPersistedConfigBase(overrides: Partial<StoredConfig> = {}): StoredConfig {
  const current = getCurrentConfig();
  const merged = mergePersistableRuntimeOverrides(persistedConfig, runtimeOverrides);

  return {
    ...merged,
    site: merged.site ?? current.site,
    mcpUrl: merged.mcpUrl,
    toolsets: merged.toolsets ?? current.toolsets,
    redirectUri: merged.redirectUri ?? current.redirectUri,
    ...overrides,
  };
}

async function updatePersistedConfig(overrides: Partial<StoredConfig>): Promise<void> {
  await savePersistedConfig(buildPersistedConfigBase(overrides));
}

async function saveHeaderCredentials(apiKey: string, applicationKey: string): Promise<void> {
  await updatePersistedConfig({
    authMode: "headers",
    apiKey: apiKey.trim(),
    applicationKey: applicationKey.trim(),
  });
}

async function ensureHeaderCredentialsConfigured(ctx: ExtensionContext): Promise<boolean> {
  const config = getCurrentConfig();
  if (hasHeaderCredentials(config)) {
    return true;
  }

  const apiKey = await ctx.ui.input("Datadog API key", "dd_api_key...");
  if (!isNonEmptyString(apiKey)) {
    ctx.ui.notify("Datadog MCP header-auth setup cancelled.", "warning");
    return false;
  }

  const applicationKey = await ctx.ui.input("Datadog application key", "dd_application_key...");
  if (!isNonEmptyString(applicationKey)) {
    ctx.ui.notify("Datadog MCP header-auth setup cancelled.", "warning");
    return false;
  }

  await saveHeaderCredentials(apiKey, applicationKey);
  return true;
}

function getConnectionSummaryText(client: DatadogMCPClient | null): string {
  const config = getCurrentConfig();
  if (!client?.state.connected) {
    return buildDisconnectedMessage(config);
  }

  const toolsets = client.state.toolsets.length > 0 ? client.state.toolsets.join(",") : "core (server default)";
  return [
    "Datadog MCP Status:",
    "- Connected: Yes",
    `- Auth mode: ${client.state.authMode ?? config.authMode}`,
    `- Site: ${client.state.site ?? config.site}`,
    `- URL: ${client.state.mcpUrl}`,
    `- Toolsets: ${toolsets}`,
    `- Session: ${client.state.sessionId ?? "None"}`,
    `- Server: ${client.state.serverName ?? "unknown"}${client.state.serverVersion ? ` ${client.state.serverVersion}` : ""}`,
    `- Tools: ${client.getTools().length}`,
  ].join("\n");
}

function buildConnectedStatusMessage(client: DatadogMCPClient): string {
  return [
    "Connected to Datadog MCP",
    `Auth: ${client.state.authMode ?? "unknown"}`,
    `Site: ${client.state.site ?? DEFAULT_SITE}`,
    `URL: ${client.state.mcpUrl}`,
    `Tools: ${client.getTools().length}`,
  ].join("\n");
}

function getConnectedToolDetails(client: DatadogMCPClient): Record<string, unknown> {
  return {
    connected: true,
    authMode: client.state.authMode,
    site: client.state.site,
    mcpUrl: client.state.mcpUrl,
    sessionId: client.state.sessionId,
    toolCount: client.getTools().length,
  };
}

function normalizeToolPromptSnippet(description: string, toolName: string): string {
  if (isNonEmptyString(description)) {
    return truncateDisplayText(description, 120);
  }
  return `Use the Datadog MCP tool ${toolName}.`;
}

function buildRegisteredToolName(originName: string, pi: ExtensionAPI): string {
  const existingTool = pi.getAllTools().find((tool) => tool.name === originName);
  if (!existingTool) return originName;
  if (registeredToolNames.has(originName)) return originName;
  return `datadog_mcp__${originName}`;
}

function createRegisteredToolDefinition(client: DatadogMCPClient, tool: MCPTool, pi: ExtensionAPI) {
  const registeredName = buildRegisteredToolName(tool.name, pi);
  return {
    name: registeredName,
    label: `Datadog: ${humanizeWords(tool.name)}`,
    description: tool.description || `Datadog MCP tool: ${tool.name}`,
    promptSnippet: normalizeToolPromptSnippet(tool.description, tool.name),
    parameters: Type.Unsafe(isRecord(tool.inputSchema) ? tool.inputSchema : Type.Object({})),
    outputSchema: tool.outputSchema,
    ...createDatadogToolRenderer(registeredName),
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
          "Datadog MCP is not connected. Run /datadog-mcp or use datadog_mcp_connect first.",
          { connected: false },
        );
      }

      if (!client.getTools().some((entry) => entry.name === tool.name)) {
        return toolError(
          registeredName,
          "This Datadog tool is not available in the current MCP session. Reconnect to refresh the discovered tools.",
          { connected: true, available: false },
        );
      }

      onUpdate?.({
        content: [{ type: "text", text: `Running ${registeredName}...` }],
        details: { tool: registeredName, phase: "running" },
      });

      try {
        const rawResult = await client.callToolRaw(
          tool.name,
          (params as Record<string, unknown>) ?? {},
        );
        const result = normalizeMcpToolResult(rawResult);
        return toolResult(registeredName, result, { connected: true, rawResult });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return toolError(registeredName, `Error: ${message}`, {
          connected: client.state.connected,
          error: message,
        });
      }
    },
  };
}

function syncDiscoveredToolActivation(pi: ExtensionAPI, client: DatadogMCPClient): void {
  const availableToolNames = new Set(client.getTools().map((tool) => buildRegisteredToolName(tool.name, pi)));
  const activeToolNames = new Set(pi.getActiveTools());

  for (const registeredName of registeredToolNames) {
    if (availableToolNames.has(registeredName)) {
      activeToolNames.add(registeredName);
    } else {
      activeToolNames.delete(registeredName);
    }
  }

  pi.setActiveTools(Array.from(activeToolNames));
}

function deactivateDiscoveredTools(pi: ExtensionAPI): void {
  const activeToolNames = new Set(pi.getActiveTools());
  for (const registeredName of registeredToolNames) {
    activeToolNames.delete(registeredName);
  }
  pi.setActiveTools(Array.from(activeToolNames));
}

function registerDiscoveredTools(pi: ExtensionAPI, client: DatadogMCPClient): number {
  let registeredCount = 0;
  for (const tool of client.getTools()) {
    const registeredName = buildRegisteredToolName(tool.name, pi);
    if (registeredToolNames.has(registeredName)) continue;
    if (pi.getAllTools().find((entry) => entry.name === registeredName)) continue;

    pi.registerTool(createRegisteredToolDefinition(client, tool, pi));
    registeredToolNames.add(registeredName);
    registeredCount += 1;
  }

  syncDiscoveredToolActivation(pi, client);
  return registeredCount;
}

async function refreshOAuthAccessTokenAndPersist(notify?: NotifyFn): Promise<boolean> {
  const config = getCurrentConfig();
  if (!hasStoredOAuthCredentials(config)) {
    return false;
  }

  try {
    const authContext = buildSavedAuthContext(config) ?? (await discoverAuthContext(config));

    const registration: OAuthRegistration = {
      clientId: config.oauthClientId!,
      clientSecret: config.oauthClientSecret,
      tokenEndpointAuthMethod: config.tokenEndpointAuthMethod ?? "none",
    };

    const tokens = await refreshOAuthTokens(
      authContext.metadata.tokenEndpoint,
      registration,
      config.refreshToken!,
      authContext.resource,
    );

    await updatePersistedConfig({
      authMode: "oauth",
      authorizationServer: authContext.authorizationServer,
      authorizationEndpoint: authContext.metadata.authorizationEndpoint,
      tokenEndpoint: authContext.metadata.tokenEndpoint,
      registrationEndpoint: authContext.metadata.registrationEndpoint,
      resource: authContext.resource,
      oauthClientId: registration.clientId,
      oauthClientSecret: registration.clientSecret,
      tokenEndpointAuthMethod: registration.tokenEndpointAuthMethod,
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      expiresAt: tokens.expiresAt,
    });

    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    notify?.(`Datadog OAuth token refresh failed: ${message}`, "error");
    return false;
  }
}

async function performInteractiveOAuth(notify?: NotifyFn): Promise<void> {
  const config = getCurrentConfig();
  const redirectUri = config.redirectUri;
  normalizeRedirectUri(redirectUri);

  const authContext = await discoverAuthContext(config);
  const registration = await registerOAuthClient(authContext.metadata, redirectUri);
  const { codeVerifier, codeChallenge } = createPkceChallenge();
  const state = randomBytes(16).toString("hex");
  const callbackServer = await startOAuthCallbackServer(redirectUri, state);

  const authUrl = buildAuthorizationUrl(
    authContext.metadata.authorizationEndpoint,
    registration.clientId,
    redirectUri,
    codeChallenge,
    state,
    authContext.resource,
  );

  notify?.("Opening Datadog authorization page...");
  try {
    await openBrowser(authUrl);
  } catch (error) {
    callbackServer.close();
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Failed to open browser: ${message}. Open this URL manually: ${authUrl}`);
  }

  try {
    const callbackResult = await callbackServer.result;
    if (isNonEmptyString(callbackResult.error)) {
      throw new Error(
        callbackResult.errorDescription
          ? `${callbackResult.error}: ${callbackResult.errorDescription}`
          : callbackResult.error,
      );
    }
    if (!isNonEmptyString(callbackResult.code)) {
      throw new Error("OAuth completed without an authorization code.");
    }

    const tokens = await exchangeCodeForTokens(
      authContext.metadata.tokenEndpoint,
      registration,
      redirectUri,
      callbackResult.code,
      codeVerifier,
      authContext.resource,
    );

    await updatePersistedConfig({
      authMode: "oauth",
      authorizationServer: authContext.authorizationServer,
      authorizationEndpoint: authContext.metadata.authorizationEndpoint,
      tokenEndpoint: authContext.metadata.tokenEndpoint,
      registrationEndpoint: authContext.metadata.registrationEndpoint,
      resource: authContext.resource,
      oauthClientId: registration.clientId,
      oauthClientSecret: registration.clientSecret,
      tokenEndpointAuthMethod: registration.tokenEndpointAuthMethod,
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      expiresAt: tokens.expiresAt,
    });
  } finally {
    callbackServer.close();
  }
}

async function connectWithSavedConfig(client: DatadogMCPClient, notify?: NotifyFn): Promise<boolean> {
  notify?.("Connecting to saved Datadog MCP session...");
  try {
    await client.connect();
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("credentials are not configured")) {
      return false;
    }
    throw error;
  }
}

async function disconnectAndForgetConfig(pi: ExtensionAPI, client: DatadogMCPClient | null): Promise<void> {
  if (client) {
    await client.disconnect();
  }
  deactivateDiscoveredTools(pi);
  await clearPersistedConfig();
}

// =============================================================================
// Exports for tests
// =============================================================================

export {
  buildAuthorizationUrl,
  buildConnectedStatusMessage,
  buildDatadogCallSummary,
  buildDatadogMcpUrl,
  buildDisconnectedMessage,
  buildPreviewLines,
  connectWithSavedConfig,
  countOutputLines,
  createPkceChallenge,
  createRegisteredToolDefinition,
  DatadogMCPClient,
  FileConfigStorage,
  getCurrentConfig,
  getEffectiveConfig,
  getRuntimeOverrides,
  mergePersistableRuntimeOverrides,
  normalizeDatadogSite,
  normalizeMcpToolResult,
  parseToolsets,
  resolveCallbackResult,
  shouldRefreshOAuthToken,
  toolError,
  toolResult,
  truncateDisplayText,
};

// =============================================================================
// Extension entry point
// =============================================================================

export default function datadogMcpExtension(pi: ExtensionAPI) {
  pi.registerFlag("--datadog-mcp-auth-file", {
    description: "Path to the persisted Datadog MCP auth file.",
    type: "string",
  });
  pi.registerFlag("--datadog-mcp-site", {
    description: "Datadog site for the MCP endpoint, for example us3 or eu.",
    type: "string",
  });
  pi.registerFlag("--datadog-mcp-url", {
    description: "Full Datadog MCP URL override.",
    type: "string",
  });
  pi.registerFlag("--datadog-mcp-toolsets", {
    description: "Comma-separated Datadog MCP toolsets to enable.",
    type: "string",
  });
  pi.registerFlag("--datadog-mcp-redirect-uri", {
    description: "Redirect URI to use for Datadog MCP OAuth.",
    type: "string",
  });
  pi.registerFlag("--datadog-api-key", {
    description: "Datadog API key used for Datadog MCP header auth.",
    type: "string",
  });
  pi.registerFlag("--datadog-application-key", {
    description: "Datadog application key used for Datadog MCP header auth.",
    type: "string",
  });

  runtimeOverrides = getRuntimeOverrides(pi);
  persistedConfig = null;
  registeredToolNames = new Set<string>();
  mcpClient = new DatadogMCPClient(() => getCurrentConfig(), () => refreshOAuthAccessTokenAndPersist());

  const registerToolsFromClient = () => {
    if (!mcpClient) return 0;
    return registerDiscoveredTools(pi, mcpClient);
  };

  async function connectClient(notify: NotifyFn, forceOAuth = false): Promise<number> {
    if (!mcpClient) {
      throw new Error("Datadog MCP client is not initialized.");
    }
    if (mcpClient.state.connected) {
      return registerToolsFromClient();
    }

    if (!forceOAuth) {
      const reusedSavedConfig = await connectWithSavedConfig(mcpClient, notify);
      if (reusedSavedConfig) {
        return registerToolsFromClient();
      }
    }

    await performInteractiveOAuth(notify);
    await mcpClient.connect();
    return registerToolsFromClient();
  }

  async function reconnectClient(notify: NotifyFn, forceOAuth = false): Promise<number> {
    if (!mcpClient) {
      throw new Error("Datadog MCP client is not initialized.");
    }
    if (mcpClient.state.connected) {
      await mcpClient.disconnect();
    }
    deactivateDiscoveredTools(pi);
    return await connectClient(notify, forceOAuth);
  }

  pi.on("session_start", async (_event, ctx) => {
    persistedConfig = await storage.load();
    if (!mcpClient) return;

    if (!hasUsableAuth(getCurrentConfig())) {
      return;
    }

    try {
      const connected = await connectWithSavedConfig(mcpClient);
      if (connected) {
        registerToolsFromClient();
      }
    } catch (error) {
      deactivateDiscoveredTools(pi);
      const message = error instanceof Error ? error.message : String(error);
      ctx.ui.notify(`Datadog MCP auto-connect failed: ${message}`, "warning");
    }
  });

  pi.registerCommand("datadog-mcp", {
    description: "Connect to Datadog MCP, show status, or update config",
    async handler(args, ctx) {
      if (!mcpClient) {
        ctx.ui.notify("Datadog MCP client is not initialized.", "error");
        return;
      }

      const notify = createUiNotifier(ctx);
      const command = args.trim();
      if (command === "status") {
        ctx.ui.notify(getConnectionSummaryText(mcpClient), "info");
        return;
      }

      if (command === "disconnect") {
        await disconnectAndForgetConfig(pi, mcpClient);
        ctx.ui.notify("Disconnected from Datadog MCP and cleared saved config.", "info");
        return;
      }

      if (command === "forget") {
        if (mcpClient.state.connected) {
          await mcpClient.disconnect();
        }
        deactivateDiscoveredTools(pi);
        await clearPersistedConfig();
        ctx.ui.notify("Cleared saved Datadog MCP configuration.", "info");
        return;
      }

      if (command === "oauth") {
        try {
          await reconnectClient(notify, true);
          ctx.ui.notify("Connected to Datadog MCP with OAuth.", "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          ctx.ui.notify(`Datadog MCP OAuth failed: ${message}`, "error");
        }
        return;
      }

      if (command === "headers") {
        const configured = await ensureHeaderCredentialsConfigured(ctx);
        if (!configured) return;
        ctx.ui.notify("Saved Datadog header credentials. Re-run /datadog-mcp to connect.", "info");
        return;
      }

      if (command.startsWith("site ")) {
        try {
          const site = normalizeDatadogSite(command.slice("site ".length).trim());
          await updatePersistedConfig({ site });
          ctx.ui.notify(`Saved Datadog MCP site: ${site}`, "info");
        } catch (error) {
          ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
        }
        return;
      }

      if (command.startsWith("url ")) {
        const url = command.slice("url ".length).trim();
        try {
          new URL(url);
          await updatePersistedConfig({ mcpUrl: url });
          ctx.ui.notify("Saved Datadog MCP URL override.", "info");
        } catch (error) {
          ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
        }
        return;
      }

      if (command.startsWith("toolsets ")) {
        const toolsets = parseToolsets(command.slice("toolsets ".length).trim());
        await updatePersistedConfig({ toolsets });
        ctx.ui.notify(
          toolsets.length > 0
            ? `Saved Datadog MCP toolsets: ${toolsets.join(",")}`
            : "Cleared explicit Datadog MCP toolsets. The server default core toolset will be used.",
          "info",
        );
        return;
      }

      if (command.startsWith("redirect-uri ")) {
        const redirectUri = command.slice("redirect-uri ".length).trim();
        try {
          normalizeRedirectUri(redirectUri);
          await updatePersistedConfig({ redirectUri });
          ctx.ui.notify("Saved Datadog MCP redirect URI.", "info");
        } catch (error) {
          ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
        }
        return;
      }

      if (command.startsWith("api-key ")) {
        const apiKey = command.slice("api-key ".length).trim();
        if (!isNonEmptyString(apiKey)) {
          ctx.ui.notify("Usage: /datadog-mcp api-key <value>", "warning");
          return;
        }
        await updatePersistedConfig({ authMode: "headers", apiKey });
        ctx.ui.notify("Saved Datadog API key.", "info");
        return;
      }

      if (command.startsWith("application-key ")) {
        const applicationKey = command.slice("application-key ".length).trim();
        if (!isNonEmptyString(applicationKey)) {
          ctx.ui.notify("Usage: /datadog-mcp application-key <value>", "warning");
          return;
        }
        await updatePersistedConfig({ authMode: "headers", applicationKey });
        ctx.ui.notify("Saved Datadog application key.", "info");
        return;
      }

      if (!mcpClient.state.connected) {
        try {
          const registered = await connectClient(notify);
          const tools = mcpClient.getTools().length;
          const message =
            registered > 0
              ? `Connected to Datadog MCP. Registered ${registered} new tool${registered === 1 ? "" : "s"}.`
              : `Connected to Datadog MCP. ${tools} tool${tools === 1 ? "" : "s"} available.`;
          ctx.ui.notify(message, "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          ctx.ui.notify(`Datadog MCP connection failed: ${message}`, "error");
        }
        return;
      }

      const choice = await ctx.ui.select(getConnectionSummaryText(mcpClient), [
        "Reconnect",
        "Reconnect with OAuth",
        "Switch to header auth",
        "Disconnect",
        "Cancel",
      ]);

      if (choice === "Reconnect") {
        try {
          await reconnectClient(notify);
          ctx.ui.notify("Reconnected to Datadog MCP.", "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          ctx.ui.notify(`Datadog MCP reconnection failed: ${message}`, "error");
        }
        return;
      }

      if (choice === "Reconnect with OAuth") {
        try {
          await reconnectClient(notify, true);
          ctx.ui.notify("Reconnected to Datadog MCP with OAuth.", "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          ctx.ui.notify(`Datadog MCP OAuth reconnection failed: ${message}`, "error");
        }
        return;
      }

      if (choice === "Switch to header auth") {
        const configured = await ensureHeaderCredentialsConfigured(ctx);
        if (!configured) return;
        try {
          await reconnectClient(notify);
          ctx.ui.notify("Connected to Datadog MCP with header auth.", "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          ctx.ui.notify(`Datadog MCP header-auth connection failed: ${message}`, "error");
        }
        return;
      }

      if (choice === "Disconnect") {
        const confirmed = await ctx.ui.confirm(
          "Disconnect Datadog MCP",
          "Clear the saved Datadog credentials and disconnect from Datadog MCP?",
        );
        if (!confirmed) return;
        await disconnectAndForgetConfig(pi, mcpClient);
        ctx.ui.notify("Disconnected from Datadog MCP.", "info");
      }
    },
  });

  pi.registerTool({
    name: "datadog_mcp_connect",
    label: "Datadog MCP Connect",
    description: "Connect to Datadog via Datadog's managed MCP server",
    promptSnippet: "Connect to Datadog MCP when Datadog tools are needed but not yet configured.",
    parameters: Type.Object({}),
    ...createDatadogToolRenderer("datadog_mcp_connect"),
    async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
      if (!mcpClient) {
        return toolError("datadog_mcp_connect", "Datadog MCP client is not initialized.");
      }

      if (mcpClient.state.connected) {
        return toolResult("datadog_mcp_connect", buildConnectedStatusMessage(mcpClient), getConnectedToolDetails(mcpClient));
      }

      try {
        const notify = ctx ? createUiNotifier(ctx) : undefined;
        const registered = await connectClient(notify ?? (() => undefined));
        return toolResult(
          "datadog_mcp_connect",
          `${buildConnectedStatusMessage(mcpClient)}\n\nRegistered ${registered} new tool${registered === 1 ? "" : "s"}.`,
          getConnectedToolDetails(mcpClient),
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return toolError("datadog_mcp_connect", `Connection failed: ${message}`, {
          error: message,
          requiresInteractiveSetup: message.includes("credentials are not configured"),
        });
      }
    },
  });

  pi.registerTool({
    name: "datadog_mcp_disconnect",
    label: "Datadog MCP Disconnect",
    description: "Disconnect from Datadog MCP and clear the saved Datadog credentials",
    parameters: Type.Object({}),
    ...createDatadogToolRenderer("datadog_mcp_disconnect"),
    async execute() {
      await disconnectAndForgetConfig(pi, mcpClient);
      return toolResult(
        "datadog_mcp_disconnect",
        "Disconnected from Datadog MCP and cleared the saved Datadog credentials.",
        { connected: false },
      );
    },
  });

  pi.registerTool({
    name: "datadog_mcp_status",
    label: "Datadog MCP Status",
    description: "Check the current Datadog MCP connection status",
    parameters: Type.Object({}),
    ...createDatadogToolRenderer("datadog_mcp_status"),
    async execute() {
      if (!mcpClient?.state.connected) {
        const config = getCurrentConfig();
        return toolResult("datadog_mcp_status", buildDisconnectedMessage(config), {
          connected: false,
          authMode: config.authMode,
          site: config.site,
          mcpUrl: config.mcpUrl,
          toolCount: 0,
        });
      }

      return toolResult("datadog_mcp_status", getConnectionSummaryText(mcpClient), getConnectedToolDetails(mcpClient));
    },
  });
}
