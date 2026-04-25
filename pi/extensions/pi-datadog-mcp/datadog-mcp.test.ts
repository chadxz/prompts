import { mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";

import datadogMcpExtension, {
  buildAuthorizationUrl,
  buildConnectedStatusMessage,
  buildDatadogCallSummary,
  buildDatadogMcpUrl,
  buildDisconnectedMessage,
  buildPreviewLines,
  connectWithSavedConfig,
  countOutputLines,
  createPkceChallenge,
  DatadogMCPClient,
  FileConfigStorage,
  getEffectiveConfig,
  mergePersistableRuntimeOverrides,
  normalizeDatadogSite,
  normalizeMcpToolResult,
  parseToolsets,
  resolveCallbackResult,
  shouldRefreshOAuthToken,
  toolError,
  toolResult,
  truncateDisplayText,
} from "./extensions/pi-datadog-mcp";

describe("normalizeDatadogSite", () => {
  it("normalizes supported site aliases and domains", () => {
    expect(normalizeDatadogSite(undefined)).toBe("us3");
    expect(normalizeDatadogSite("US1")).toBe("us1");
    expect(normalizeDatadogSite("us3.datadoghq.com")).toBe("us3");
    expect(normalizeDatadogSite("datadoghq.eu")).toBe("eu");
    expect(normalizeDatadogSite("us1_fed")).toBe("us1-fed");
  });
});

describe("buildDatadogMcpUrl", () => {
  it("builds regional MCP URLs and appends toolsets", () => {
    expect(buildDatadogMcpUrl("us3", undefined, [])).toBe(
      "https://mcp.us3.datadoghq.com/api/unstable/mcp-server/mcp",
    );
    expect(buildDatadogMcpUrl("eu", undefined, ["core", "dashboards"])).toBe(
      "https://mcp.datadoghq.eu/api/unstable/mcp-server/mcp?toolsets=core%2Cdashboards",
    );
  });
});

describe("OAuth helpers", () => {
  it("creates PKCE values and authorization URLs", () => {
    const { codeVerifier, codeChallenge } = createPkceChallenge();
    expect(codeVerifier).toBeTruthy();
    expect(codeChallenge).toBeTruthy();

    const url = new URL(
      buildAuthorizationUrl(
        "https://mcp.us3.datadoghq.com/api/unstable/mcp-server/authorize",
        "client-123",
        "http://127.0.0.1:8563/oauth/callback",
        "challenge-123",
        "state-123",
        "https://mcp.us3.datadoghq.com",
      ),
    );

    expect(url.searchParams.get("client_id")).toBe("client-123");
    expect(url.searchParams.get("redirect_uri")).toBe("http://127.0.0.1:8563/oauth/callback");
    expect(url.searchParams.get("code_challenge")).toBe("challenge-123");
    expect(url.searchParams.get("resource")).toBe("https://mcp.us3.datadoghq.com");
  });

  it("resolves callback results", () => {
    expect(resolveCallbackResult(new URLSearchParams("state=bad"), "expected").result.error).toBe(
      "State mismatch",
    );
    expect(
      resolveCallbackResult(
        new URLSearchParams("state=expected&error=access_denied&error_description=nope"),
        "expected",
      ).result,
    ).toMatchObject({ error: "access_denied", errorDescription: "nope" });
    expect(
      resolveCallbackResult(new URLSearchParams("state=expected&code=auth-code"), "expected").result,
    ).toMatchObject({ code: "auth-code" });
  });
});

describe("toolset and output helpers", () => {
  it("parses toolsets and formats output helpers", () => {
    expect(parseToolsets("core, dashboards ,core")).toEqual(["core", "dashboards"]);
    expect(countOutputLines("line 1\n\nline 2")).toBe(2);
    expect(truncateDisplayText("x".repeat(90))).toHaveLength(88);
    expect(buildPreviewLines("one\n\n two \nthree", 5)).toEqual(["one", "two", "three"]);
  });

  it("normalizes tool results and helper result payloads", () => {
    expect(
      normalizeMcpToolResult({
        content: [
          { type: "text", text: "first" },
          { type: "text", text: "second" },
        ],
      }),
    ).toBe("first\nsecond");

    expect(
      normalizeMcpToolResult({
        structuredContent: { ok: true, items: 3 },
      }),
    ).toContain('"items": 3');

    expect(toolResult("demo", "ok")).toEqual({
      content: [{ type: "text", text: "ok" }],
      details: { tool: "demo", lineCount: 1, characterCount: 2 },
    });

    expect(toolError("demo", "bad")).toEqual({
      content: [{ type: "text", text: "bad" }],
      isError: true,
      details: { tool: "demo" },
    });
  });
});

describe("config persistence helpers", () => {
  it("does not persist runtime header credentials", () => {
    expect(
      mergePersistableRuntimeOverrides(
        {
          authMode: "oauth",
          site: "us3",
          accessToken: "stored-token",
          refreshToken: "stored-refresh",
          oauthClientId: "stored-client",
        },
        {
          site: "eu",
          apiKey: "runtime-api-key",
          applicationKey: "runtime-app-key",
        },
      ),
    ).toEqual({
      authMode: "oauth",
      site: "eu",
      accessToken: "stored-token",
      refreshToken: "stored-refresh",
      oauthClientId: "stored-client",
    });
  });

  it("writes the auth file with owner-only permissions", async () => {
    const tempDir = mkdtempSync(join(tmpdir(), "pi-datadog-mcp-"));
    const authFile = join(tempDir, "auth.json");
    const originalAuthFile = process.env.DATADOG_MCP_AUTH_FILE;
    process.env.DATADOG_MCP_AUTH_FILE = authFile;

    try {
      const storage = new FileConfigStorage();
      await storage.save({
        authMode: "oauth",
        accessToken: "access-token",
        refreshToken: "refresh-token",
        oauthClientId: "client-id",
      });

      const saved = await storage.load();
      const mode = statSync(authFile).mode & 0o777;

      expect(saved).toEqual({
        authMode: "oauth",
        accessToken: "access-token",
        refreshToken: "refresh-token",
        oauthClientId: "client-id",
      });
      expect(mode).toBe(0o600);
    } finally {
      if (originalAuthFile === undefined) {
        delete process.env.DATADOG_MCP_AUTH_FILE;
      } else {
        process.env.DATADOG_MCP_AUTH_FILE = originalAuthFile;
      }
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
});

describe("call summaries and status text", () => {
  it("summarizes Datadog tool calls compactly", () => {
    expect(
      buildDatadogCallSummary("search_datadog_logs", {
        query: "service:payments status:error",
        limit: 25,
      }),
    ).toEqual({
      primary: "service:payments status:error",
      meta: ["limit=25"],
    });
  });

  it("formats connected and disconnected status messages", () => {
    const config = getEffectiveConfig(
      {
        authMode: "oauth",
        site: "us3",
        toolsets: ["core", "dashboards"],
        accessToken: "token-123",
        refreshToken: "refresh-123",
        oauthClientId: "client-123",
      },
      {},
    );

    expect(buildDisconnectedMessage(config)).toContain("Connected: No");
    expect(buildDisconnectedMessage(config)).toContain("Auth mode: oauth");

    const client = new DatadogMCPClient(() => config);
    client.state.connected = true;
    client.state.authMode = "oauth";
    client.state.site = "us3";
    client.state.mcpUrl = config.mcpUrl;
    expect(buildConnectedStatusMessage(client)).toContain("Connected to Datadog MCP");
    expect(buildConnectedStatusMessage(client)).toContain("Auth: oauth");
  });
});

describe("shouldRefreshOAuthToken", () => {
  it("identifies when OAuth tokens need refresh", () => {
    expect(
      shouldRefreshOAuthToken(
        getEffectiveConfig(
          {
            authMode: "oauth",
            site: "us3",
            refreshToken: "refresh-123",
            oauthClientId: "client-123",
          },
          {},
        ),
      ),
    ).toBe(true);

    expect(
      shouldRefreshOAuthToken(
        getEffectiveConfig(
          {
            authMode: "oauth",
            site: "us3",
            accessToken: "token-123",
            refreshToken: "refresh-123",
            oauthClientId: "client-123",
            expiresAt: Date.now() + 60 * 60 * 1000,
          },
          {},
        ),
      ),
    ).toBe(false);
  });
});

describe("DatadogMCPClient", () => {
  it("connects, discovers tools, and calls tools with OAuth bearer auth", async () => {
    const originalFetch = global.fetch;
    const config = getEffectiveConfig(
      {
        authMode: "oauth",
        site: "us3",
        accessToken: "token-123",
        refreshToken: "refresh-123",
        oauthClientId: "client-123",
      },
      {},
    );

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({
          "content-type": "application/json",
          "mcp-session-id": "session-12345678",
        }),
        json: async () => ({ result: { serverInfo: { name: "datadog-mcp", version: "1.0.0" } } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
        body: { cancel: vi.fn() },
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          result: {
            tools: [{ name: "search_datadog_logs", description: "Search logs", inputSchema: {} }],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ result: { content: [{ type: "text", text: "hello" }] } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
      });

    global.fetch = fetchMock as typeof fetch;

    try {
      const client = new DatadogMCPClient(() => config);
      await client.connect();

      expect(client.state.connected).toBe(true);
      expect(client.getTools()).toHaveLength(1);
      expect(
        await client.callTool("search_datadog_logs", {
          query: "service:payments",
          properties: { id: "12345", priority: "7" },
        }),
      ).toContain("hello");
      expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
        method: "POST",
        headers: expect.any(Headers),
      });

      const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
      expect(headers.get("Authorization")).toBe("Bearer token-123");

      const callBody = JSON.parse(String(fetchMock.mock.calls[3]?.[1]?.body));
      expect(callBody.params.arguments.properties.id).toBe("12345");
      expect(callBody.params.arguments.properties.priority).toBe("7");

      await client.disconnect();
      expect(client.state.connected).toBe(false);
    } finally {
      global.fetch = originalFetch;
    }
  });

  it("supports SSE tool responses and token refresh on 401", async () => {
    const originalFetch = global.fetch;
    const config = getEffectiveConfig(
      {
        authMode: "oauth",
        site: "us3",
        accessToken: "token-123",
        refreshToken: "refresh-123",
        oauthClientId: "client-123",
      },
      {},
    );

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({
          "content-type": "application/json",
          "mcp-session-id": "session-sse",
        }),
        json: async () => ({ result: { serverInfo: { name: "datadog-mcp", version: "1.0.0" } } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
        body: { cancel: vi.fn() },
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ result: { tools: [] } }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "text/plain" }),
        text: async () => "Unauthorized",
        body: { cancel: vi.fn() },
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "text/event-stream" }),
        text: async () => 'data: {"id":3,"result":{"content":[{"type":"text","text":"from sse"}]}}\n\n',
      }) as typeof fetch;

    try {
      const refreshSpy = vi.fn(async () => true);
      const client = new DatadogMCPClient(() => config, refreshSpy);
      await client.connect();
      await expect(client.callTool("demo", {})).resolves.toContain("from sse");
      expect(refreshSpy).toHaveBeenCalled();
    } finally {
      global.fetch = originalFetch;
    }
  });

  it("surfaces the original 401 when token refresh fails", async () => {
    const originalFetch = global.fetch;
    const config = getEffectiveConfig(
      {
        authMode: "oauth",
        site: "us3",
        accessToken: "expired-token",
        refreshToken: "refresh-123",
        oauthClientId: "client-123",
      },
      {},
    );

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({
          "content-type": "application/json",
          "mcp-session-id": "session-refresh-fail",
        }),
        json: async () => ({ result: { serverInfo: { name: "datadog-mcp", version: "1.0.0" } } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
        body: { cancel: vi.fn() },
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ result: { tools: [] } }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "text/plain" }),
        text: async () => "Unauthorized",
        body: { cancel: vi.fn() },
      }) as typeof fetch;

    try {
      const refreshSpy = vi.fn(async () => false);
      const client = new DatadogMCPClient(() => config, refreshSpy);
      await client.connect();
      await expect(client.callTool("demo", {})).rejects.toThrow("HTTP 401: Unauthorized");
      expect(refreshSpy).toHaveBeenCalled();
    } finally {
      global.fetch = originalFetch;
    }
  });
});

