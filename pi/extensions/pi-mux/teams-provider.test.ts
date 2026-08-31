import { mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildAuthorizationUrl,
  createCodeChallenge,
  DEFAULT_CLIENT_ID,
  DEFAULT_MCP_URL,
  DEFAULT_TENANT_ID,
  extractClaimsChallenge,
  getConnectionStatusText,
  parseTokenBundle,
  resolveTeamsConfiguration,
  TeamsConfigStorage,
  TeamsMCPClient,
} from "./providers/teams/pi-teams-mcp.ts";

const cleanupPaths = new Set<string>();

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
  it("defaults to the managed multi-user endpoint and public client", () => {
    const configuration = resolveTeamsConfiguration({}, {});

    expect(configuration).toMatchObject({
      clientId: DEFAULT_CLIENT_ID,
      tenantId: DEFAULT_TENANT_ID,
      mcpUrl: DEFAULT_MCP_URL,
    });
  });

  it("prefers runtime endpoint identifiers over persisted values", () => {
    const configuration = resolveTeamsConfiguration(
      {
        clientId: "runtime-client",
        tenantId: "runtime-tenant",
        mcpUrl: "https://runtime.example/mcp",
      },
      {
        clientId: "saved-client",
        tenantId: "saved-tenant",
        mcpUrl: "https://saved.example/mcp",
        refreshToken: "saved-refresh",
      },
    );

    expect(configuration).toMatchObject({
      clientId: "runtime-client",
      tenantId: "runtime-tenant",
      mcpUrl: "https://runtime.example/mcp",
      refreshToken: "saved-refresh",
    });
  });

  it("builds an Entra PKCE request for the MCP resource scope", () => {
    const configuration = resolveTeamsConfiguration({}, {});
    const claims = '{"access_token":{"xms_cc":{"values":["cp1"]}}}';
    const url = buildAuthorizationUrl(
      configuration,
      "http://localhost:54321",
      "state-value",
      createCodeChallenge("verifier"),
      claims,
    );

    expect(url.origin).toBe("https://login.microsoftonline.com");
    expect(url.pathname).toContain(DEFAULT_TENANT_ID);
    expect(url.searchParams.get("client_id")).toBe(DEFAULT_CLIENT_ID);
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
    expect(
      new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get(
        "MCP-Protocol-Version",
      ),
    ).toBe("2026-07-28");
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
