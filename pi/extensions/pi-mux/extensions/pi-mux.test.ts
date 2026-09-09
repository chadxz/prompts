import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import piMuxExtension, {
  buildMuxStatusCommandMessage,
  buildMuxToolsCommandMessage,
  buildToolId,
  CALL_TOOL_TOOL_NAME,
  CatalogStorage,
  createToolTextResult,
  EmbeddedExtensionHost,
  EmbeddedProviderAdapter,
  findCatalogTools,
  FIND_TOOLS_TOOL_NAME,
  GET_TOOL_DETAILS_TOOL_NAME,
  loadEmbeddedProviderDefinitions,
  MuxService,
  normalizeCatalogDescription,
  scoreCatalogEntry,
} from "./pi-mux.js";

const cleanupPaths = new Set<string>();

function registerMuxExtension() {
  const tools = new Map<string, Record<string, unknown>>();
  const commands = new Map<string, Record<string, unknown>>();

  piMuxExtension({
    on: () => undefined,
    registerCommand(name, command) {
      commands.set(name, command as never);
    },
    registerTool(tool) {
      tools.set(tool.name, tool as never);
    },
  } as never);

  return { tools, commands };
}

function registerMuxTools() {
  return registerMuxExtension().tools;
}

function renderToolCall(
  tool: Record<string, unknown>,
  args: Record<string, unknown>,
) {
  const component = (tool.renderCall as never)(
    args,
    {
      fg: (_token: string, text: string) => text,
      bold: (text: string) => text,
    },
    {},
  ) as { render(width: number): string[] };

  return component.render(200).join("\n").trimEnd();
}

function renderToolResult(
  tool: Record<string, unknown>,
  result: Record<string, unknown>,
  options: { expanded: boolean; isPartial?: boolean },
  context: { isError?: boolean } = {},
) {
  const component = (tool.renderResult as never)(
    result,
    {
      expanded: options.expanded,
      isPartial: options.isPartial ?? false,
    },
    {
      fg: (_token: string, text: string) => text,
      bold: (text: string) => text,
    },
    context,
  ) as { render(width: number): string[] };

  return component.render(200).join("\n").trimEnd();
}

afterEach(() => {
  for (const path of cleanupPaths) {
    rmSync(path, { recursive: true, force: true });
  }
  cleanupPaths.clear();
});

describe("tool constants", () => {
  it("exports the stable three-tool surface", () => {
    expect(FIND_TOOLS_TOOL_NAME).toBe("find_tools");
    expect(GET_TOOL_DETAILS_TOOL_NAME).toBe("get_tool_details");
    expect(CALL_TOOL_TOOL_NAME).toBe("call_tool");
  });
});

describe("catalog search helpers", () => {
  const entries = [
    {
      toolId: buildToolId("datadog", "search_datadog_logs"),
      provider: "datadog",
      nativeToolName: "search_datadog_logs",
      name: "Datadog Log Search",
      description: "Search Datadog logs",
      discoveryDescription: normalizeCatalogDescription("Search Datadog logs for incidents and errors."),
      available: true,
      inputSchema: {},
    },
    {
      toolId: buildToolId("slack", "slack_search_public"),
      provider: "slack",
      nativeToolName: "slack_search_public",
      name: "Slack Search Public",
      description: "Search public Slack channels",
      discoveryDescription: normalizeCatalogDescription("Search public Slack channels."),
      available: false,
      inputSchema: {},
    },
  ] as const;

  it("scores exact and near-exact tool name matches highly", () => {
    expect(scoreCatalogEntry(entries[0], "search_datadog_logs")).toBeGreaterThan(
      scoreCatalogEntry(entries[0], "facts"),
    );
    expect(scoreCatalogEntry(entries[1], "slack")).toBeGreaterThan(0);
  });

  it("sorts by score first and availability second", () => {
    const results = findCatalogTools(entries as never, "search", 10);
    expect(results.map((entry) => entry.toolId)).toEqual([
      "datadog/search_datadog_logs",
      "slack/slack_search_public",
    ]);
  });
});

