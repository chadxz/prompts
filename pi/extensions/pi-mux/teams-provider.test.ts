import { mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  authenticateInteractively,
  buildAuthorizationUrl,
  registerTeamsOAuthClient,
  exchangeCodeForTokens,
  refreshTokens,
  createCodeChallenge,
  DEFAULT_MCP_URL,
  extractClaimsChallenge,
  getConnectionStatusText,
  parseTokenBundle,
  resolveTeamsConfiguration,
  TeamsConfigStorage,
  TeamsMCPClient,
} from "./providers/teams/pi-teams-mcp.ts";

const cleanupPaths = new Set<string>();
const registeredOAuth = {
  clientId: "discovered-client-id",
  issuer: "https://teams.mcp.convergint.tech/oauth",
  authorizationEndpoint: "https://login.microsoftonline.com/discovered-tenant/oauth2/v2.0/authorize",
  tokenEndpoint: "https://login.microsoftonline.com/discovered-tenant/oauth2/v2.0/token",
};

/** Creates a successful JSON-RPC HTTP response. */
function rpcResult(id: number, result: unknown): Response {
  return Response.json({ jsonrpc: "2.0", id, result });
}

afterEach(() => {
  vi.unstubAllGlobals();
  for (const path of cleanupPaths) {
    rmSync(path, { recursive: true, force: true });
  }
  cleanupPaths.clear();
});

describe("Teams provider configuration", () => {
  it("starts with only the MCP URL and no built-in client or tenant", () => {
    expect(resolveTeamsConfiguration({}, {})).toEqual({ mcpUrl: DEFAULT_MCP_URL });
  });

  it("discards saved credentials when the endpoint changes", () => {
    expect(resolveTeamsConfiguration(
      { mcpUrl: "https://runtime.example/mcp" },
      { mcpUrl: DEFAULT_MCP_URL, oauth: registeredOAuth, refreshToken: "saved-refresh" },
    )).toEqual({ mcpUrl: "https://runtime.example/mcp" });
  });

  it("requires new registration for legacy token caches", () => {
    expect(resolveTeamsConfiguration({}, {
      mcpUrl: DEFAULT_MCP_URL, accessToken: "old-access", refreshToken: "old-refresh",
    })).toEqual({ mcpUrl: DEFAULT_MCP_URL });
  });

  it("retains the discovered registration with tokens for the same resource", () => {
    const saved = { mcpUrl: DEFAULT_MCP_URL, oauth: registeredOAuth, refreshToken: "refresh" };
    expect(resolveTeamsConfiguration({}, saved)).toEqual(saved);
  });

  it("builds an Entra PKCE request for the MCP resource scope", () => {
    const configuration = { mcpUrl: DEFAULT_MCP_URL, oauth: registeredOAuth };
    const claims = '{"access_token":{"xms_cc":{"values":["cp1"]}}}';
    const url = buildAuthorizationUrl(
      configuration,
      "http://localhost:54321",
      "state-value",
      createCodeChallenge("verifier"),
      claims,
    );

    expect(url.origin).toBe("https://login.microsoftonline.com");
    expect(url.pathname).toContain("discovered-tenant");
    expect(url.searchParams.get("client_id")).toBe(registeredOAuth.clientId);
    expect(url.searchParams.get("redirect_uri")).toBe(
      "http://localhost:54321",
    );
    expect(url.searchParams.get("scope")).toContain(
      "https://teams.mcp.convergint.tech/mcp/access_as_user",
    );
    expect(url.searchParams.get("scope")).toContain("offline_access");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("claims")).toBe(claims);
  });

  it("keeps the prior rotating refresh token when Entra omits a replacement", () => {
    const before = Date.now();
    const bundle = parseTokenBundle(
      { access_token: "access", expires_in: 300 },
      "refresh",
    );

    expect(bundle.accessToken).toBe("access");
    expect(bundle.refreshToken).toBe("refresh");
    expect(bundle.expiresAt).toBeGreaterThanOrEqual(before + 300_000);
  });

  it("stores each Pi user's OAuth state with owner-only permissions", () => {
    const directory = mkdtempSync(join(tmpdir(), "pi-teams-mcp-"));
    cleanupPaths.add(directory);
    const filePath = join(directory, "private", "oauth.json");
    const storage = new TeamsConfigStorage(filePath);

    storage.save({ accessToken: "access", refreshToken: "refresh" });

    expect(statSync(filePath).mode & 0o777).toBe(0o600);
    expect(statSync(join(directory, "private")).mode & 0o777).toBe(0o700);
    expect(storage.load()).toEqual({
      accessToken: "access",
      refreshToken: "refresh",
    });
  });

  it("extracts escaped Conditional Access claims challenges", () => {
    const claims =
      '{\\"access_token\\":{\\"xms_cc\\":{\\"values\\":[\\"cp1\\"]}}}';
    const header =
      `Bearer error="insufficient_claims", claims="${claims}", resource_metadata="https://example/.well-known/oauth-protected-resource"`;

    expect(extractClaimsChallenge(header)).toBe(
      '{"access_token":{"xms_cc":{"values":["cp1"]}}}',
    );
  });
});

