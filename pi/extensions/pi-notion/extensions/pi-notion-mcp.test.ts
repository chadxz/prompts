import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import notionMCPClientExtension, {
  buildAuthorizationUrl,
  buildHtmlResponse,
  coerceNumericProperties,
  connectWithSavedConfig,
  countOutputLines,
  createNotionToolRenderer,
  createPkceChallenge,
  createRegisteredToolDefinition,
  createRegisteredToolExecutor,
  createUiNotifier,
  disconnectClient,
  ensureConnected,
  FileTokenStorage,
  finalizeConnection,
  getConnectedStatusMessage,
  getConnectionStatusText,
  getDefaultAuthFilePath,
  NotionMCPClient,
  renderNotionToolCall,
  renderNotionToolResult,
  resolveAccessToken,
  resolveCallbackResult,
  SKILLS_DIRECTORY,
  startOAuthCallbackServer,
  storage,
  toolError,
  toolResult,
  truncateDisplayText,
} from "./pi-notion-mcp.js";

const testTheme = {
  fg: (_token: string, text: string) => text,
  bold: (text: string) => text,
} as never;

describe("pi-notion-mcp.ts", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("builds HTML responses, resolves callback results, and creates PKCE auth URLs", () => {
    const html = "<html>ok</html>";
    expect(buildHtmlResponse("HTTP/1.1 200 OK", html)).toContain(html);

    expect(resolveCallbackResult(new URLSearchParams("state=bad"), "expected").result.error).toBe("State mismatch");
    expect(
      resolveCallbackResult(new URLSearchParams("state=expected&error=denied&error_description=nope"), "expected")
        .result,
    ).toMatchObject({ error: "denied", errorDescription: "nope" });
    expect(
      resolveCallbackResult(new URLSearchParams("state=expected&access_token=token-123"), "expected").result,
    ).toMatchObject({ accessToken: "token-123" });
    expect(resolveCallbackResult(new URLSearchParams("state=expected&code=code-123"), "expected").result).toMatchObject({
      code: "code-123",
    });

    const { codeVerifier, codeChallenge } = createPkceChallenge();
    expect(codeVerifier).toBeTruthy();
    expect(codeChallenge).toBeTruthy();

    const url = buildAuthorizationUrl({ client_id: "client-1" }, "http://localhost:3333/callback", codeChallenge, "state-1");
    expect(url).toContain("client_id=client-1");
    expect(url).toContain("code_challenge_method=S256");
    expect(url).toContain("prompt=consent");
  });

  it("coerces numeric properties and formats tool results", () => {
    const coerced = coerceNumericProperties({
      properties: {
        limit: "5",
        nested: { value: "3" },
      },
      list: ["1", { properties: { count: "2" } }],
    }) as {
      properties: { limit: number; nested: { value: string } };
      list: Array<string | { properties: { count: number } }>;
    };

    expect(coerced.properties.limit).toBe(5);
    expect(coerced.properties.nested.value).toBe("3");
    expect(coerced.list[0]).toBe("1");
    expect((coerced.list[1] as { properties: { count: number } }).properties.count).toBe(2);

    expect(countOutputLines("line 1\n\nline 2")).toBe(2);
    expect(truncateDisplayText("x".repeat(90))).toHaveLength(84);

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

  it("renders compact summaries for Notion tool calls and results", () => {
    const renderedCall = renderNotionToolCall(
      "notion-search",
      {
        query: "quarterly roadmap",
        content_search_mode: "workspace_search",
        query_type: "internal",
        page_size: 25,
      },
      testTheme,
    );
    const renderedResult = renderNotionToolResult(
      "notion-search",
      {
        query: "quarterly roadmap",
        content_search_mode: "workspace_search",
        query_type: "internal",
        page_size: 25,
      },
      {
        content: [{ type: "text", text: "<page>very long hidden body</page>" }],
        details: {
          tool: "notion-search",
          lineCount: 24,
          characterCount: 5120,
        },
      },
      { expanded: true, isPartial: false },
      testTheme,
      { isError: false },
    );

    expect(renderedCall.render(160).join("\n")).toContain(
      "notion-search quarterly roadmap (mode=workspace_search, type=internal)",
    );
    expect(renderedResult.render(160).join("\n")).toContain(
      "Search complete (24 lines, 5,120 chars)",
    );
    expect(renderedResult.render(160).join("\n")).toContain("query: quarterly roadmap");
    expect(renderedResult.render(160).join("\n")).not.toContain("very long hidden body");

    expect(
      renderNotionToolResult(
        "notion-fetch",
        { id: "https://www.notion.so/page-1" },
        { content: [], details: {} },
        { expanded: false, isPartial: true },
        testTheme,
        { isError: false },
      )
        .render(120)
        .join("\n"),
    ).toContain("Fetching Notion content...");

    expect(
      renderNotionToolResult(
        "notion-fetch",
        { id: "https://www.notion.so/page-1" },
        { content: [{ type: "text", text: "something blew up badly" }], details: {} },
        { expanded: false, isPartial: false },
        testTheme,
        { isError: true },
      )
        .render(120)
        .join("\n"),
    ).toContain("something blew up badly");

    const mcpRenderer = createNotionToolRenderer("notion_mcp_status");
    const renderedStatus = mcpRenderer
      .renderResult?.(
        {
          content: [{ type: "text", text: "Notion MCP Status:\nAvailable tools:\n- notion-search" }],
          details: {
            connected: true,
            toolCount: 1,
            sessionId: "session-12345678",
            mcpUrl: "https://mcp.notion.com/mcp",
          },
        },
        { expanded: true, isPartial: false },
        testTheme,
        { args: {}, isError: false },
      )
      ?.render(160)
      .join("\n");

    expect(renderedStatus).toContain("Connected (1 tool)");
    expect(renderedStatus).toContain("url: https://mcp.notion.com/mcp");
    expect(renderedStatus).not.toContain("Available tools");
  });

  it("connects, discovers tools, formats status, and calls tools", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json", "mcp-session-id": "session-12345678" }),
        json: async () => ({ result: { ok: true } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ result: { tools: [{ name: "notion-search", description: "Search", inputSchema: {} }] } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
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

    const client = new NotionMCPClient();
    await client.connect("https://mcp.notion.com/mcp", "token-123");

    expect(client.state.connected).toBe(true);
    expect(client.getTools()).toHaveLength(1);
    expect(getConnectionStatusText(client)).toContain("Connected: Yes");
    expect(getConnectedStatusMessage(client)).toContain("Connected to Notion MCP");

    const result = await client.callTool("https://mcp.notion.com/mcp", "notion-search", { properties: { count: "2" } });
    expect(result).toContain("hello");
    expect(fetchMock).toHaveBeenCalledWith("https://mcp.notion.com/mcp", expect.objectContaining({ method: "POST" }));

    await client.disconnect();
    expect(client.state.connected).toBe(false);
  });

  it("handles SSE responses, request failures, and access token resolution", async () => {
    const client = new NotionMCPClient();
    const notify = vi.fn();

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "text/event-stream", "mcp-session-id": "session-sse" }),
        text: async () => 'data: {"result":{"ok":true}}\n',
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "text/event-stream" }),
        text: async () => 'data: {"result":{"tools":[]}}\n',
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "text/event-stream" }),
        text: async () => 'data: {"result":{"content":[{"type":"text","text":"from sse"}]}}\n',
      }) as typeof fetch;

    await client.connect("https://mcp.notion.com/mcp", "token-123");
    expect(await client.callTool("https://mcp.notion.com/mcp", "demo", {})).toContain("from sse");

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      headers: new Headers({ "content-type": "text/plain" }),
      text: async () => "boom",
    }) as typeof fetch;

    await expect(client.callTool("https://mcp.notion.com/mcp", "demo", {})).rejects.toThrow("HTTP 500: boom");

    await expect(
      resolveAccessToken(
        { accessToken: "direct-token" },
        "http://localhost/callback",
        "verifier",
        { client_id: "client" },
        notify,
      ),
    ).resolves.toMatchObject({ accessToken: "direct-token" });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        access_token: "exchanged-token",
        refresh_token: "refresh-token",
        token_type: "bearer",
        expires_in: 3600,
      }),
    }) as typeof fetch;

    await expect(
      resolveAccessToken(
        { code: "code-123" },
        "http://localhost/callback",
        "verifier",
        { client_id: "client" },
        notify,
      ),
    ).resolves.toMatchObject({
      accessToken: "exchanged-token",
      refreshToken: "refresh-token",
      tokenType: "bearer",
    });
    expect(notify).toHaveBeenCalledWith("Exchanging authorization code for token...");
    await expect(
      resolveAccessToken({ error: "denied" }, "http://localhost/callback", "verifier", { client_id: "client" }, notify),
    ).rejects.toThrow("Authorization failed: denied");
  });

  it("refreshes saved credentials before connect and retries 401 tool calls", async () => {
    const client = new NotionMCPClient();
    const saveSpy = vi.spyOn(storage, "save").mockResolvedValue();

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          access_token: "refreshed-token",
          refresh_token: "refresh-2",
          token_type: "bearer",
          expires_in: 3600,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json", "mcp-session-id": "session-refresh" }),
        json: async () => ({ result: { ok: true } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ result: { tools: [] } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => "",
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "text/plain" }),
        text: async () => "invalid_token",
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          access_token: "refreshed-token-2",
          refresh_token: "refresh-3",
          token_type: "bearer",
          expires_in: 3600,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ result: { content: [{ type: "text", text: "after refresh" }] } }),
      }) as typeof fetch;

    await client.connect("https://mcp.notion.com/mcp", "expired-token", {
      mcpUrl: "https://mcp.notion.com/mcp",
      accessToken: "expired-token",
      refreshToken: "refresh-1",
      clientId: "client-1",
      clientSecret: "secret-1",
      expiresAt: Date.now() - 1000,
    });

    expect(saveSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        accessToken: "refreshed-token",
        refreshToken: "refresh-2",
      }),
    );

    await expect(client.callTool("https://mcp.notion.com/mcp", "demo", {})).resolves.toContain("after refresh");
    expect(saveSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        accessToken: "refreshed-token-2",
        refreshToken: "refresh-3",
      }),
    );
  });

  it("creates registered tool executors and definitions with compact renderers", async () => {
    const disconnectedClient = new NotionMCPClient();
    const disconnectedExecute = createRegisteredToolExecutor(disconnectedClient, "https://mcp.notion.com/mcp", {
      name: "notion-search",
      description: "Search",
      inputSchema: {},
    });
    const disconnectedResult = await disconnectedExecute("id", {}, new AbortController().signal, undefined, undefined);
    expect(disconnectedResult.isError).toBe(true);

    const connectedClient = new NotionMCPClient();
    connectedClient.state.connected = true;
    vi.spyOn(connectedClient, "callTool").mockResolvedValue("done");
    const execute = createRegisteredToolExecutor(connectedClient, "https://mcp.notion.com/mcp", {
      name: "notion-search",
      description: "Search",
      inputSchema: {},
    });
    const onUpdate = vi.fn();
    const success = await execute("id", { query: "docs" }, new AbortController().signal, onUpdate, undefined);
    expect(onUpdate).toHaveBeenCalledWith({
      content: [{ type: "text", text: "Running notion-search..." }],
      details: { tool: "notion-search", phase: "running" },
    });
    expect(success).toEqual({
      content: [{ type: "text", text: "done" }],
      details: { tool: "notion-search", lineCount: 1, characterCount: 4 },
    });

    const definition = createRegisteredToolDefinition(connectedClient, "https://mcp.notion.com/mcp", {
      name: "notion-fetch",
      description: "Fetch",
      inputSchema: {},
    });
    expect(definition.renderCall?.({ id: "https://www.notion.so/page-1" }, testTheme, {})?.render(160).join("\n")).toContain(
      "notion-fetch https://www.notion.so/page-1",
    );
  });

  it("resolves auth file paths from defaults, env vars, and migrated legacy files", () => {
    const originalHome = process.env.HOME;
    const originalFile = process.env.NOTION_MCP_AUTH_FILE;
    const originalLegacy = process.env.NOTION_MCP_AUTH;
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const tempHome = mkdtempSync(join(tmpdir(), "pi-notion-auth-home-"));
    const legacyDir = join(tempHome, ".pi", "agent", "extensions");

    mkdirSync(legacyDir, { recursive: true });
    writeFileSync(
      join(legacyDir, "notion-mcp-auth.json"),
      JSON.stringify({ mcpUrl: "https://mcp.notion.com/mcp", accessToken: "token-123" }),
      "utf-8",
    );

    delete process.env.NOTION_MCP_AUTH_FILE;
    delete process.env.NOTION_MCP_AUTH;
    process.env.HOME = tempHome;

    try {
      expect(getDefaultAuthFilePath()).toBe(join(tempHome, ".pi", "agent", "notion-mcp-auth.json"));
      expect(existsSync(join(legacyDir, "notion-mcp-auth.json"))).toBe(false);
      expect(existsSync(join(tempHome, ".pi", "agent", "notion-mcp-auth.json"))).toBe(true);

      process.env.NOTION_MCP_AUTH_FILE = "~/custom-notion-auth.json";
      expect(getDefaultAuthFilePath()).toContain("custom-notion-auth.json");

      delete process.env.NOTION_MCP_AUTH_FILE;
      process.env.NOTION_MCP_AUTH = "~/legacy-notion-auth.json";
      expect(getDefaultAuthFilePath()).toContain("legacy-notion-auth.json");
      expect(warnSpy).toHaveBeenCalledWith("[pi-notion] NOTION_MCP_AUTH is deprecated; use NOTION_MCP_AUTH_FILE.");
    } finally {
      if (originalHome) process.env.HOME = originalHome;
      else delete process.env.HOME;
      if (originalFile) process.env.NOTION_MCP_AUTH_FILE = originalFile;
      else delete process.env.NOTION_MCP_AUTH_FILE;
      if (originalLegacy) process.env.NOTION_MCP_AUTH = originalLegacy;
      else delete process.env.NOTION_MCP_AUTH;
    }
  });

  it("persists token storage and uses notifier/connection helpers", async () => {
    const dir = mkdtempSync(join(tmpdir(), "pi-notion-mcp-storage-"));
    const tokenStorage = new FileTokenStorage();
    (tokenStorage as unknown as { path: string }).path = join(dir, "notion-mcp-auth.json");

    await tokenStorage.save({ mcpUrl: "https://mcp.notion.com/mcp", accessToken: "token-123" });
    expect(await tokenStorage.load()).toMatchObject({ accessToken: "token-123" });
    await tokenStorage.clear();
    expect(await tokenStorage.load()).toBeNull();

    const emit = vi.fn();
    const notify = createUiNotifier({ events: { emit } } as never);
    notify("hello");
    expect(emit).toHaveBeenCalledWith("ui:notify", { message: "hello", type: "info" });

    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const fallbackNotify = createUiNotifier({
      events: {
        emit: vi.fn(() => {
          throw new Error("no ui");
        }),
      },
    } as never);
    fallbackNotify("fallback message", "error");
    expect(logSpy).toHaveBeenCalledWith("[pi-notion] fallback message");
  });

  it("reuses or clears saved config and finalizes new connections", async () => {
    const client = new NotionMCPClient();
    const notify = vi.fn();
    const registerTools = vi.fn();

    vi.spyOn(storage, "load").mockResolvedValueOnce({ mcpUrl: "https://mcp.notion.com/mcp", accessToken: "token-123" });
    vi.spyOn(client, "connect").mockResolvedValueOnce();
    expect(await connectWithSavedConfig(client, notify)).toBe(true);

    const failingClient = new NotionMCPClient();
    vi.spyOn(storage, "load").mockResolvedValueOnce({ mcpUrl: "https://mcp.notion.com/mcp", accessToken: "token" });
    vi.spyOn(failingClient, "connect").mockRejectedValueOnce(new Error("HTTP 401: invalid_token"));
    const clearSpy = vi.spyOn(storage, "clear").mockResolvedValueOnce();
    expect(await connectWithSavedConfig(failingClient, notify)).toBe(false);
    expect(notify).toHaveBeenCalledWith("Connection failed: HTTP 401: invalid_token", "error");
    expect(clearSpy).toHaveBeenCalled();

    const finalizedClient = new NotionMCPClient();
    vi.spyOn(finalizedClient, "connect").mockResolvedValue();
    const saveSpy = vi.spyOn(storage, "save").mockResolvedValue();
    await finalizeConnection(
      finalizedClient,
      { client_id: "client-1", client_secret: "secret-1" },
      {
        accessToken: "token-123",
        refreshToken: "refresh-123",
        tokenType: "bearer",
        expiresAt: Date.now() + 3600 * 1000,
      },
      registerTools,
      vi.fn(),
    );
    expect(saveSpy).toHaveBeenCalled();
    expect(registerTools).toHaveBeenCalled();

    const reuseClient = new NotionMCPClient();
    vi.spyOn(storage, "load").mockResolvedValueOnce({ mcpUrl: "https://mcp.notion.com/mcp", accessToken: "token-123" });
    vi.spyOn(reuseClient, "connect").mockResolvedValueOnce();
    expect(await ensureConnected(reuseClient, vi.fn(), vi.fn())).toEqual({ reusedSavedConfig: true });

    const disconnected = new NotionMCPClient();
    disconnected.state.connected = true;
    vi.spyOn(disconnected, "disconnect").mockResolvedValueOnce();
    const disconnectClearSpy = vi.spyOn(storage, "clear").mockResolvedValueOnce();
    await disconnectClient(disconnected);
    expect(disconnectClearSpy).toHaveBeenCalled();
  });

  it("registers flags, tools, commands, guardrails, and reports disconnected status", async () => {
    const mockPi = {
      registerFlag: vi.fn(),
      getFlag: vi.fn(() => undefined),
      registerTool: vi.fn(),
      registerCommand: vi.fn(),
      getAllTools: vi.fn(() => []),
      on: vi.fn(),
      events: { emit: vi.fn() },
    };

    notionMCPClientExtension(mockPi as never);

    const flags = mockPi.registerFlag.mock.calls.map(([name]) => name);
    expect(flags).toEqual(expect.arrayContaining(["--notion-mcp-auth-file", "--notion-mcp-auth"]));

    const tools = mockPi.registerTool.mock.calls.map(([tool]) => tool.name);
    expect(tools).toEqual(expect.arrayContaining(["notion_mcp_connect", "notion_mcp_disconnect", "notion_mcp_status"]));
    expect(mockPi.registerCommand).toHaveBeenCalledWith("notion", expect.any(Object));

    const resourceDiscoverHandler = mockPi.on.mock.calls.find(([event]) => event === "resources_discover")?.[1] as
      | ((...args: unknown[]) => Promise<{ skillPaths?: string[] }>)
      | undefined;
    await expect(resourceDiscoverHandler?.({}, {})).resolves.toEqual({
      skillPaths: [SKILLS_DIRECTORY],
    });

    const toolCallHandler = mockPi.on.mock.calls.find(([event]) => event === "tool_call")?.[1] as
      | ((...args: unknown[]) => Promise<void>)
      | undefined;
    const notify = vi.fn();
    await toolCallHandler?.({ toolName: "mcp__notion-search", input: { query: "meeting notes" } }, { ui: { notify } });
    expect(notify).toHaveBeenCalledWith(
      expect.stringContaining("content_search_mode is not 'workspace_search'"),
      "warning",
    );

    const statusTool = mockPi.registerTool.mock.calls.map(([tool]) => tool).find((tool) => tool.name === "notion_mcp_status");
    const result = await statusTool.execute("id", {}, new AbortController().signal, undefined, undefined);
    expect(result.content[0].text).toContain("Connected: No");
  });

  it("supports the deprecated auth-file flag alias with a warning", () => {
    const originalConfigFile = process.env.NOTION_MCP_AUTH_FILE;
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const mockPi = {
      registerFlag: vi.fn(),
      getFlag: vi.fn((flag: string) => (flag === "--notion-mcp-auth" ? "~/legacy-auth.json" : undefined)),
      registerTool: vi.fn(),
      registerCommand: vi.fn(),
      getAllTools: vi.fn(() => []),
      on: vi.fn(),
      events: { emit: vi.fn() },
    };

    try {
      notionMCPClientExtension(mockPi as never);
      expect(process.env.NOTION_MCP_AUTH_FILE).toBe("~/legacy-auth.json");
      expect(warnSpy).toHaveBeenCalledWith("[pi-notion] --notion-mcp-auth is deprecated; use --notion-mcp-auth-file.");
    } finally {
      if (originalConfigFile) process.env.NOTION_MCP_AUTH_FILE = originalConfigFile;
      else delete process.env.NOTION_MCP_AUTH_FILE;
    }
  });

  it("runs the OAuth callback server end-to-end", async () => {
    const state = "state-123";
    const server = await startOAuthCallbackServer(4300, state, 5000);

    await fetch(`http://127.0.0.1:${server.port}/callback?state=${state}&code=auth-code`);
    await expect(server.result).resolves.toEqual({ code: "auth-code" });
  });
});