describe("EmbeddedExtensionHost", () => {
  it("supports dynamic tool registration through embedded commands and tools", async () => {
    const host = new EmbeddedExtensionHost("fake-provider.ts", (pi) => {
      let connected = false;

      const registerDiscoveredTool = () => {
        pi.registerTool({
          name: "demo_tool",
          description: "A discovered tool",
          parameters: {
            type: "object",
            properties: { value: { type: "string" } },
            required: ["value"],
            additionalProperties: false,
          },
          async execute(_toolCallId, params) {
            return {
              content: [{ type: "text", text: `value:${(params as { value: string }).value}` }],
              details: { connected },
            };
          },
        });
      };

      pi.on("session_start", async () => {
        if (connected) {
          registerDiscoveredTool();
        }
      });

      pi.registerCommand("demo", {
        async handler(args, ctx) {
          if (args.trim() === "connect") {
            connected = true;
            registerDiscoveredTool();
            ctx.ui.notify("connected", "info");
          }
        },
      });

      pi.registerTool({
        name: "demo_mcp_status",
        description: "status",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: connected ? "connected" : "disconnected" }],
            details: { connected },
          };
        },
      });
    });

    await host.runSessionStart();
    expect(host.getRegisteredTools().map((tool) => tool.name)).toEqual([
      "demo_mcp_status",
    ]);

    await host.executeCommand(
      "demo",
      "connect",
      {
        ui: {
          notify: () => undefined,
          setStatus: () => undefined,
          setWidget: () => undefined,
          select: async () => undefined,
          confirm: async () => false,
          input: async () => undefined,
          editor: async () => undefined,
          setTitle: () => undefined,
          setEditorText: () => undefined,
          getEditorText: () => "",
        },
        hasUI: true,
        cwd: process.cwd(),
      } as never,
    );

    const toolNames = host.getRegisteredTools().map((tool) => tool.name);
    expect(toolNames).toContain("demo_tool");

    const result = await host.executeTool("demo_tool", { value: "abc" });
    expect(result).toEqual({
      content: [{ type: "text", text: "value:abc" }],
      details: { connected: true },
    });
  });

  it("bridges provider flags back to the real extension API", async () => {
    const values = new Map<string, boolean | string | undefined>([["--demo-flag", "from-real-pi"]]);
    const host = new EmbeddedExtensionHost(
      "fake-provider.ts",
      (pi) => {
        pi.registerFlag("--demo-flag", {
          default: "from-provider-default",
        });

        pi.registerTool({
          name: "read_flag",
          description: "Reads a bridged flag",
          parameters: { type: "object", properties: {} },
          async execute() {
            return {
              content: [{ type: "text", text: String(pi.getFlag("--demo-flag")) }],
              details: { value: pi.getFlag("--demo-flag") as string },
            };
          },
        });
      },
      {
        registerFlag(name) {
          values.set(name, values.get(name));
        },
        getFlag(name) {
          return values.get(name);
        },
      } as never,
    );

    await expect(host.executeTool("read_flag", {})).resolves.toEqual({
      content: [{ type: "text", text: "from-real-pi" }],
      details: { value: "from-real-pi" },
    });
  });

  it("runs embedded tool_call handlers and forwards signal and updates", async () => {
    const host = new EmbeddedExtensionHost("fake-provider.ts", (pi) => {
      pi.on("tool_call", async (event) => {
        if (event.toolName === "demo_tool") {
          event.input.value = `${String(event.input.value)}-mutated`;
        }
      });

      pi.registerTool({
        name: "demo_tool",
        description: "A tool with updates",
        parameters: {
          type: "object",
          properties: { value: { type: "string" } },
        },
        async execute(_toolCallId, params, signal, onUpdate) {
          onUpdate?.({
            content: [{ type: "text", text: "update" }],
            details: { signalForwarded: Boolean(signal) },
          });
          return {
            content: [{ type: "text", text: String((params as { value: string }).value) }],
            details: { aborted: signal?.aborted ?? false },
          };
        },
      });
    });

    const controller = new AbortController();
    const updates: Array<{ content: Array<{ type: "text"; text: string }>; details?: Record<string, unknown> }> = [];
    const result = await host.executeTool(
      "demo_tool",
      { value: "abc" },
      controller.signal,
      (payload) => {
        updates.push(payload);
      },
    );

    expect(updates).toEqual([
      {
        content: [{ type: "text", text: "update" }],
        details: { signalForwarded: true },
      },
    ]);
    expect(result).toEqual({
      content: [{ type: "text", text: "abc-mutated" }],
      details: { aborted: false },
    });
  });

  it("blocks execution when an embedded tool_call handler returns block=true", async () => {
    const host = new EmbeddedExtensionHost("fake-provider.ts", (pi) => {
      pi.on("tool_call", async () => ({
        block: true,
        reason: "blocked by test",
      }));

      pi.registerTool({
        name: "demo_tool",
        description: "A blocked tool",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: "should not run" }],
            details: {},
          };
        },
      });
    });

    await expect(host.executeTool("demo_tool", {})).rejects.toThrow("blocked by test");
  });
});

