import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  checkNotionAuth,
  formatBlocks,
  formatDatabase,
  formatPage,
  formatSearch,
  getTitleFromProperties,
  loadConfig,
  registerNotionGuardrails,
  resolveConfigPath,
  toolChecks,
} from "./pi-notion.js";

afterEach(() => {
  vi.restoreAllMocks();
});

function createMockPi() {
  return {
    on: vi.fn(),
  };
}

function getEventHandler(mockPi: ReturnType<typeof createMockPi>, eventName: string) {
  const entry = mockPi.on.mock.calls.find(([event]) => event === eventName);
  return entry?.[1] as ((...args: unknown[]) => Promise<void>) | undefined;
}

async function withIsolatedAuthEnv<T>(
  run: (paths: { tempHome: string; tempProject: string }) => Promise<T> | T,
  options: { apiKey?: string; tempPrefix?: string } = {},
): Promise<T> {
  const originalHome = process.env.HOME;
  const originalApiKey = process.env.NOTION_API_KEY;
  const originalToken = process.env.NOTION_TOKEN;
  const originalMcpAuthFile = process.env.NOTION_MCP_AUTH_FILE;
  const originalLegacyMcpAuthFile = process.env.NOTION_MCP_AUTH;
  const originalCwd = process.cwd();
  const tempPrefix = options.tempPrefix ?? "pi-notion-auth";
  const tempHome = mkdtempSync(join(tmpdir(), `${tempPrefix}-home-`));
  const tempProject = mkdtempSync(join(tmpdir(), `${tempPrefix}-project-`));

  mkdirSync(join(tempHome, ".pi", "agent"), { recursive: true });
  mkdirSync(join(tempProject, ".pi"), { recursive: true });

  process.env.HOME = tempHome;
  process.chdir(tempProject);
  delete process.env.NOTION_MCP_AUTH_FILE;
  delete process.env.NOTION_MCP_AUTH;
  delete process.env.NOTION_TOKEN;

  if (options.apiKey) process.env.NOTION_API_KEY = options.apiKey;
  else delete process.env.NOTION_API_KEY;

  try {
    return await run({ tempHome, tempProject });
  } finally {
    process.chdir(originalCwd);
    if (originalHome) process.env.HOME = originalHome;
    else delete process.env.HOME;
    if (originalApiKey) process.env.NOTION_API_KEY = originalApiKey;
    else delete process.env.NOTION_API_KEY;
    if (originalToken) process.env.NOTION_TOKEN = originalToken;
    else delete process.env.NOTION_TOKEN;
    if (originalMcpAuthFile) process.env.NOTION_MCP_AUTH_FILE = originalMcpAuthFile;
    else delete process.env.NOTION_MCP_AUTH_FILE;
    if (originalLegacyMcpAuthFile) process.env.NOTION_MCP_AUTH = originalLegacyMcpAuthFile;
    else delete process.env.NOTION_MCP_AUTH;
  }
}

describe("pi-notion.ts utilities", () => {
  it("resolves config paths from home, absolute, and cwd-relative paths", () => {
    expect(resolveConfigPath("~/.pi/config.json")).toContain(join(homedir(), ".pi", "config.json"));
    expect(resolveConfigPath("~")).toBe(homedir());
    expect(resolveConfigPath("/absolute/path.json")).toBe("/absolute/path.json");
    expect(resolveConfigPath("relative/path.json")).toBe(resolve(process.cwd(), "relative/path.json"));
  });

  it("loads config files from disk and environment variables", () => {
    const base = mkdtempSync(join(tmpdir(), "pi-notion-config-"));
    const configPath = join(base, "notion.json");
    const envConfigPath = join(base, "env-notion.json");
    const originalConfigFile = process.env.NOTION_CONFIG_FILE;

    writeFileSync(configPath, JSON.stringify({ token: "local-token" }), "utf-8");
    writeFileSync(envConfigPath, JSON.stringify({ token: "env-token" }), "utf-8");
    process.env.NOTION_CONFIG_FILE = envConfigPath;

    try {
      expect(loadConfig(configPath)).toEqual({ token: "local-token" });
      expect(loadConfig(undefined)).toEqual({ token: "env-token" });
      expect(loadConfig(join(base, "missing.json"))).toBeNull();
    } finally {
      if (originalConfigFile) process.env.NOTION_CONFIG_FILE = originalConfigFile;
      else delete process.env.NOTION_CONFIG_FILE;
    }
  });

  it("supports the deprecated NOTION_CONFIG env alias with a warning", () => {
    const base = mkdtempSync(join(tmpdir(), "pi-notion-config-legacy-"));
    const configPath = join(base, "notion.json");
    const originalConfigFile = process.env.NOTION_CONFIG_FILE;
    const originalLegacyConfig = process.env.NOTION_CONFIG;
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    writeFileSync(configPath, JSON.stringify({ token: "legacy-token" }), "utf-8");
    delete process.env.NOTION_CONFIG_FILE;
    process.env.NOTION_CONFIG = configPath;

    try {
      expect(loadConfig(undefined)).toEqual({ token: "legacy-token" });
      expect(warnSpy).toHaveBeenCalledWith("[pi-notion] NOTION_CONFIG is deprecated; use NOTION_CONFIG_FILE.");
    } finally {
      if (originalConfigFile) process.env.NOTION_CONFIG_FILE = originalConfigFile;
      else delete process.env.NOTION_CONFIG_FILE;
      if (originalLegacyConfig) process.env.NOTION_CONFIG = originalLegacyConfig;
      else delete process.env.NOTION_CONFIG;
    }
  });

  it("extracts titles and formats pages, databases, blocks, and search results", () => {
    expect(getTitleFromProperties({ Name: { type: "title", title: [{ plain_text: "My Page" }] } })).toBe("My Page");
    expect(getTitleFromProperties({})).toBe("Untitled");

    expect(
      formatPage({
        id: "page-1",
        url: "https://notion.so/page-1",
        properties: { Name: { type: "title", title: [{ plain_text: "Page Title" }] } },
      }),
    ).toContain("Page Title");

    expect(
      formatDatabase({
        id: "db-1",
        title: [{ plain_text: "Database Title" }],
        properties: { Name: { type: "title" } },
      }),
    ).toContain("Database Title");

    expect(
      formatBlocks({
        results: [
          { type: "paragraph", paragraph: { text: [{ plain_text: "Hello" }] } },
          { type: "heading_1", heading_1: { text: [{ plain_text: "World" }] } },
        ],
      }),
    ).toContain("Hello");

    expect(formatBlocks({ results: [] })).toBe("No blocks found.");

    expect(
      formatSearch({
        results: [{ object: "page", id: "page-1", properties: { Name: { type: "title", title: [{ plain_text: "Search Result" }] } } }],
      }),
    ).toContain("Search Result");
    expect(formatSearch({ results: [] })).toBe("No results found.");
  });
});