describe("TeamsMCPClient", () => {
  it("discovers tools without initialize or protocol session state", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        rpcResult(1, {
          tools: [
            {
              name: "send_chat_message",
              description: "Send a message.",
              inputSchema: { type: "object" },
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        rpcResult(2, {
          content: [{ type: "text", text: "Authenticated as Person Example" }],
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const client = new TeamsMCPClient(
      "https://teams.example/mcp",
      async () => "user-token",
      async () => "refreshed-token",
    );

    await client.connect();

    expect(client.state).toMatchObject({
      connected: true,
      authenticated: true,
      account: "Person Example",
      protocolVersion: "2026-07-28",
    });
    expect(client.getTools()).toHaveLength(1);
    const requests = fetchMock.mock.calls.map((call) => {
      const body = call[1]?.body;
      if (typeof body !== "string") {
        throw new Error("Expected a string request body.");
      }
      return JSON.parse(body);
    });
    expect(requests.map((request) => request.method)).toEqual([
      "tools/list",
      "tools/call",
    ]);
    expect(requests.map((request) => request.params._meta)).toEqual([
      {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {
          name: "pi-mux",
          version: "1.0.0",
        },
      },
      {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {
          name: "pi-mux",
          version: "1.0.0",
        },
      },
    ]);
    expect(
      new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get(
        "MCP-Protocol-Version",
      ),
    ).toBe("2026-07-28");
    expect(
      new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Mcp-Method"),
    ).toBe("tools/list");
    expect(
      new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Mcp-Method"),
    ).toBe("tools/call");
    expect(
      new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Mcp-Name"),
    ).toBe("auth_status");
    expect(
      new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has(
        "MCP-Session-Id",
      ),
    ).toBe(false);
  });

  it("refreshes once after an ordinary bearer challenge", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(rpcResult(2, { tools: [] }))
      .mockResolvedValueOnce(
        rpcResult(3, {
          content: [{ type: "text", text: "Authenticated as Person Example" }],
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const refresh = vi.fn(async () => "refreshed-token");
    const client = new TeamsMCPClient(
      "https://teams.example/mcp",
      async () => "user-token",
      refresh,
    );

    await client.connect();

    expect(refresh).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("retains a Conditional Access challenge for interactive reauthorization", async () => {
    const claims =
      '{\\"access_token\\":{\\"xms_cc\\":{\\"values\\":[\\"cp1\\"]}}}';
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(null, {
          status: 401,
          headers: {
            "WWW-Authenticate": `Bearer error="insufficient_claims", claims="${claims}"`,
          },
        }),
      ),
    );
    const client = new TeamsMCPClient(
      "https://teams.example/mcp",
      async () => "user-token",
      async () => "refreshed-token",
    );

    await expect(client.connect()).rejects.toThrow(
      "additional interactive authentication",
    );
    expect(client.state.claimsChallenge).toContain("xms_cc");
    expect(getConnectionStatusText(client)).toContain("Conditional Access");
  });

  it("reports disconnected state without contacting the remote endpoint", () => {
    const client = new TeamsMCPClient();

    expect(getConnectionStatusText(client)).toContain(
      "- Remote connection: Not connected",
    );
    expect(getConnectionStatusText(client)).toContain(
      "Run /mux connect teams to authenticate and connect.",
    );
  });
});

/** Supplies real SDK discovery and registration with controlled HTTP responses. */
function mockRegistration(options: {
  resource?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  registration?: Record<string, unknown>;
  registrationStatus?: number;
} = {}) {
  const fetchMock = vi.fn<typeof fetch>()
    .mockResolvedValueOnce(Response.json({
      resource: DEFAULT_MCP_URL,
      authorization_servers: [registeredOAuth.issuer],
      ...options.resource,
    }))
    .mockResolvedValueOnce(Response.json({
      issuer: registeredOAuth.issuer,
      authorization_endpoint: registeredOAuth.authorizationEndpoint,
      token_endpoint: registeredOAuth.tokenEndpoint,
      registration_endpoint: `${registeredOAuth.issuer}/register`,
      response_types_supported: ["code"],
      code_challenge_methods_supported: ["S256"],
      ...options.metadata,
    }))
    .mockResolvedValueOnce(Response.json({
      client_id: registeredOAuth.clientId,
      redirect_uris: ["http://localhost:54321"],
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
      token_endpoint_auth_method: "none",
      ...options.registration,
    }, { status: options.registrationStatus ?? 201 }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Teams dynamic client registration", () => {
  it("discovers metadata and registers the actual callback without credentials", async () => {
    const fetchMock = mockRegistration();
    const oauth = await registerTeamsOAuthClient({ mcpUrl: DEFAULT_MCP_URL }, "http://localhost:54321");
    expect(oauth).toEqual(registeredOAuth);
    expect(fetchMock.mock.calls.map(([url]) => (url instanceof Request ? url.url : String(url)))).toEqual([
      "https://teams.mcp.convergint.tech/.well-known/oauth-protected-resource/mcp",
      "https://teams.mcp.convergint.tech/.well-known/oauth-authorization-server/oauth",
      "https://teams.mcp.convergint.tech/oauth/register",
    ]);
    const registrationRequest = fetchMock.mock.calls[2]![1]!;
    expect(JSON.parse(registrationRequest.body as string)).toEqual({
      client_name: "Pi Teams MCP",
      redirect_uris: ["http://localhost:54321"],
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
      token_endpoint_auth_method: "none",
      scope: `${DEFAULT_MCP_URL}/access_as_user openid profile offline_access`,
    });
    for (const [, init] of fetchMock.mock.calls) {
      expect(init?.redirect).toBe("error");
      expect(init?.signal).toBeInstanceOf(AbortSignal);
      expect(new Headers(init?.headers).has("Authorization")).toBe(false);
    }
  });

  it.each([
    { resource: { resource: "https://other.example/mcp" } },
    { resource: { authorization_servers: [] } },
    { metadata: { issuer: "https://other.example/oauth" } },
    { metadata: { registration_endpoint: undefined } },
    { metadata: { code_challenge_methods_supported: ["plain"] } },
    { metadata: { authorization_endpoint: "http://login.example/authorize" } },
    { metadata: { token_endpoint: "http://login.example/token" } },
    { metadata: { registration_endpoint: "https://user:password@example.com/register" } },
  ])("rejects invalid discovery before registering: %j", async (options) => {
    const fetchMock = mockRegistration(options);
    await expect(registerTeamsOAuthClient({ mcpUrl: DEFAULT_MCP_URL }, "http://localhost:54321"))
      .rejects.toThrow();
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== "POST")).toBe(true);
  });

  it.each([
    { client_id: "" },
    { token_endpoint_auth_method: "client_secret_post", client_secret: "secret" },
    { redirect_uris: ["http://localhost:11111"] },
    { grant_types: ["client_credentials"] },
    { scope: "openid" },
  ])("rejects incompatible registration responses: %j", async (registration) => {
    mockRegistration({ registration });
    await expect(registerTeamsOAuthClient({ mcpUrl: DEFAULT_MCP_URL }, "http://localhost:54321"))
      .rejects.toThrow();
  });

  it("closes the callback timer when discovery fails before browser sign-in", async () => {
    vi.useFakeTimers();
    try {
      mockRegistration({ metadata: { issuer: "https://wrong.example/oauth" } });
      await expect(authenticateInteractively({ mcpUrl: DEFAULT_MCP_URL }, () => undefined))
        .rejects.toThrow("different authorization-server issuer");
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("surfaces rejected callbacks without falling back to a built-in ID", async () => {
    mockRegistration({ registration: { error: "invalid_redirect_uri" }, registrationStatus: 400 });
    await expect(registerTeamsOAuthClient({ mcpUrl: DEFAULT_MCP_URL }, "http://localhost:54321"))
      .rejects.toThrow();
  });

  it("uses the discovered client and endpoint for code exchange and refresh after restart", async () => {
    const fetchMock = mockRegistration();
    const oauth = await registerTeamsOAuthClient({ mcpUrl: DEFAULT_MCP_URL }, "http://localhost:54321");
    fetchMock.mockResolvedValueOnce(Response.json({ access_token: "access", refresh_token: "refresh", expires_in: 3600 }));
    const bundle = await exchangeCodeForTokens({ mcpUrl: DEFAULT_MCP_URL, oauth }, "code", "http://localhost:54321", "verifier");
    const directory = mkdtempSync(join(tmpdir(), "pi-teams-dcr-"));
    cleanupPaths.add(directory);
    const storage = new TeamsConfigStorage(join(directory, "oauth.json"));
    storage.save({ mcpUrl: DEFAULT_MCP_URL, oauth, ...bundle });
    fetchMock.mockResolvedValueOnce(Response.json({ access_token: "refreshed", refresh_token: "rotated", expires_in: 3600 }));
    const refreshed = await refreshTokens(resolveTeamsConfiguration({}, storage.load()));
    expect(refreshed.refreshToken).toBe("rotated");
    const requests = fetchMock.mock.calls.slice(3);
    expect(requests.map(([url]) => (url instanceof Request ? url.url : String(url)))).toEqual([oauth.tokenEndpoint, oauth.tokenEndpoint]);
    const code = new URLSearchParams(requests[0]![1]!.body as string);
    expect(code.get("client_id")).toBe(oauth.clientId);
    expect(code.get("code_verifier")).toBe("verifier");
    expect(code.get("redirect_uri")).toBe("http://localhost:54321");
    const refresh = new URLSearchParams(requests[1]![1]!.body as string);
    expect(refresh.get("client_id")).toBe(oauth.clientId);
    expect(refresh.get("refresh_token")).toBe("refresh");
    expect(requests.every(([, init]) => !new URLSearchParams(init?.body as string).has("client_secret"))).toBe(true);
  });
});