describe("EmbeddedProviderAdapter", () => {
  it("discovers the command and control tools from a normal extension", async () => {
    let connected = false;
    const host = new EmbeddedExtensionHost("fake-provider.ts", (pi) => {
      pi.registerCommand("demo", {
        async handler() {
          connected = true;
        },
      });

      pi.registerTool({
        name: "demo_mcp_connect",
        description: "connect",
        parameters: { type: "object", properties: {} },
        async execute() {
          if (!connected) {
            return {
              content: [{ type: "text", text: "Run /demo first." }],
              isError: true,
              details: { connected: false, requiresInteractiveSetup: true },
            };
          }

          return {
            content: [{ type: "text", text: "connected" }],
            details: { connected: true },
          };
        },
      });

      pi.registerTool({
        name: "demo_mcp_disconnect",
        description: "disconnect",
        parameters: { type: "object", properties: {} },
        async execute() {
          connected = false;
          return {
            content: [{ type: "text", text: "disconnected" }],
            details: { connected: false },
          };
        },
      });

      pi.registerTool({
        name: "demo_mcp_status",
        description: "status",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: connected ? "connected" : "disconnected" }],
            details: { connected },
          };
        },
      });

      pi.registerTool({
        name: "demo_tool",
        description: "A discovered tool",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: "ok" }],
            details: {},
          };
        },
      });
    });

    const adapter = new EmbeddedProviderAdapter("demo", host);
    expect(await adapter.isAvailable()).toBe(false);
    expect((await adapter.listTools()).map((tool) => tool.name)).toEqual(["demo_tool"]);

    await expect(
      adapter.connect({
        ui: {
          notify: () => undefined,
          setStatus: () => undefined,
          setWidget: () => undefined,
          select: async () => undefined,
          confirm: async () => false,
          input: async () => undefined,
          editor: async () => undefined,
          setTitle: () => undefined,
          setEditorText: () => undefined,
          getEditorText: () => "",
        },
        hasUI: true,
        cwd: process.cwd(),
      } as never),
    ).resolves.toBe("connected");
  });

  it("lets a provider override non-standard command and control names", async () => {
    let connected = false;
    const host = new EmbeddedExtensionHost("fake-provider.ts", (pi) => {
      pi.registerCommand("custom-provider", {
        async handler() {
          connected = true;
        },
      });

      pi.registerTool({
        name: "open_connection",
        description: "connect",
        parameters: { type: "object", properties: {} },
        async execute() {
          if (!connected) {
            return {
              content: [{ type: "text", text: "Run /custom-provider first." }],
              isError: true,
              details: { connected: false, requiresInteractiveSetup: true },
            };
          }

          return {
            content: [{ type: "text", text: "connected" }],
            details: { connected: true },
          };
        },
      });

      pi.registerTool({
        name: "close_connection",
        description: "disconnect",
        parameters: { type: "object", properties: {} },
        async execute() {
          connected = false;
          return {
            content: [{ type: "text", text: "disconnected" }],
            details: { connected: false },
          };
        },
      });

      pi.registerTool({
        name: "connection_status",
        description: "status",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: connected ? "connected" : "disconnected" }],
            details: { connected },
          };
        },
      });

      pi.registerTool({
        name: "regular_tool",
        description: "A discovered tool",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: "ok" }],
            details: {},
          };
        },
      });

      pi.registerTool({
        name: "inactive_tool",
        description: "A tool that should not stay discoverable",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: "inactive" }],
            details: {},
          };
        },
      });

      pi.setActiveTools([
        "open_connection",
        "close_connection",
        "connection_status",
        "regular_tool",
      ]);
    });

    const adapter = new EmbeddedProviderAdapter("custom", host, {
      commandName: "custom-provider",
      controls: {
        connect: "open_connection",
        disconnect: "close_connection",
        status: "connection_status",
      },
    });

    expect((await adapter.listTools()).map((tool) => tool.name)).toEqual(["regular_tool"]);
    expect(await adapter.isAvailable()).toBe(false);

    await expect(
      adapter.connect({
        ui: {
          notify: () => undefined,
          setStatus: () => undefined,
          setWidget: () => undefined,
          select: async () => undefined,
          confirm: async () => false,
          input: async () => undefined,
          editor: async () => undefined,
          setTitle: () => undefined,
          setEditorText: () => undefined,
          getEditorText: () => "",
        },
        hasUI: true,
        cwd: process.cwd(),
      } as never),
    ).resolves.toBe("connected");
    expect(await adapter.isAvailable()).toBe(true);
  });

  it("returns the provider status text", async () => {
    const host = new EmbeddedExtensionHost("fake-provider.ts", (pi) => {
      pi.registerTool({
        name: "demo_mcp_connect",
        description: "connect",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: "connected" }],
            details: { connected: true },
          };
        },
      });

      pi.registerTool({
        name: "demo_mcp_disconnect",
        description: "disconnect",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{ type: "text", text: "disconnected" }],
            details: { connected: false },
          };
        },
      });

      pi.registerTool({
        name: "demo_mcp_status",
        description: "status",
        parameters: { type: "object", properties: {} },
        async execute() {
          return {
            content: [{
              type: "text",
              text: "Demo MCP Status:\n- Connected: Yes\n- Toolsets: all",
            }],
            details: { connected: true },
          };
        },
      });
    });

    const adapter = new EmbeddedProviderAdapter("demo", host);
    await expect(adapter.getStatusText()).resolves.toBe(
      "Demo MCP Status:\n- Connected: Yes\n- Toolsets: all",
    );
  });
});

describe("dynamic provider discovery", () => {
  it("loads provider modules from providers/*/index.ts", async () => {
    const definitions = await loadEmbeddedProviderDefinitions();
    expect(definitions.map((definition) => definition.provider)).toEqual([
      "cloudflare",
      "datadog",
      "notion",
      "slack",
      "teams",
    ]);
  });
});