describe("checkNotionAuth", () => {
  it("returns not authenticated when no config exists", async () => {
    const result = await withIsolatedAuthEnv(() => checkNotionAuth());
    expect(result.authenticated).toBe(false);
    expect(result.message).toContain("Not authenticated");
  });

  it("migrates the legacy MCP auth file to the new location", async () => {
    await withIsolatedAuthEnv(
      ({ tempHome }) => {
        const configDir = join(tempHome, ".pi", "agent", "extensions");
        const agentDir = join(tempHome, ".pi", "agent");

        mkdirSync(configDir, { recursive: true });
        writeFileSync(
          join(configDir, "notion-mcp.json"),
          JSON.stringify({ mcpUrl: "https://mcp.notion.com/mcp", accessToken: "token-123" }),
          "utf-8",
        );

        const result = checkNotionAuth();
        expect(result.authenticated).toBe(true);
        expect(existsSync(join(configDir, "notion-mcp.json"))).toBe(false);
        expect(existsSync(join(agentDir, "notion-mcp-auth.json"))).toBe(true);
      },
      { tempPrefix: "pi-notion-migrate" },
    );
  });

  it("treats expired MCP tokens with refresh support as reusable", async () => {
    await withIsolatedAuthEnv(({ tempHome }) => {
      const agentDir = join(tempHome, ".pi", "agent");

      writeFileSync(
        join(agentDir, "notion-mcp-auth.json"),
        JSON.stringify({
          mcpUrl: "https://mcp.notion.com/mcp",
          accessToken: "expired-token",
          refreshToken: "refresh-token",
          clientId: "client-123",
          expiresAt: Date.now() - 1000,
        }),
        "utf-8",
      );

      const result = checkNotionAuth();
      expect(result.authenticated).toBe(true);
      expect(result.message).toContain("will refresh automatically on next use");
    });
  });

  it("detects legacy API keys but still requires MCP OAuth", async () => {
    const result = await withIsolatedAuthEnv(() => checkNotionAuth(), { apiKey: "test-key" });
    expect(result.authenticated).toBe(false);
    expect(result.message).toContain("NOTION_API_KEY");
    expect(result.message).toContain("MCP OAuth is still required");
  });
});

describe("tool guardrails", () => {
  it("warns for incorrect notion-search inputs", () => {
    const warnings = toolChecks["notion-search"]({
      query: "meeting notes",
      content_search_mode: "ai_search",
    });
    expect(warnings.some((warning) => warning.includes("content_search_mode"))).toBe(true);
    expect(warnings.some((warning) => warning.includes("filters"))).toBe(true);
  });

  it("does not warn when notion-search omits content_search_mode", () => {
    const warnings = toolChecks["notion-search"]({ query: "meeting notes", filters: {} });
    expect(warnings.some((warning) => warning.includes("content_search_mode"))).toBe(false);
  });

  it("warns for raw notion-fetch ids and empty meeting note filters", () => {
    expect(toolChecks["notion-fetch"]({ id: "12345" })[0]).toContain("Prefer the 'url' field");
    expect(toolChecks["notion-query-meeting-notes"]({ filter: {} })[0]).toContain("Empty filter {} will fail");
  });

  it("returns no warnings for correctly configured inputs", () => {
    expect(
      toolChecks["notion-search"]({
        query: "docs",
        content_search_mode: "workspace_search",
        filters: {},
      }),
    ).toHaveLength(0);
    expect(toolChecks["notion-fetch"]({ id: "https://notion.so/page-1" })).toHaveLength(0);
    expect(toolChecks["notion-query-meeting-notes"]({ filter: { operator: "and", filters: [] } })).toHaveLength(0);
  });
});

describe("pi-notion.ts guardrail registration", () => {
  it("registers tool handlers", async () => {
    const mockPi = createMockPi();
    registerNotionGuardrails(mockPi as never);

    const toolCall = getEventHandler(mockPi, "tool_call");
    const notify = vi.fn();

    await toolCall?.(
      {
        toolName: "mcp__notion-search",
        input: { query: "meeting notes", content_search_mode: "ai_search" },
      },
      { ui: { notify } },
    );

    expect(notify).toHaveBeenCalledWith(
      expect.stringContaining("content_search_mode is not 'workspace_search'"),
      "warning",
    );
  });
});