describe("connectWithSavedConfig", () => {
  it("reuses saved credentials when present", async () => {
    const config = getEffectiveConfig(
      {
        authMode: "oauth",
        site: "us3",
        accessToken: "token-123",
        refreshToken: "refresh-123",
        oauthClientId: "client-123",
      },
      {},
    );

    const client = new DatadogMCPClient(() => config);
    const connectSpy = vi.spyOn(client, "connect").mockResolvedValue();

    expect(await connectWithSavedConfig(client, vi.fn())).toBe(true);
    expect(connectSpy).toHaveBeenCalled();
  });

  it("returns false when credentials are missing", async () => {
    const config = getEffectiveConfig({ site: "us3" }, {});
    const client = new DatadogMCPClient(() => config);
    vi.spyOn(client, "connect").mockRejectedValue(new Error("Datadog MCP credentials are not configured."));
    expect(await connectWithSavedConfig(client, vi.fn())).toBe(false);
  });

  it("throws when a saved-config connection fails for a real error", async () => {
    const config = getEffectiveConfig(
      {
        authMode: "headers",
        site: "us3",
        apiKey: "bad-api-key",
        applicationKey: "bad-app-key",
      },
      {},
    );
    const client = new DatadogMCPClient(() => config);
    vi.spyOn(client, "connect").mockRejectedValue(new Error("HTTP 401: Unauthorized"));
    await expect(connectWithSavedConfig(client, vi.fn())).rejects.toThrow("HTTP 401: Unauthorized");
  });
});