describe("MuxService", () => {
  function createProvider(overrides: Partial<{
    tools: Array<{
      name: string;
      label?: string;
      description: string;
      inputSchema: Record<string, unknown>;
      outputSchema?: Record<string, unknown>;
    }>;
    available: boolean;
    statusText: string;
    callResult: unknown;
  }> = {}) {
    return {
      async initialize() {
        return;
      },
      async listTools() {
        return overrides.tools ?? [];
      },
      async isAvailable() {
        return overrides.available ?? true;
      },
      async getStatusText() {
        return overrides.statusText ?? "";
      },
      async connect() {
        return "connected";
      },
      async disconnect() {
        return "disconnected";
      },
      async callTool() {
        return overrides.callResult ?? { content: [{ type: "text", text: "ok" }] };
      },
    };
  }

  function createService(
    providerOverrides: Record<string, ReturnType<typeof createProvider>>,
    storageState?: Record<string, unknown>,
  ) {
    const dir = mkdtempSync(join(tmpdir(), "pi-mux-test-"));
    cleanupPaths.add(dir);
    const storage = new CatalogStorage(join(dir, "mux-state.json"));
    if (storageState) {
      storage.save(storageState as never);
    }

    return new MuxService(providerOverrides as never, storage);
  }

  it("includes toolsets in the status overview when a provider reports them", async () => {
    const service = createService({
      datadog: createProvider({
        available: true,
        tools: [
          {
            name: "search_datadog_logs",
            description: "Search Datadog logs",
            inputSchema: { type: "object", properties: {} },
          },
        ],
        statusText: "Datadog MCP Status:\n- Connected: Yes\n- Toolsets: all (default)",
      }),
    });

    await expect(service.getStatusOverview()).resolves.toBe([
      "pi-mux provider status:",
      "- datadog: available (1 tool, toolsets: all (default))",
    ].join("\n"));
  });

  it("does not fall back to stale cached tools when a provider is available but currently exposes none", async () => {
    const service = createService(
      {
        slack: createProvider({ available: true, tools: [] }),
      },
      {
        toolsByProvider: {
          slack: [
            {
              name: "slack_search_public",
              description: "Search public Slack channels",
              inputSchema: { type: "object", properties: {} },
            },
          ],
        },
      },
    );

    await expect(service.getCatalogEntries()).resolves.toEqual([]);
  });

  it("surfaces cached tools as unavailable when a provider is disconnected", async () => {
    const service = createService(
      {
        slack: createProvider({ available: false, tools: [] }),
      },
      {
        toolsByProvider: {
          slack: [
            {
              name: "slack_search_public",
              description: "Search public Slack channels",
              inputSchema: { type: "object", properties: {} },
            },
          ],
        },
      },
    );

    const entries = await service.getCatalogEntries();
    const slackEntry = entries.find((entry) => entry.toolId === "slack/slack_search_public");
    expect(slackEntry).toMatchObject({
      toolId: "slack/slack_search_public",
      available: false,
    });
  });

  it("keeps the mux usable when one provider throws during catalog reads", async () => {
    const failingProvider = {
      ...createProvider(),
      async isAvailable() {
        throw new Error("boom");
      },
      async listTools() {
        throw new Error("boom");
      },
    } as never;

    const service = createService(
      {
        datadog: createProvider({
          tools: [
            {
              name: "search_datadog_logs",
              description: "Search Datadog logs",
              inputSchema: { type: "object", properties: {} },
            },
          ],
        }),
        slack: failingProvider,
      },
      {
        toolsByProvider: {
          slack: [
            {
              name: "slack_search_public",
              description: "Search public Slack channels",
              inputSchema: { type: "object", properties: {} },
            },
          ],
        },
      },
    );

    await expect(service.getCatalogEntries()).resolves.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          toolId: "datadog/search_datadog_logs",
          available: true,
        }),
        expect.objectContaining({
          toolId: "slack/slack_search_public",
          available: false,
        }),
      ]),
    );

    await expect(service.getStatusOverview()).resolves.toContain(
      "- slack: unavailable (1 tool)",
    );
  });

  it("returns details for known tools and throws for unknown tools", async () => {
    const service = createService({
      datadog: createProvider({
        tools: [
          {
            name: "search_datadog_logs",
            label: "Datadog Log Search",
            description: "Search Datadog logs",
            inputSchema: { type: "object", properties: {} },
          },
        ],
      }),
    });

    await expect(service.getToolDetails("datadog/search_datadog_logs")).resolves.toMatchObject({
      toolId: "datadog/search_datadog_logs",
      nativeToolName: "search_datadog_logs",
    });
    await expect(service.getToolDetails("datadog/missing")).rejects.toThrow(
      "Unknown tool_id 'datadog/missing'.",
    );
  });

  it("resolves repeated get_tool_details lookups from the runtime index", async () => {
    let isAvailableCalls = 0;
    let listToolsCalls = 0;

    const service = createService({
      datadog: {
        async initialize() {
          return;
        },
        async listTools() {
          listToolsCalls += 1;
          return [
            {
              name: "search_datadog_logs",
              description: "Search Datadog logs",
              inputSchema: { type: "object", properties: {} },
            },
          ];
        },
        async isAvailable() {
          isAvailableCalls += 1;
          return true;
        },
        async connect() {
          return "connected";
        },
        async disconnect() {
          return "disconnected";
        },
        async callTool() {
          return { content: [{ type: "text", text: "ok" }] };
        },
      },
    });

    await expect(service.getToolDetails("datadog/search_datadog_logs")).resolves.toMatchObject({
      toolId: "datadog/search_datadog_logs",
    });
    await expect(service.getToolDetails("datadog/search_datadog_logs")).resolves.toMatchObject({
      toolId: "datadog/search_datadog_logs",
    });

    expect(isAvailableCalls).toBe(1);
    expect(listToolsCalls).toBe(1);
  });

  it("returns unavailable errors for known but disconnected tools", async () => {
    const service = createService(
      {
        datadog: createProvider({
          available: false,
          tools: [
            {
              name: "search_datadog_logs",
              description: "Search Datadog logs",
              inputSchema: { type: "object", properties: {} },
            },
          ],
        }),
      },
      {
        toolsByProvider: {
          datadog: [
            {
              name: "search_datadog_logs",
              description: "Search Datadog logs",
              inputSchema: { type: "object", properties: {} },
            },
          ],
        },
      },
    );

    await expect(service.callTool("datadog/search_datadog_logs", {})).resolves.toEqual({
      ok: false,
      error: "Tool 'datadog/search_datadog_logs' is unavailable. Connect the provider with /mux connect datadog.",
    });
  });

  it("validates input and output schemas before reporting success", async () => {
    const service = createService({
      datadog: createProvider({
        tools: [
          {
            name: "search_datadog_logs",
            description: "Search Datadog logs",
            inputSchema: {
              type: "object",
              properties: { query: { type: "string" } },
              required: ["query"],
              additionalProperties: false,
            },
            outputSchema: {
              type: "object",
              properties: { ok: { const: true } },
              required: ["ok"],
              additionalProperties: false,
            },
          },
        ],
        callResult: { ok: true },
      }),
    });

    await expect(service.callTool("datadog/search_datadog_logs", {})).resolves.toEqual({
      ok: false,
      error: expect.stringContaining("Invalid arguments"),
    });

    await expect(service.callTool("datadog/search_datadog_logs", { query: "hello" })).resolves.toEqual({
      ok: true,
      result: { ok: true },
    });

    const structuredOutputService = createService({
      datadog: createProvider({
        tools: [
          {
            name: "search_datadog_logs",
            description: "Search Datadog logs",
            inputSchema: {
              type: "object",
              properties: { query: { type: "string" } },
              required: ["query"],
            },
            outputSchema: {
              type: "object",
              properties: { ok: { const: true } },
              required: ["ok"],
              additionalProperties: false,
            },
          },
        ],
        callResult: {
          structuredContent: { ok: true },
          content: [{ type: "text", text: "ok" }],
        },
      }),
    });

    await expect(
      structuredOutputService.callTool("datadog/search_datadog_logs", { query: "hello" }),
    ).resolves.toEqual({
      ok: true,
      result: {
        structuredContent: { ok: true },
        content: [{ type: "text", text: "ok" }],
      },
    });

    const invalidOutputService = createService({
      datadog: createProvider({
        tools: [
          {
            name: "search_datadog_logs",
            description: "Search Datadog logs",
            inputSchema: {
              type: "object",
              properties: { query: { type: "string" } },
              required: ["query"],
            },
            outputSchema: {
              type: "object",
              properties: { ok: { const: true } },
              required: ["ok"],
              additionalProperties: false,
            },
          },
        ],
        callResult: { ok: false },
      }),
    });

    await expect(
      invalidOutputService.callTool("datadog/search_datadog_logs", { query: "hello" }),
    ).resolves.toEqual({
      ok: false,
      error: expect.stringContaining("output schema"),
    });
  });

  it("treats upstream tool errors as mux errors", async () => {
    const service = createService({
      datadog: createProvider({
        tools: [
          {
            name: "search_datadog_logs",
            description: "Search Datadog logs",
            inputSchema: { type: "object", properties: {} },
          },
        ],
        callResult: {
          isError: true,
          content: [{ type: "text", text: "upstream failed" }],
        },
      }),
    });

    await expect(service.callTool("datadog/search_datadog_logs", {})).resolves.toEqual({
      ok: false,
      error: "upstream failed",
    });
  });

  it("finds tools through the mux catalog with normalized descriptions", async () => {
    const service = createService({
      datadog: createProvider({
        tools: [
          {
            name: "search_datadog_logs",
            label: "Datadog Log Search",
            description: "Search Datadog logs for docs and facts. Extra details that should not matter.",
            inputSchema: { type: "object", properties: {} },
          },
        ],
      }),
    });

    await expect(service.findTools("docs", 10)).resolves.toEqual([
      {
        tool_id: "datadog/search_datadog_logs",
        name: "search_datadog_logs",
        description: "Search Datadog logs for docs and facts.",
        available: true,
      },
    ]);
  });

  it("filters find_tools results to the requested provider and preserves omitted-provider behavior", async () => {
    const service = createService({
      datadog: createProvider({
        tools: [
          {
            name: "search_datadog_logs",
            description: "Search messages in Datadog logs",
            inputSchema: { type: "object", properties: {} },
          },
        ],
      }),
      slack: createProvider({
        tools: [
          {
            name: "slack_search_public",
            description: "Search messages in public Slack channels",
            inputSchema: { type: "object", properties: {} },
          },
        ],
      }),
    });

    await expect(service.findTools("search messages", 10, "slack")).resolves.toEqual([
      {
        tool_id: "slack/slack_search_public",
        name: "slack_search_public",
        description: "Search messages in public Slack channels",
        available: true,
      },
    ]);

    await expect(service.findTools("search messages", 10)).resolves.toEqual([
      {
        tool_id: "datadog/search_datadog_logs",
        name: "search_datadog_logs",
        description: "Search messages in Datadog logs",
        available: true,
      },
      {
        tool_id: "slack/slack_search_public",
        name: "slack_search_public",
        description: "Search messages in public Slack channels",
        available: true,
      },
    ]);
  });

  it("lists provider tools in stable tool-id order", async () => {
    const service = createService({
      datadog: createProvider({
        tools: [
          {
            name: "search_datadog_spans",
            description: "Search Datadog spans",
            inputSchema: { type: "object", properties: {} },
          },
          {
            name: "search_datadog_logs",
            description: "Search Datadog logs",
            inputSchema: { type: "object", properties: {} },
          },
        ],
      }),
    });

    await expect(service.listProviderTools("datadog")).resolves.toEqual([
      {
        tool_id: "datadog/search_datadog_logs",
        name: "search_datadog_logs",
        description: "Search Datadog logs",
        available: true,
      },
      {
        tool_id: "datadog/search_datadog_spans",
        name: "search_datadog_spans",
        description: "Search Datadog spans",
        available: true,
      },
    ]);
  });

  it("returns a clear validation error for an invalid find_tools provider", async () => {
    const service = createService({
      datadog: createProvider(),
      slack: createProvider(),
    });

    await expect(service.findTools("search", 10, "missing")).rejects.toThrow(
      "Invalid provider 'missing'. Allowed providers: datadog, slack.",
    );
  });

  it("refreshes cached catalog state on connect and disconnect", async () => {
    let connected = false;
    const service = createService({
      slack: {
        async initialize() {
          return;
        },
        async listTools() {
          return connected
            ? [
                {
                  name: "slack_search_public",
                  description: "Search messages in public Slack channels",
                  inputSchema: { type: "object", properties: {} },
                },
              ]
            : [];
        },
        async isAvailable() {
          return connected;
        },
        async connect() {
          connected = true;
          return "connected";
        },
        async disconnect() {
          connected = false;
          return "disconnected";
        },
        async callTool() {
          return { content: [{ type: "text", text: "ok" }] };
        },
      },
    });

    await expect(service.findTools("search messages", 10)).resolves.toEqual([]);

    await expect(service.connectProvider("slack", {} as never)).resolves.toBe("connected");
    await expect(service.findTools("search messages", 10)).resolves.toEqual([
      {
        tool_id: "slack/slack_search_public",
        name: "slack_search_public",
        description: "Search messages in public Slack channels",
        available: true,
      },
    ]);

    await expect(service.disconnectProvider("slack", {} as never)).resolves.toBe("disconnected");
    await expect(service.findTools("search messages", 10)).resolves.toEqual([
      {
        tool_id: "slack/slack_search_public",
        name: "slack_search_public",
        description: "Search messages in public Slack channels",
        available: false,
      },
    ]);
  });

  it("limits call_tool provider checks to the requested tool's provider", async () => {
    const calls = {
      datadog: { isAvailable: 0, listTools: 0, callTool: 0 },
      slack: { isAvailable: 0, listTools: 0, callTool: 0 },
    };

    const service = createService({
      datadog: {
        async initialize() {
          return;
        },
        async listTools() {
          calls.datadog.listTools += 1;
          return [
            {
              name: "search_datadog_logs",
              description: "Search Datadog logs",
              inputSchema: { type: "object", properties: {} },
            },
          ];
        },
        async isAvailable() {
          calls.datadog.isAvailable += 1;
          return true;
        },
        async connect() {
          return "connected";
        },
        async disconnect() {
          return "disconnected";
        },
        async callTool() {
          calls.datadog.callTool += 1;
          return { content: [{ type: "text", text: "ok" }] };
        },
      },
      slack: {
        async initialize() {
          return;
        },
        async listTools() {
          calls.slack.listTools += 1;
          return [
            {
              name: "slack_search_public",
              description: "Search Slack messages",
              inputSchema: { type: "object", properties: {} },
            },
          ];
        },
        async isAvailable() {
          calls.slack.isAvailable += 1;
          return true;
        },
        async connect() {
          return "connected";
        },
        async disconnect() {
          return "disconnected";
        },
        async callTool() {
          calls.slack.callTool += 1;
          return { content: [{ type: "text", text: "ok" }] };
        },
      },
    });

    await service.initialize();
    calls.datadog.isAvailable = 0;
    calls.datadog.listTools = 0;
    calls.datadog.callTool = 0;
    calls.slack.isAvailable = 0;
    calls.slack.listTools = 0;
    calls.slack.callTool = 0;

    await expect(service.callTool("slack/slack_search_public", {})).resolves.toEqual({
      ok: true,
      result: { content: [{ type: "text", text: "ok" }] },
    });

    expect(calls.datadog).toEqual({ isAvailable: 0, listTools: 0, callTool: 0 });
    expect(calls.slack).toEqual({ isAvailable: 1, listTools: 0, callTool: 1 });
  });
});

describe("command rendering", () => {
  it("appends usage text after the root /mux status output", () => {
    expect(
      buildMuxStatusCommandMessage(
        "pi-mux provider status:\n- datadog: available (1 tool, toolsets: all)",
        "Usage: /mux | /mux status | /mux help | /mux tools <provider> | /mux connect <provider> | /mux disconnect <provider>",
      ),
    ).toBe(
      "pi-mux provider status:\n- datadog: available (1 tool, toolsets: all)\n\nUsage: /mux | /mux status | /mux help | /mux tools <provider> | /mux connect <provider> | /mux disconnect <provider>",
    );
  });

  it("formats provider tool listings for the /mux tools command", () => {
    expect(buildMuxToolsCommandMessage("datadog", [
      {
        tool_id: "datadog/search_datadog_logs",
        name: "search_datadog_logs",
        description: "Search Datadog logs",
        available: true,
      },
      {
        tool_id: "datadog/search_datadog_spans",
        name: "search_datadog_spans",
        description: "Search Datadog spans",
        available: false,
      },
    ])).toBe([
      "pi-mux tools for datadog:",
      "- datadog/search_datadog_logs",
      "  name: search_datadog_logs",
      "  available: yes",
      "  description: Search Datadog logs",
      "- datadog/search_datadog_spans",
      "  name: search_datadog_spans",
      "  available: no",
      "  description: Search Datadog spans",
    ].join("\n"));
  });

  it("shows /mux help as an info message instead of a warning", async () => {
    const { commands } = registerMuxExtension();
    const command = commands.get("mux");
    expect(command).toBeDefined();
    if (!command) {
      throw new Error("mux command was not registered");
    }
    const handler = command.handler as never;

    const notifications: Array<{ message: string; type?: string }> = [];
    await handler(
      "help",
      {
        ui: {
          notify(message: string, type?: string) {
            notifications.push({ message, type });
          },
          setStatus: () => undefined,
          setWidget: () => undefined,
          select: async () => undefined,
          confirm: async () => false,
          input: async () => undefined,
          editor: async () => undefined,
          setTitle: () => undefined,
          setEditorText: () => undefined,
          getEditorText: () => "",
        },
        hasUI: true,
        cwd: process.cwd(),
      } as never,
    );

    expect(notifications).toEqual([
      {
        message:
          "Usage: /mux | /mux status | /mux help | /mux tools <provider> | /mux connect <provider> | /mux disconnect <provider>",
        type: "info",
      },
    ]);
  });
});