describe("reconnect flows", () => {
  it("deactivates stale discovered tools when reconnecting with narrower toolsets", async () => {
    const originalFetch = global.fetch;
    const originalAuthFile = process.env.DATADOG_MCP_AUTH_FILE;
    const tempDir = mkdtempSync(join(tmpdir(), "pi-datadog-mcp-reconnect-"));
    const authFile = join(tempDir, "auth.json");
    process.env.DATADOG_MCP_AUTH_FILE = authFile;

    const registeredTools: Array<Record<string, unknown>> = [];
    const commands = new Map<string, { handler: (args: string, ctx: { ui: Record<string, unknown> }) => Promise<void> }>();
    let activeTools: string[] = [];

    const mockPi = {
      registerFlag: vi.fn(),
      getFlag: vi.fn(() => undefined),
      registerTool: vi.fn((tool: Record<string, unknown>) => {
        registeredTools.push(tool);
        const name = tool.name as string;
        if (!activeTools.includes(name)) {
          activeTools = [...activeTools, name];
        }
      }),
      registerCommand: vi.fn((name: string, options: { handler: (args: string, ctx: { ui: Record<string, unknown> }) => Promise<void> }) => {
        commands.set(name, options);
      }),
      getAllTools: vi.fn(() =>
        registeredTools.map((tool) => ({
          name: tool.name,
          description: tool.description,
          parameters: tool.parameters,
          sourceInfo: { source: "extension", path: "test", scope: "temporary", origin: "top-level" },
        })),
      ),
      getActiveTools: vi.fn(() => [...activeTools]),
      setActiveTools: vi.fn((toolNames: string[]) => {
        activeTools = [...toolNames];
      }),
      on: vi.fn(),
    };

    datadogMcpExtension(mockPi as never);

    const command = commands.get("datadog-mcp")?.handler;
    expect(command).toBeDefined();

    const ctx = {
      ui: {
        notify: vi.fn(),
        input: vi.fn(),
        select: vi.fn(async () => "Reconnect"),
        confirm: vi.fn(),
      },
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({
          "content-type": "application/json",
          "mcp-session-id": "session-1",
        }),
        json: async () => ({ result: { serverInfo: { name: "datadog-mcp", version: "1.0.0" } } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
        body: { cancel: vi.fn() },
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          result: {
            tools: [
              { name: "search_datadog_logs", description: "Search logs", inputSchema: {} },
              { name: "manage_dashboards", description: "Manage dashboards", inputSchema: {} },
            ],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({
          "content-type": "application/json",
          "mcp-session-id": "session-2",
        }),
        json: async () => ({ result: { serverInfo: { name: "datadog-mcp", version: "1.0.1" } } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
        body: { cancel: vi.fn() },
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          result: {
            tools: [{ name: "search_datadog_logs", description: "Search logs", inputSchema: {} }],
          },
        }),
      });

    global.fetch = fetchMock as typeof fetch;

    try {
      await command?.("api-key test-api-key", ctx);
      await command?.("application-key test-app-key", ctx);
      await command?.("toolsets core,dashboards", ctx);
      await command?.("", ctx);

      expect(activeTools).toContain("search_datadog_logs");
      expect(activeTools).toContain("manage_dashboards");

      await command?.("toolsets core", ctx);
      await command?.("", ctx);

      expect(activeTools).toContain("search_datadog_logs");
      expect(activeTools).not.toContain("manage_dashboards");

      expect(mockPi.setActiveTools).toHaveBeenCalled();
      expect(activeTools).not.toContain("manage_dashboards");
    } finally {
      global.fetch = originalFetch;
      if (originalAuthFile === undefined) {
        delete process.env.DATADOG_MCP_AUTH_FILE;
      } else {
        process.env.DATADOG_MCP_AUTH_FILE = originalAuthFile;
      }
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
});

describe("extension registration", () => {
  it("registers flags, tools, and the /datadog-mcp command", () => {
    const mockPi = {
      registerFlag: vi.fn(),
      getFlag: vi.fn(() => undefined),
      registerTool: vi.fn(),
      registerCommand: vi.fn(),
      getAllTools: vi.fn(() => []),
      getActiveTools: vi.fn(() => []),
      setActiveTools: vi.fn(),
      on: vi.fn(),
    };

    datadogMcpExtension(mockPi as never);

    const flags = mockPi.registerFlag.mock.calls.map(([name]) => name);
    expect(flags).toEqual(
      expect.arrayContaining([
        "--datadog-mcp-auth-file",
        "--datadog-mcp-site",
        "--datadog-mcp-url",
        "--datadog-mcp-toolsets",
        "--datadog-mcp-redirect-uri",
        "--datadog-api-key",
        "--datadog-application-key",
      ]),
    );

    const tools = mockPi.registerTool.mock.calls.map(([tool]) => tool.name);
    expect(tools).toEqual(
      expect.arrayContaining([
        "datadog_mcp_connect",
        "datadog_mcp_disconnect",
        "datadog_mcp_status",
      ]),
    );
    expect(mockPi.registerCommand).toHaveBeenCalledWith("datadog-mcp", expect.any(Object));
  });
});