describe("tool rendering", () => {
  it("registers mux tools with prompt snippets and the find_tools provider filter", () => {
    const tools = registerMuxTools();
    const findTool = tools.get(FIND_TOOLS_TOOL_NAME);
    const detailsTool = tools.get(GET_TOOL_DETAILS_TOOL_NAME);
    const callTool = tools.get(CALL_TOOL_TOOL_NAME);
    expect(findTool).toBeDefined();
    expect(detailsTool).toBeDefined();
    expect(callTool).toBeDefined();

    expect(findTool?.description).toContain("pass provider to limit discovery to that exact provider");
    expect(findTool?.promptSnippet).toContain("Search installed provider tools for a task");
    expect(findTool?.promptSnippet).toContain(
      "Installed providers: cloudflare, datadog, notion, slack, teams.",
    );
    expect(findTool?.promptSnippet).toContain("If you already know the provider, pass provider to search only that provider");
    expect(findTool?.promptGuidelines).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Use find_tools first"),
        expect.stringContaining("pass the provider parameter to find_tools to search only that provider"),
      ]),
    );
    expect(findTool?.parameters).toMatchObject({
      properties: {
        query: expect.any(Object),
        provider: expect.any(Object),
        limit: expect.any(Object),
      },
    });

    expect(detailsTool?.promptSnippet).toContain("Inspect a discovered provider tool's description, availability, and input/output schemas");
    expect(detailsTool?.promptGuidelines).toEqual(
      expect.arrayContaining([
        expect.stringContaining("use get_tool_details before call_tool"),
      ]),
    );

    expect(callTool?.promptSnippet).toContain("Call a discovered provider tool by tool_id using arguments that match its input schema");
    expect(callTool?.promptGuidelines).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Only use call_tool after"),
        expect.stringContaining("do not call it"),
      ]),
    );
  });

  it("keeps find_tools compact when collapsed and shows full output when expanded", () => {
    const tools = registerMuxTools();
    const tool = tools.get(FIND_TOOLS_TOOL_NAME);
    expect(tool).toBeDefined();

    const result = createToolTextResult({
      results: [
        {
          tool_id: "slack/slack_search_public",
          name: "slack_search_public",
          description: "Search public Slack channels",
          available: true,
        },
        {
          tool_id: "datadog/search_datadog_logs",
          name: "search_datadog_logs",
          description: "Search Datadog logs",
          available: true,
        },
      ],
    });

    const collapsed = renderToolResult(tool as never, result as never, { expanded: false });
    expect(collapsed).toContain("2 tools found");
    expect(collapsed).toContain("ctrl+o");

    const expanded = renderToolResult(tool as never, result as never, { expanded: true });
    expect(expanded).toContain('"tool_id": "slack/slack_search_public"');
    expect(expanded).toContain('"tool_id": "datadog/search_datadog_logs"');

    const emptyResult = createToolTextResult({ results: [] });
    const emptyCollapsed = renderToolResult(tool as never, emptyResult as never, { expanded: false });
    expect(emptyCollapsed).toContain("No matching tools");
    expect(emptyCollapsed).toContain("ctrl+o");
  });

  it("keeps get_tool_details compact when collapsed and shows full output when expanded", () => {
    const tools = registerMuxTools();
    const tool = tools.get(GET_TOOL_DETAILS_TOOL_NAME);
    expect(tool).toBeDefined();

    const result = createToolTextResult({
      tool_id: "slack/slack_search_public",
      provider: "slack",
      name: "slack_search_public",
      description: "Search public Slack channels",
      available: true,
      input_schema: { type: "object", properties: { query: { type: "string" } } },
    });

    const collapsed = renderToolResult(tool as never, result as never, { expanded: false });
    expect(collapsed).toContain("slack/slack_search_public");
    expect(collapsed).toContain("available");
    expect(collapsed).toContain("1 input field");
    expect(collapsed).toContain("no output schema");
    expect(collapsed).toContain("ctrl+o");

    const expanded = renderToolResult(tool as never, result as never, { expanded: true });
    expect(expanded).toContain('"tool_id": "slack/slack_search_public"');
    expect(expanded).toContain('"input_schema"');
  });

  it("shows the call_tool arguments in the call display", () => {
    const tools = registerMuxTools();
    const tool = tools.get(CALL_TOOL_TOOL_NAME);
    expect(tool).toBeDefined();

    const callText = renderToolCall(tool as never, {
      tool_id: "datadog/search_datadog_logs",
      arguments: {
        query: "service:api status:error",
        limit: 25,
      },
    });

    expect(callText).toContain("call_tool datadog/search_datadog_logs");
    expect(callText).toContain('"query": "service:api status:error"');
    expect(callText).toContain('"limit": 25');
  });

  it("keeps call_tool compact when collapsed and shows full output when expanded", () => {
    const tools = registerMuxTools();
    const tool = tools.get(CALL_TOOL_TOOL_NAME);
    expect(tool).toBeDefined();

    const successResult = createToolTextResult({
      ok: true,
      result: {
        structuredContent: { answer: "done" },
      },
    });

    const collapsedSuccess = renderToolResult(tool as never, successResult as never, { expanded: false });
    expect(collapsedSuccess).toContain("Tool call succeeded");
    expect(collapsedSuccess).toContain("lines");
    expect(collapsedSuccess).toContain("chars");
    expect(collapsedSuccess).toContain("ctrl+o");
    expect(
      renderToolResult(tool as never, successResult as never, { expanded: true }),
    ).toContain('"structuredContent"');

    const errorResult = createToolTextResult({
      ok: false,
      error: "Datadog query failed because the time window was invalid.",
    });

    const collapsedError = renderToolResult(tool as never, errorResult as never, { expanded: false });
    expect(collapsedError).toContain("Datadog query failed because the time window was invalid.");
    expect(collapsedError).toContain("ctrl+o");
    expect(
      renderToolResult(tool as never, errorResult as never, { expanded: true }),
    ).toContain('"error": "Datadog query failed because the time window was invalid."');
  });
});

describe("tool result helpers", () => {
  it("wraps mux payloads as tool text results", () => {
    expect(createToolTextResult({ ok: true })).toEqual({
      content: [{ type: "text", text: JSON.stringify({ ok: true }, null, 2) }],
      details: { payload: { ok: true } },
    });
  });
});
