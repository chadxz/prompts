import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  keyHint,
  type ExtensionAPI,
  type ExtensionCommandContext,
  type ExtensionContext,
} from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type, type Static } from "@sinclair/typebox";
import Ajv, { type ValidateFunction } from "ajv";
import type { MuxProviderConfig, MuxProviderControls, MuxProviderFactory } from "../mux-provider.ts";

const PI_CODING_AGENT_DIR_ENV = "PI_CODING_AGENT_DIR";
const DEFAULT_PI_AGENT_DIR = "~/.pi/agent";
const MUX_STATE_FILE_NAME = "pi-mux-state.json";
const FIND_TOOLS_TOOL_NAME = "find_tools";
const GET_TOOL_DETAILS_TOOL_NAME = "get_tool_details";
const CALL_TOOL_TOOL_NAME = "call_tool";
const DEFAULT_FIND_LIMIT = 10;
const MAX_FIND_LIMIT = 50;

type ProviderName = string;
type NotifyLevel = "info" | "warning" | "error";

type TextContentBlock = {
  type: "text";
  text: string;
};

type UpstreamToolResult = {
  content: TextContentBlock[];
  details?: Record<string, unknown>;
  isError?: boolean;
};

type MuxToolCallResponse =
  | {
      ok: true;
      result: unknown;
    }
  | {
      ok: false;
      error: string;
    };

type ToolUpdateCallback = (
  payload: { content: TextContentBlock[]; details?: Record<string, unknown> },
) => void;

type EmbeddedToolDefinition = {
  name: string;
  label?: string;
  description?: string;
  parameters?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  execute?: (
    toolCallId: string,
    params: unknown,
    signal?: AbortSignal,
    onUpdate?: ToolUpdateCallback,
    ctx?: ExtensionContext,
  ) => Promise<UpstreamToolResult> | UpstreamToolResult;
};

type EmbeddedCommandDefinition = {
  description?: string;
  handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> | void;
};

type EmbeddedEventHandler = (
  event: unknown,
  ctx: ExtensionContext,
) => Promise<Record<string, unknown> | void> | Record<string, unknown> | void;

type EmbeddedProviderModuleDefinition = {
  provider: ProviderName;
  modulePath: string;
  extensionFactory: MuxProviderFactory;
  muxProvider: MuxProviderConfig;
};

type EmbeddedFlagBridge = Pick<ExtensionAPI, "registerFlag" | "getFlag">;

type ToolCatalogEntry = {
  toolId: string;
  provider: ProviderName;
  nativeToolName: string;
  name: string;
  description: string;
  discoveryDescription: string;
  available: boolean;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
};

type CachedCatalogTool = {
  name: string;
  label?: string;
  description: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
};

type CachedMuxState = {
  toolsByProvider?: Record<ProviderName, CachedCatalogTool[]>;
};

type ToolListItem = {
  tool_id: string;
  name: string;
  description: string;
  available: boolean;
};

type ResolvedProviderControlPlane = {
  controls: MuxProviderControls;
};

const findToolsParameters = Type.Object({
  query: Type.String({ minLength: 1 }),
  provider: Type.Optional(Type.String({ minLength: 1 })),
  limit: Type.Optional(Type.Integer({ minimum: 1, maximum: MAX_FIND_LIMIT })),
});

const getToolDetailsParameters = Type.Object({
  tool_id: Type.String({ minLength: 1 }),
});

const callToolParameters = Type.Object({
  tool_id: Type.String({ minLength: 1 }),
  arguments: Type.Record(Type.String(), Type.Unknown()),
});

type FindToolsParams = Static<typeof findToolsParameters>;
type GetToolDetailsParams = Static<typeof getToolDetailsParameters>;
type CallToolParams = Static<typeof callToolParameters>;

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

function getDefaultMuxStatePath(): string {
  const agentDir = resolveOptionalPath(
    process.env[PI_CODING_AGENT_DIR_ENV] || DEFAULT_PI_AGENT_DIR,
  );
  return join(agentDir, MUX_STATE_FILE_NAME);
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

function normalizeName(text: string): string {
  return compactWhitespace(text).toLowerCase();
}

function normalizeCatalogDescription(description: string): string {
  const compact = compactWhitespace(description);
  if (!compact) {
    return "";
  }

  const firstSentence = compact.split(/(?<=[.!?])\s+/u, 1)[0] ?? compact;
  return firstSentence.length > 160
    ? `${firstSentence.slice(0, 159)}…`
    : firstSentence;
}

function tokenize(value: string): string[] {
  return normalizeName(value)
    .split(/[^a-z0-9]+/u)
    .filter((token) => token.length > 0);
}

function buildToolId(provider: ProviderName, nativeToolName: string): string {
  return `${provider}/${nativeToolName}`;
}

function getDefaultProviderControls(provider: ProviderName): MuxProviderControls {
  return {
    connect: `${provider}_mcp_connect`,
    disconnect: `${provider}_mcp_disconnect`,
    status: `${provider}_mcp_status`,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getTextContent(content: Array<{ type: string; text?: string }> | undefined): string {
  return (content ?? [])
    .map((item) => (item.type === "text" ? item.text ?? "" : ""))
    .filter((item) => item.length > 0)
    .join("\n")
    .trim();
}

function buildToolErrorMessage(result: unknown): string | undefined {
  if (!isRecord(result)) return undefined;
  if (result.isError !== true) return undefined;

  const content = Array.isArray(result.content)
    ? getTextContent(result.content as Array<{ type: string; text?: string }>)
    : "";
  return content || "Tool execution failed.";
}

function requiresInteractiveSetup(result: unknown): boolean {
  return isRecord(result) && isRecord(result.details) && result.details.requiresInteractiveSetup === true;
}

function extractRawResult(result: unknown): unknown {
  if (isRecord(result) && isRecord(result.details) && "rawResult" in result.details) {
    return result.details.rawResult;
  }
  return result;
}

function getOutputValidationTarget(result: unknown): unknown {
  if (isRecord(result) && "structuredContent" in result) {
    return result.structuredContent;
  }
  return result;
}

class CatalogStorage {
  private readonly path: string;

  constructor(path = getDefaultMuxStatePath()) {
    this.path = resolveOptionalPath(path);
  }

  load(): CachedMuxState {
    if (!existsSync(this.path)) {
      return {};
    }

    try {
      return JSON.parse(readFileSync(this.path, "utf8")) as CachedMuxState;
    } catch {
      return {};
    }
  }

  save(state: CachedMuxState): void {
    mkdirSync(dirname(this.path), { recursive: true });
    writeFileSync(this.path, JSON.stringify(state, null, 2), "utf8");
  }
}

class SchemaValidator {
  private readonly ajv: Ajv;
  private readonly cache = new Map<string, ValidateFunction>();

  constructor() {
    this.ajv = new Ajv({ allErrors: true, strict: false, validateSchema: false });
  }

  validate(schema: Record<string, unknown> | undefined, data: unknown): string | null {
    if (!schema) return null;

    try {
      const key = safeJsonStringify(schema);
      let validate = this.cache.get(key);
      if (!validate) {
        validate = this.ajv.compile(schema);
        this.cache.set(key, validate);
      }

      if (validate(data)) {
        return null;
      }

      const message = (validate.errors ?? [])
        .map((error) => {
          const instancePath = error.instancePath || "/";
          return `${instancePath} ${error.message ?? "is invalid"}`.trim();
        })
        .join("; ");
      return message || "Validation failed.";
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return `Schema validation failed: ${message}`;
    }
  }
}

class EmbeddedEventBus {
  private readonly handlers = new Map<string, Array<(data: unknown) => void>>();
  private notifyBridge?: (message: string, type?: NotifyLevel) => void;

  setNotifyBridge(notifyBridge?: (message: string, type?: NotifyLevel) => void): void {
    this.notifyBridge = notifyBridge;
  }

  on(event: string, handler: (data: unknown) => void): void {
    const list = this.handlers.get(event) ?? [];
    list.push(handler);
    this.handlers.set(event, list);
  }

  emit(event: string, data: unknown): void {
    if (event === "ui:notify" && isRecord(data) && typeof data.message === "string") {
      this.notifyBridge?.(
        data.message,
        typeof data.type === "string" ? (data.type as NotifyLevel) : "info",
      );
    }

    for (const handler of this.handlers.get(event) ?? []) {
      handler(data);
    }
  }
}

function createNoopUi(realCtx?: ExtensionContext | ExtensionCommandContext) {
  return {
    notify(message: string, type: NotifyLevel = "info") {
      realCtx?.ui.notify(message, type);
    },
    setStatus(key: string, value?: string) {
      realCtx?.ui.setStatus(key, value);
    },
    setWidget(key: string, value?: unknown) {
      realCtx?.ui.setWidget(key, value as never);
    },
    async select(title: string, options: string[]) {
      return realCtx?.ui.select ? await realCtx.ui.select(title, options) : undefined;
    },
    async confirm(title: string, message: string) {
      return realCtx?.ui.confirm ? await realCtx.ui.confirm(title, message) : false;
    },
    async input(title: string, placeholder?: string) {
      return realCtx?.ui.input ? await realCtx.ui.input(title, placeholder) : undefined;
    },
    async editor(title: string, initialValue?: string) {
      return realCtx?.ui.editor ? await realCtx.ui.editor(title, initialValue) : undefined;
    },
    setTitle(title: string) {
      realCtx?.ui.setTitle(title);
    },
    setEditorText(text: string) {
      realCtx?.ui.setEditorText(text);
    },
    getEditorText() {
      return realCtx?.ui.getEditorText?.() ?? "";
    },
  };
}

class EmbeddedExtensionHost {
  private readonly tools = new Map<string, EmbeddedToolDefinition>();
  private readonly commands = new Map<string, EmbeddedCommandDefinition>();
  private readonly handlers = new Map<string, EmbeddedEventHandler[]>();
  private readonly flags = new Map<string, boolean | string | undefined>();
  private readonly events = new EmbeddedEventBus();
  private activeTools = new Set<string>();
  private initialized = false;
  private initializing?: Promise<void>;
  private sessionStarted = false;

  constructor(
    private readonly sourcePath: string,
    private readonly factory: MuxProviderFactory,
    private readonly flagBridge?: EmbeddedFlagBridge,
  ) {}

  async initialize(): Promise<void> {
    if (this.initialized) return;
    if (this.initializing) {
      await this.initializing;
      return;
    }

    this.initializing = (async () => {
      const register = typeof this.factory === "function" ? this.factory : this.factory.default;
      await register(this.createFakePi());
      this.initialized = true;
    })();

    await this.initializing;
  }

  async runSessionStart(realCtx?: ExtensionContext): Promise<void> {
    await this.initialize();
    if (this.sessionStarted) return;

    const handlers = this.handlers.get("session_start") ?? [];
    const ctx = this.createContext(realCtx);
    this.events.setNotifyBridge(realCtx?.ui.notify.bind(realCtx.ui));
    try {
      for (const handler of handlers) {
        await handler({ reason: "startup" }, ctx);
      }
      this.sessionStarted = true;
    } finally {
      this.events.setNotifyBridge(undefined);
    }
  }

  private async runToolCallHandlers(
    name: string,
    args: Record<string, unknown>,
    realCtx?: ExtensionContext,
    signal?: AbortSignal,
  ): Promise<void> {
    const handlers = this.handlers.get("tool_call") ?? [];
    if (handlers.length === 0) return;

    const ctx = this.createContext(realCtx, signal);
    const event = {
      toolName: name,
      toolCallId: `${name}-${Date.now()}`,
      input: args,
    };

    for (const handler of handlers) {
      const result = await handler(event, ctx);
      if (isRecord(result) && result.block === true) {
        const reason = typeof result.reason === "string"
          ? result.reason
          : `Tool '${name}' was blocked by an embedded extension handler.`;
        throw new Error(reason);
      }
    }
  }

  getRegisteredTools(): EmbeddedToolDefinition[] {
    return [...this.tools.values()];
  }

  getActiveToolDefinitions(): EmbeddedToolDefinition[] {
    return [...this.activeTools]
      .map((name) => this.tools.get(name))
      .filter((tool): tool is EmbeddedToolDefinition => tool !== undefined);
  }

  getTool(name: string): EmbeddedToolDefinition | undefined {
    return this.tools.get(name);
  }

  getRegisteredCommands(): Array<{ name: string; description?: string }> {
    return [...this.commands.entries()].map(([name, definition]) => ({
      name,
      description: definition.description,
    }));
  }

  async executeTool(
    name: string,
    args: Record<string, unknown>,
    signal?: AbortSignal,
    onUpdate?: ToolUpdateCallback,
    realCtx?: ExtensionContext,
  ): Promise<unknown> {
    await this.initialize();
    const tool = this.tools.get(name);
    if (!tool?.execute) {
      throw new Error(`Unknown embedded tool '${name}'.`);
    }

    await this.runToolCallHandlers(name, args, realCtx, signal);

    this.events.setNotifyBridge(realCtx?.ui.notify.bind(realCtx.ui));
    try {
      return await tool.execute(
        `${name}-${Date.now()}`,
        args,
        signal,
        onUpdate,
        this.createContext(realCtx, signal),
      );
    } finally {
      this.events.setNotifyBridge(undefined);
    }
  }

  async executeCommand(
    name: string,
    args: string,
    realCtx: ExtensionCommandContext,
  ): Promise<void> {
    await this.initialize();
    const command = this.commands.get(name);
    if (!command) {
      throw new Error(`Unknown embedded command '${name}'.`);
    }

    this.events.setNotifyBridge(realCtx.ui.notify.bind(realCtx.ui));
    try {
      await command.handler(args, this.createCommandContext(realCtx));
    } finally {
      this.events.setNotifyBridge(undefined);
    }
  }

  private createFakePi(): ExtensionAPI {
    return {
      on: (event: string, handler: EmbeddedEventHandler) => {
        const list = this.handlers.get(event) ?? [];
        list.push(handler);
        this.handlers.set(event, list);
      },
      registerTool: (tool: EmbeddedToolDefinition) => {
        this.tools.set(tool.name, tool);
        this.activeTools.add(tool.name);
      },
      registerCommand: (name: string, options: EmbeddedCommandDefinition) => {
        this.commands.set(name, options);
      },
      registerShortcut: () => undefined,
      registerFlag: (name: string, options: { default?: boolean | string }) => {
        this.flagBridge?.registerFlag(name, options as never);
        if (!this.flags.has(name)) {
          this.flags.set(name, options.default);
        }
      },
      getFlag: (name: string) => this.flagBridge?.getFlag(name) ?? this.flags.get(name),
      registerMessageRenderer: () => undefined,
      sendMessage: () => undefined,
      sendUserMessage: () => undefined,
      appendEntry: () => undefined,
      setSessionName: () => undefined,
      getSessionName: () => undefined,
      setLabel: () => undefined,
      exec: async () => ({ stdout: "", stderr: "", code: 0, killed: false }),
      getActiveTools: () => [...this.activeTools],
      getAllTools: () =>
        [...this.tools.values()].map((tool) => ({
          name: tool.name,
          description: tool.description ?? "",
          parameters: tool.parameters ?? {},
          sourceInfo: {
            path: this.sourcePath,
            source: this.sourcePath,
            scope: "temporary",
            origin: "top-level",
          },
        })),
      setActiveTools: (toolNames: string[]) => {
        this.activeTools = new Set(toolNames);
      },
      getCommands: () => [],
      setModel: async () => false,
      getThinkingLevel: () => "off",
      setThinkingLevel: () => undefined,
      registerProvider: () => undefined,
      unregisterProvider: () => undefined,
      events: this.events as never,
    } as ExtensionAPI;
  }

  private createBaseContext(
    realCtx?: ExtensionContext | ExtensionCommandContext,
    signal?: AbortSignal,
  ) {
    return {
      ui: createNoopUi(realCtx),
      hasUI: realCtx?.hasUI ?? false,
      cwd: realCtx?.cwd ?? process.cwd(),
      sessionManager: realCtx?.sessionManager,
      modelRegistry: realCtx?.modelRegistry,
      model: realCtx?.model,
      signal: signal ?? realCtx?.signal,
      isIdle: () => true,
      abort: () => undefined,
      hasPendingMessages: () => false,
      shutdown: () => undefined,
      getContextUsage: () => undefined,
      compact: () => undefined,
      getSystemPrompt: () => "",
    };
  }

  private createContext(realCtx?: ExtensionContext, signal?: AbortSignal): ExtensionContext {
    return this.createBaseContext(realCtx, signal) as ExtensionContext;
  }

  private createCommandContext(realCtx?: ExtensionCommandContext): ExtensionCommandContext {
    return {
      ...this.createBaseContext(realCtx),
      waitForIdle: async () => undefined,
      newSession: async () => ({ cancelled: true }),
      fork: async () => ({ cancelled: true }),
      navigateTree: async () => ({ cancelled: true }),
      switchSession: async () => ({ cancelled: true }),
      reload: async () => undefined,
    } as ExtensionCommandContext;
  }
}

interface MuxProviderAdapter {
  initialize(ctx?: ExtensionContext): Promise<void>;
  listTools(): Promise<CachedCatalogTool[]>;
  isAvailable(): Promise<boolean>;
  getStatusText(): Promise<string>;
  connect(ctx: ExtensionCommandContext): Promise<string>;
  disconnect(ctx: ExtensionCommandContext): Promise<string>;
  callTool(
    nativeToolName: string,
    args: Record<string, unknown>,
    signal?: AbortSignal,
    onUpdate?: ToolUpdateCallback,
    ctx?: ExtensionContext,
  ): Promise<unknown>;
}

class EmbeddedProviderAdapter implements MuxProviderAdapter {
  private controlPlane?: ResolvedProviderControlPlane;

  constructor(
    private readonly provider: ProviderName,
    private readonly host: EmbeddedExtensionHost,
    private readonly muxProvider: MuxProviderConfig = {},
  ) {}

  async initialize(ctx?: ExtensionContext): Promise<void> {
    await this.host.runSessionStart(ctx);
  }

  async listTools(): Promise<CachedCatalogTool[]> {
    const controlToolNames = new Set(Object.values((await this.getControlPlane()).controls));
    return this.host
      .getActiveToolDefinitions()
      .filter((tool) => !controlToolNames.has(tool.name))
      .filter((tool) => isRecord(tool.parameters))
      .map((tool) => ({
        name: tool.name,
        label: tool.label,
        description: tool.description ?? "",
        inputSchema: (tool.parameters as Record<string, unknown>) ?? {},
        outputSchema: isRecord(tool.outputSchema) ? tool.outputSchema : undefined,
      }));
  }

  async isAvailable(): Promise<boolean> {
    const { controls } = await this.getControlPlane();
    const result = await this.host.executeTool(controls.status, {});
    return isRecord(result) && isRecord(result.details) && result.details.connected === true;
  }

  async getStatusText(): Promise<string> {
    const { controls } = await this.getControlPlane();
    const result = await this.host.executeTool(controls.status, {});
    return getTextContent(isRecord(result) ? (result.content as TextContentBlock[]) : []);
  }

  async connect(ctx: ExtensionCommandContext): Promise<string> {
    const { controls } = await this.getControlPlane(ctx);
    const result = await this.host.executeTool(controls.connect, {}, undefined, undefined, ctx);
    const errorMessage = buildToolErrorMessage(result);
    if (!errorMessage) {
      return getTextContent(isRecord(result) ? (result.content as TextContentBlock[]) : []);
    }

    if (requiresInteractiveSetup(result)) {
      await this.host.executeCommand(this.getRequiredCommandName(), "", ctx);
      const refreshed = await this.host.executeTool(
        controls.connect,
        {},
        undefined,
        undefined,
        ctx,
      );
      const refreshedError = buildToolErrorMessage(refreshed);
      if (refreshedError) {
        throw new Error(
          `Provider bootstrap completed, but '${controls.connect}' still failed: ${refreshedError}`,
        );
      }
      return getTextContent(isRecord(refreshed) ? (refreshed.content as TextContentBlock[]) : []);
    }

    throw new Error(errorMessage);
  }

  async disconnect(ctx: ExtensionCommandContext): Promise<string> {
    const { controls } = await this.getControlPlane(ctx);
    const result = await this.host.executeTool(controls.disconnect, {}, undefined, undefined, ctx);
    const errorMessage = buildToolErrorMessage(result);
    if (errorMessage) {
      throw new Error(errorMessage);
    }
    return getTextContent(isRecord(result) ? (result.content as TextContentBlock[]) : []);
  }

  async callTool(
    nativeToolName: string,
    args: Record<string, unknown>,
    signal?: AbortSignal,
    onUpdate?: ToolUpdateCallback,
    ctx?: ExtensionContext,
  ): Promise<unknown> {
    await this.initialize(ctx);
    const result = await this.host.executeTool(
      nativeToolName,
      args,
      signal,
      onUpdate,
      ctx,
    );
    return extractRawResult(result);
  }

  private async getControlPlane(
    ctx?: ExtensionContext,
  ): Promise<ResolvedProviderControlPlane> {
    await this.initialize(ctx);
    if (this.controlPlane) {
      return this.controlPlane;
    }

    const defaultControls = getDefaultProviderControls(this.provider);
    const controls: MuxProviderControls = {
      connect: this.resolveControlToolName(
        this.muxProvider.controls?.connect ?? defaultControls.connect,
        "connect",
      ),
      disconnect: this.resolveControlToolName(
        this.muxProvider.controls?.disconnect ?? defaultControls.disconnect,
        "disconnect",
      ),
      status: this.resolveControlToolName(
        this.muxProvider.controls?.status ?? defaultControls.status,
        "status",
      ),
    };

    this.controlPlane = {
      controls,
    };
    return this.controlPlane;
  }

  private resolveControlToolName(name: string, role: keyof MuxProviderControls): string {
    if (this.host.getTool(name)) {
      return name;
    }

    throw new Error(
      `pi-mux could not find the ${role} control tool '${name}' for provider '${this.provider}'.`,
    );
  }

  private getRequiredCommandName(): string {
    if (this.muxProvider.commandName) {
      return this.muxProvider.commandName;
    }

    const registeredCommands = this.host.getRegisteredCommands();
    if (registeredCommands.length === 1) {
      const commandName = registeredCommands[0]?.name;
      if (commandName) {
        return commandName;
      }

      throw new Error(
        `pi-mux provider '${this.provider}' registered a bootstrap command without a name. Set muxProvider.commandName to fix this.`,
      );
    }
    if (registeredCommands.length === 0) {
      throw new Error(
        `pi-mux provider '${this.provider}' requested command bootstrap but did not register a command. Set muxProvider.commandName to fix this.`,
      );
    }

    throw new Error(
      `pi-mux provider '${this.provider}' requested command bootstrap but registered ${registeredCommands.length} commands. Set muxProvider.commandName to fix this.`,
    );
  }
}

function buildCatalogEntry(
  provider: ProviderName,
  tool: CachedCatalogTool,
  available: boolean,
): ToolCatalogEntry {
  const name = tool.label?.trim() || tool.name;
  const description = compactWhitespace(tool.description || "");
  return {
    toolId: buildToolId(provider, tool.name),
    provider,
    nativeToolName: tool.name,
    name,
    description,
    discoveryDescription: normalizeCatalogDescription(description),
    available,
    inputSchema: tool.inputSchema,
    outputSchema: tool.outputSchema,
  };
}

function scoreCatalogEntry(entry: ToolCatalogEntry, query: string): number {
  const normalizedQuery = normalizeName(query);
  if (!normalizedQuery) return 0;

  const queryTokens = tokenize(query);
  const toolId = normalizeName(entry.toolId);
  const provider = normalizeName(entry.provider);
  const nativeName = normalizeName(entry.nativeToolName);
  const displayName = normalizeName(entry.name);
  const description = normalizeName(entry.discoveryDescription || entry.description);

  let score = 0;

  if (toolId === normalizedQuery) score += 100;
  if (nativeName === normalizedQuery) score += 95;
  if (displayName === normalizedQuery) score += 90;
  if (provider === normalizedQuery) score += 30;

  if (toolId.includes(normalizedQuery)) score += 40;
  if (nativeName.includes(normalizedQuery)) score += 36;
  if (displayName.includes(normalizedQuery)) score += 32;
  if (description.includes(normalizedQuery)) score += 16;
  if (provider.includes(normalizedQuery)) score += 8;

  const fieldTokens = {
    toolId: new Set(tokenize(entry.toolId)),
    provider: new Set(tokenize(entry.provider)),
    nativeName: new Set(tokenize(entry.nativeToolName)),
    displayName: new Set(tokenize(entry.name)),
    description: new Set(tokenize(entry.discoveryDescription || entry.description)),
  };

  for (const token of queryTokens) {
    if (fieldTokens.toolId.has(token)) score += 14;
    if (fieldTokens.nativeName.has(token)) score += 16;
    if (fieldTokens.displayName.has(token)) score += 12;
    if (fieldTokens.description.has(token)) score += 5;
    if (fieldTokens.provider.has(token)) score += 3;
  }

  return score;
}

function findCatalogTools(
  entries: ToolCatalogEntry[],
  query: string,
  limit = DEFAULT_FIND_LIMIT,
): ToolCatalogEntry[] {
  const normalizedLimit = Math.min(Math.max(limit, 1), MAX_FIND_LIMIT);

  return entries
    .map((entry) => ({ entry, score: scoreCatalogEntry(entry, query) }))
    .filter((item) => item.score > 0)
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score;
      if (left.entry.available !== right.entry.available) {
        return left.entry.available ? -1 : 1;
      }
      return left.entry.toolId.localeCompare(right.entry.toolId);
    })
    .slice(0, normalizedLimit)
    .map((item) => item.entry);
}

class MuxService {
  private readonly validator = new SchemaValidator();
  private cachedState: CachedMuxState;
  private readonly catalogEntriesByToolId = new Map<string, ToolCatalogEntry>();
  private readonly catalogEntriesByProvider = new Map<ProviderName, ToolCatalogEntry[]>();
  private readonly providerAvailability = new Map<ProviderName, boolean>();
  private initialized = false;
  private initializing?: Promise<void>;

  constructor(
    private readonly adapters: Record<ProviderName, MuxProviderAdapter>,
    private readonly storage: CatalogStorage,
  ) {
    this.cachedState = storage.load();
    this.rebuildRuntimeCatalogIndex();
  }

  getProviderNames(): ProviderName[] {
    return Object.keys(this.adapters);
  }

  async initialize(ctx?: ExtensionContext): Promise<void> {
    if (this.initialized) return;
    if (this.initializing) {
      await this.initializing;
      return;
    }

    this.initializing = (async () => {
      const providerNames = this.getProviderNames();
      const results = await Promise.allSettled(
        providerNames.map(async (provider) => {
          await this.adapters[provider].initialize(ctx);
          return provider;
        }),
      );

      for (const [index, result] of results.entries()) {
        if (result.status === "rejected") {
          reportInitializationFailure(providerNames[index] ?? "unknown", result.reason, ctx);
        }
      }

      await this.refreshCaches();
      this.initialized = true;
    })();

    try {
      await this.initializing;
    } finally {
      this.initializing = undefined;
    }
  }

  async refreshCaches(providers: readonly ProviderName[] = this.getProviderNames()): Promise<void> {
    const next: CachedMuxState = {
      toolsByProvider: { ...this.cachedState.toolsByProvider },
    };

    for (const provider of providers) {
      const cachedTools = next.toolsByProvider?.[provider] ?? [];

      try {
        const adapter = this.adapters[provider];
        const available = await adapter.isAvailable();
        const liveTools = await adapter.listTools();
        const sourceTools = available || liveTools.length > 0 ? liveTools : cachedTools;

        this.providerAvailability.set(provider, available);
        next.toolsByProvider ??= {};
        if (available || sourceTools.length > 0) {
          next.toolsByProvider[provider] = sourceTools;
        } else {
          delete next.toolsByProvider[provider];
        }
      } catch {
        this.providerAvailability.set(provider, false);
        // Keep cached entries for providers that cannot currently refresh.
      }
    }

    this.cachedState = next;
    this.storage.save(this.cachedState);
    this.rebuildRuntimeCatalogIndex();
  }

  async getCatalogEntries(ctx?: ExtensionContext): Promise<ToolCatalogEntry[]> {
    await this.initialize(ctx);
    return this.getIndexedCatalogEntries();
  }

  async getToolDetails(toolId: string, ctx?: ExtensionContext): Promise<ToolCatalogEntry> {
    const entry = await this.findExactTool(toolId, ctx);
    if (!entry) {
      throw new Error(`Unknown tool_id '${toolId}'.`);
    }
    return entry;
  }

  async findTools(
    query: string,
    limit = DEFAULT_FIND_LIMIT,
    provider?: string,
    ctx?: ExtensionContext,
  ): Promise<ToolListItem[]> {
    await this.initialize(ctx);
    const providerScope = provider ? this.validateProviderName(provider) : undefined;
    const entries = this.getIndexedCatalogEntries(providerScope);
    return findCatalogTools(entries, query, limit).map((entry) => ({
      tool_id: entry.toolId,
      name: entry.nativeToolName,
      description: entry.discoveryDescription || entry.description,
      available: entry.available,
    }));
  }

  async listProviderTools(provider: string, ctx?: ExtensionContext): Promise<ToolListItem[]> {
    await this.initialize(ctx);
    const providerScope = this.validateProviderName(provider);
    return this.getIndexedCatalogEntries(providerScope)
      .slice()
      .sort((left, right) => left.toolId.localeCompare(right.toolId))
      .map((entry) => ({
        tool_id: entry.toolId,
        name: entry.nativeToolName,
        description: entry.discoveryDescription || entry.description,
        available: entry.available,
      }));
  }

  async getStatusOverview(ctx?: ExtensionContext): Promise<string> {
    await this.initialize(ctx);
    const lines = ["pi-mux provider status:"];

    for (const provider of this.getProviderNames()) {
      const toolCount = this.cachedState.toolsByProvider?.[provider]?.length ?? 0;
      const available = this.providerAvailability.get(provider) ?? false;
      let suffix = `${toolCount} tool${toolCount === 1 ? "" : "s"}`;

      try {
        const statusText = await this.adapters[provider].getStatusText();
        const toolsets = extractStatusField(statusText, "Toolsets");
        if (toolsets) {
          suffix += `, toolsets: ${toolsets}`;
        }
      } catch {
        // Ignore provider-specific status parsing failures and keep the base summary.
      }

      lines.push(`- ${provider}: ${available ? "available" : "unavailable"} (${suffix})`);
    }

    return lines.join("\n");
  }

  async connectProvider(provider: ProviderName, ctx: ExtensionCommandContext): Promise<string> {
    await this.initialize(ctx);
    const message = await this.adapters[provider].connect(ctx);
    await this.refreshCaches([provider]);
    return message;
  }

  async disconnectProvider(provider: ProviderName, ctx: ExtensionCommandContext): Promise<string> {
    await this.initialize(ctx);
    const message = await this.adapters[provider].disconnect(ctx);
    await this.refreshCaches([provider]);
    return message;
  }

  async callTool(
    toolId: string,
    args: Record<string, unknown>,
    ctx?: ExtensionContext,
    signal?: AbortSignal,
    onUpdate?: ToolUpdateCallback,
  ): Promise<MuxToolCallResponse> {
    const entry = await this.findExactTool(toolId, ctx);
    if (!entry) {
      return {
        ok: false,
        error: `Unknown tool_id '${toolId}'.`,
      };
    }

    const available = await this.isProviderCurrentlyAvailable(entry.provider);
    if (!available) {
      return {
        ok: false,
        error: `Tool '${toolId}' is unavailable. Connect the provider with /mux connect ${entry.provider}.`,
      };
    }

    const inputValidationError = this.validator.validate(entry.inputSchema, args);
    if (inputValidationError) {
      return {
        ok: false,
        error: `Invalid arguments for '${toolId}': ${inputValidationError}`,
      };
    }

    try {
      const result = await this.adapters[entry.provider].callTool(
        entry.nativeToolName,
        args,
        signal,
        onUpdate,
        ctx,
      );
      const toolError = buildToolErrorMessage(result);
      if (toolError) {
        return { ok: false, error: toolError };
      }

      if (entry.outputSchema) {
        const outputValidationError = this.validator.validate(
          entry.outputSchema,
          getOutputValidationTarget(result),
        );
        if (outputValidationError) {
          return {
            ok: false,
            error: `Tool '${toolId}' returned data that did not match its output schema: ${outputValidationError}`,
          };
        }
      }

      return { ok: true, result };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return { ok: false, error: message };
    }
  }

  private getIndexedCatalogEntries(provider?: ProviderName): ToolCatalogEntry[] {
    if (provider) {
      return [...(this.catalogEntriesByProvider.get(provider) ?? [])];
    }

    return this.getProviderNames().flatMap((name) => this.catalogEntriesByProvider.get(name) ?? []);
  }

  private rebuildRuntimeCatalogIndex(): void {
    this.catalogEntriesByToolId.clear();
    this.catalogEntriesByProvider.clear();

    for (const provider of this.getProviderNames()) {
      const available = this.providerAvailability.get(provider) ?? false;
      const tools = this.cachedState.toolsByProvider?.[provider] ?? [];
      const entries = tools.map((tool) => buildCatalogEntry(provider, tool, available));

      if (entries.length === 0) {
        continue;
      }

      this.catalogEntriesByProvider.set(provider, entries);
      for (const entry of entries) {
        this.catalogEntriesByToolId.set(entry.toolId, entry);
      }
    }
  }

  private async isProviderCurrentlyAvailable(provider: ProviderName): Promise<boolean> {
    try {
      const available = await this.adapters[provider].isAvailable();
      this.providerAvailability.set(provider, available);
      this.rebuildRuntimeCatalogIndex();
      return available;
    } catch {
      this.providerAvailability.set(provider, false);
      this.rebuildRuntimeCatalogIndex();
      return false;
    }
  }

  private validateProviderName(provider: string): ProviderName {
    const allowedProviders = this.getProviderNames();
    if (allowedProviders.includes(provider)) {
      return provider;
    }

    throw new Error(
      `Invalid provider '${provider}'. Allowed providers: ${allowedProviders.join(", ")}.`,
    );
  }

  private async findExactTool(
    toolId: string,
    ctx?: ExtensionContext,
  ): Promise<ToolCatalogEntry | undefined> {
    await this.initialize(ctx);
    return this.catalogEntriesByToolId.get(toolId);
  }
}

function getEmbeddedProviderDirectoryNames(): ProviderName[] {
  const extensionDir = dirname(fileURLToPath(import.meta.url));
  const providersDir = resolve(extensionDir, "../providers");
  return readdirSync(providersDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function formatInstalledProvidersSnippet(): string {
  const providers = getEmbeddedProviderDirectoryNames();
  if (providers.length === 0) {
    return "";
  }

  return ` Installed providers: ${providers.join(", ")}.`;
}

async function loadEmbeddedProviderDefinitions(): Promise<
  EmbeddedProviderModuleDefinition[]
> {
  const extensionDir = dirname(fileURLToPath(import.meta.url));
  const providersDir = resolve(extensionDir, "../providers");
  const providerDirs = getEmbeddedProviderDirectoryNames();

  const definitions: EmbeddedProviderModuleDefinition[] = [];
  for (const providerDir of providerDirs) {
    const modulePath = join(providersDir, providerDir, "index.ts");
    if (!existsSync(modulePath)) {
      throw new Error(`Provider directory '${providerDir}' is missing index.ts.`);
    }

    const imported = (await import(pathToFileURL(modulePath).href)) as {
      default?: MuxProviderFactory;
      muxProvider?: MuxProviderConfig;
    };
    const extensionFactory = imported.default;
    if (!extensionFactory) {
      throw new Error(`Provider module '${modulePath}' did not export a default extension.`);
    }

    const provider = imported.muxProvider?.provider ?? providerDir;
    if (definitions.some((definition) => definition.provider === provider)) {
      throw new Error(`Duplicate pi-mux provider name '${provider}' found while loading '${modulePath}'.`);
    }

    definitions.push({
      provider,
      modulePath,
      extensionFactory,
      muxProvider: imported.muxProvider ?? {},
    });
  }

  return definitions;
}

async function loadMuxService(flagBridge?: EmbeddedFlagBridge): Promise<MuxService> {
  const definitions = await loadEmbeddedProviderDefinitions();
  const adapters = Object.fromEntries(
    definitions.map((definition) => {
      const host = new EmbeddedExtensionHost(
        definition.modulePath,
        definition.extensionFactory,
        flagBridge,
      );

      return [
        definition.provider,
        new EmbeddedProviderAdapter(
          definition.provider,
          host,
          definition.muxProvider,
        ),
      ];
    }),
  ) as Record<ProviderName, MuxProviderAdapter>;

  return new MuxService(adapters, new CatalogStorage());
}

function createToolTextResult(payload: unknown): UpstreamToolResult {
  return {
    content: [{ type: "text", text: safeJsonStringify(payload) }],
    details: { payload },
  };
}

function renderMuxToolCall(name: string, detail: string, theme: { fg(token: string, text: string): string; bold(text: string): string }) {
  let text = theme.fg("toolTitle", theme.bold(name));
  if (detail.trim().length > 0) {
    text += ` ${theme.fg("accent", detail)}`;
  }
  return new Text(text, 0, 0);
}

function renderCallToolCall(
  args: { tool_id: string; arguments: Record<string, unknown> },
  theme: { fg(token: string, text: string): string; bold(text: string): string },
) {
  let text = theme.fg("toolTitle", theme.bold(CALL_TOOL_TOOL_NAME));
  text += ` ${theme.fg("accent", args.tool_id)}`;

  const serializedArgs = compactWhitespace(safeJsonStringify(args.arguments));
  if (serializedArgs.length > 0) {
    text += ` ${theme.fg("muted", serializedArgs)}`;
  }

  return new Text(text, 0, 0);
}

function truncateDisplayText(text: string, maxLength = 120): string {
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function countOutputLines(text: string): number {
  return text.split("\n").filter((line) => line.trim().length > 0).length;
}

function formatCount(value: number, singular: string, plural = `${singular}s`): string {
  return `${value} ${value === 1 ? singular : plural}`;
}

function getSchemaPropertyCount(schema: unknown): number | undefined {
  if (!isRecord(schema) || !isRecord(schema.properties)) {
    return undefined;
  }
  return Object.keys(schema.properties).length;
}

function summarizeToolDetails(payload: Record<string, unknown>): string {
  const toolId = typeof payload.tool_id === "string" ? payload.tool_id : "tool";
  const availability = payload.available === true ? "available" : "unavailable";
  const inputCount = getSchemaPropertyCount(payload.input_schema);
  const outputCount = getSchemaPropertyCount(payload.output_schema);

  const parts = [toolId, availability];
  parts.push(
    inputCount === undefined ? "input schema" : formatCount(inputCount, "input field"),
  );

  if ("output_schema" in payload) {
    parts.push(
      outputCount === undefined ? "output schema" : formatCount(outputCount, "output field"),
    );
  } else {
    parts.push("no output schema");
  }

  return parts.join(" · ");
}

function getResultSizeSummary(result: unknown): string | null {
  let text: string | null = null;

  if (isRecord(result) && Array.isArray(result.content)) {
    const contentText = getTextContent(result.content as Array<{ type: string; text?: string }>);
    if (contentText.length > 0) {
      text = contentText;
    }
  }

  if (text === null && isRecord(result) && "structuredContent" in result) {
    text = safeJsonStringify(result.structuredContent);
  }

  if (text === null && typeof result === "string") {
    text = result;
  }

  if (text === null && result !== undefined) {
    text = safeJsonStringify(result);
  }

  if (!text || text.trim().length === 0) {
    return null;
  }

  return `${countOutputLines(text)} lines, ${text.length} chars`;
}

function withExpandHint(summary: string): string {
  try {
    return `${summary} ${keyHint("app.tools.expand", "for details")}`;
  } catch {
    return `${summary} (ctrl+o for details)`;
  }
}

function renderMuxFindToolsResult(
  result: UpstreamToolResult,
  options: { expanded: boolean; isPartial: boolean },
  theme: { fg(token: string, text: string): string },
  context: { isError?: boolean },
) {
  if (options.isPartial) {
    return new Text(theme.fg("warning", "Searching tools..."), 0, 0);
  }

  const text = getTextContent(result.content);
  const payload = isRecord(result.details) ? result.details.payload : undefined;
  const isError = context.isError;

  if (options.expanded) {
    return new Text(isError ? theme.fg("error", text) : theme.fg("success", text), 0, 0);
  }

  if (isRecord(payload) && Array.isArray(payload.results)) {
    const count = payload.results.length;
    return new Text(
      count > 0
        ? theme.fg("success", withExpandHint(`${count} tool${count === 1 ? "" : "s"} found`))
        : theme.fg("dim", withExpandHint("No matching tools")),
      0,
      0,
    );
  }

  return new Text(isError ? theme.fg("error", truncateDisplayText(text)) : theme.fg("success", "Tool search completed"), 0, 0);
}

function renderMuxSummaryToolResult(
  toolName: typeof GET_TOOL_DETAILS_TOOL_NAME | typeof CALL_TOOL_TOOL_NAME,
  result: UpstreamToolResult,
  options: { expanded: boolean; isPartial: boolean },
  theme: { fg(token: string, text: string): string },
  context: { isError?: boolean },
) {
  if (options.isPartial) {
    return new Text(
      theme.fg("warning", toolName === GET_TOOL_DETAILS_TOOL_NAME ? "Loading details..." : "Calling tool..."),
      0,
      0,
    );
  }

  const text = getTextContent(result.content);
  const payload = isRecord(result.details) ? result.details.payload : undefined;
  const isMuxError = isRecord(payload) && payload.ok === false;
  const isError = context.isError || isMuxError;

  if (options.expanded) {
    return new Text(isError ? theme.fg("error", text) : theme.fg("success", text), 0, 0);
  }

  if (toolName === GET_TOOL_DETAILS_TOOL_NAME && isRecord(payload)) {
    return new Text(
      theme.fg("success", withExpandHint(summarizeToolDetails(payload))),
      0,
      0,
    );
  }

  if (toolName === CALL_TOOL_TOOL_NAME && isRecord(payload)) {
    if (payload.ok === true) {
      const sizeSummary = getResultSizeSummary(payload.result);
      const summary = sizeSummary ? `Tool call succeeded (${sizeSummary})` : "Tool call succeeded";
      return new Text(theme.fg("success", withExpandHint(summary)), 0, 0);
    }
    if (payload.ok === false && typeof payload.error === "string") {
      return new Text(theme.fg("error", withExpandHint(truncateDisplayText(payload.error))), 0, 0);
    }
  }

  if (isError) {
    return new Text(theme.fg("error", truncateDisplayText(text)), 0, 0);
  }

  return new Text(
    theme.fg(
      "success",
      withExpandHint(
        toolName === GET_TOOL_DETAILS_TOOL_NAME ? "Tool details loaded" : "Tool call completed",
      ),
    ),
    0,
    0,
  );
}

function parseProviderName(
  value: string,
  providerNames: readonly ProviderName[],
): ProviderName | null {
  return providerNames.includes(value) ? value : null;
}

function extractStatusField(statusText: string, label: string): string | undefined {
  const prefix = `- ${label}:`;
  for (const line of statusText.split(/\r?\n/u)) {
    if (!line.startsWith(prefix)) continue;

    const value = line.slice(prefix.length).trim();
    return value.length > 0 ? value : undefined;
  }

  return undefined;
}

function buildMuxStatusCommandMessage(statusOverview: string, usageText?: string): string {
  if (!usageText) {
    return statusOverview;
  }

  return `${statusOverview}\n\n${usageText}`;
}

function buildMuxToolsCommandMessage(provider: string, tools: readonly ToolListItem[]): string {
  const lines = [`pi-mux tools for ${provider}:`];

  if (tools.length === 0) {
    lines.push("- No tools found.");
    return lines.join("\n");
  }

  for (const tool of tools) {
    lines.push(`- ${tool.tool_id}`);
    lines.push(`  name: ${tool.name}`);
    lines.push(`  available: ${tool.available ? "yes" : "no"}`);
    lines.push(`  description: ${tool.description}`);
  }

  return lines.join("\n");
}

function reportInitializationFailure(provider: ProviderName, error: unknown, ctx?: ExtensionContext): void {
  const message = error instanceof Error ? error.message : String(error);
  const text = `pi-mux could not initialize ${provider}: ${message}`;
  if (ctx?.hasUI) {
    ctx.ui.notify(text, "warning");
    return;
  }
  console.warn(text);
}

export {
  buildCatalogEntry,
  buildMuxStatusCommandMessage,
  buildMuxToolsCommandMessage,
  buildToolId,
  CALL_TOOL_TOOL_NAME,
  CatalogStorage,
  loadMuxService,
  createToolTextResult,
  EmbeddedExtensionHost,
  EmbeddedProviderAdapter,
  FIND_TOOLS_TOOL_NAME,
  findCatalogTools,
  GET_TOOL_DETAILS_TOOL_NAME,
  loadEmbeddedProviderDefinitions,
  MuxService,
  normalizeCatalogDescription,
  parseProviderName,
  scoreCatalogEntry,
  SchemaValidator,
};

export default function piMuxExtension(pi: ExtensionAPI) {
  const servicePromise = loadMuxService(pi);
  const installedProvidersSnippet = formatInstalledProvidersSnippet();
  const usageText = "Usage: /mux | /mux status | /mux help | /mux tools <provider> | /mux connect <provider> | /mux disconnect <provider>";

  const showCommandMessage = (
    ctx: ExtensionCommandContext,
    message: string,
    type: NotifyLevel = "info",
  ) => {
    if (ctx.hasUI) {
      ctx.ui.notify(message, type);
      return;
    }

    console.log(message);
  };

  pi.on("session_start", async (_event, ctx) => {
    const service = await servicePromise;
    await service.initialize(ctx);
  });

  pi.registerCommand("mux", {
    description: "Show pi-mux provider status and manage provider connections",
    async handler(args, ctx) {
      const trimmed = args.trim();
      if (trimmed === "help") {
        showCommandMessage(ctx, usageText, "info");
        return;
      }

      const service = await servicePromise;
      await service.initialize();
      if (!trimmed) {
        showCommandMessage(
          ctx,
          buildMuxStatusCommandMessage(await service.getStatusOverview(), usageText),
          "info",
        );
        return;
      }

      if (trimmed === "status") {
        showCommandMessage(ctx, await service.getStatusOverview(), "info");
        return;
      }

      const [command, providerValue] = trimmed.split(/\s+/, 2);
      const providerNames = service.getProviderNames();
      const provider = parseProviderName(providerValue ?? "", providerNames);
      if (command === "tools" && !providerValue) {
        showCommandMessage(
          ctx,
          `Usage: /mux tools <provider>. Available providers: ${providerNames.join(", ")}.`,
          "error",
        );
        return;
      }

      if ((command === "tools" || command === "connect" || command === "disconnect") && !provider) {
        showCommandMessage(
          ctx,
          `Unknown provider '${providerValue ?? ""}'. Use one of: ${providerNames.join(", ")}.`,
          "error",
        );
        return;
      }

      if (command === "tools" && provider) {
        showCommandMessage(
          ctx,
          buildMuxToolsCommandMessage(provider, await service.listProviderTools(provider, ctx)),
          "info",
        );
        return;
      }

      if (command === "connect" && provider) {
        try {
          showCommandMessage(ctx, await service.connectProvider(provider, ctx), "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          showCommandMessage(ctx, message, "error");
        }
        return;
      }

      if (command === "disconnect" && provider) {
        try {
          showCommandMessage(ctx, await service.disconnectProvider(provider, ctx), "info");
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          showCommandMessage(ctx, message, "error");
        }
        return;
      }

      showCommandMessage(ctx, usageText, "warning");
    },
  });

  pi.registerTool({
    name: FIND_TOOLS_TOOL_NAME,
    label: "Find Tools",
    description:
      "Search the mux catalog for tools relevant to a task. Use this first when you need a capability and do not yet know which tool to call. Results include whether each tool is currently available. When you already know which provider domain you want, pass provider to limit discovery to that exact provider. After choosing a tool, call get_tool_details to inspect its input schema and, when available, its output schema. If a tool you want to use is unavailable, ask the user to connect the provider with /mux connect <provider>.",
    promptSnippet:
      `Search installed provider tools for a task.${installedProvidersSnippet} If you already know the provider, pass provider to search only that provider.`,
    promptGuidelines: [
      "Use find_tools first when you need a capability and do not yet know which provider tool to call.",
      "If you already know the provider you want, pass the provider parameter to find_tools to search only that provider.",
    ],
    parameters: findToolsParameters,
    renderCall(args, theme) {
      const detail = args.provider
        ? `${args.provider} ${compactWhitespace(args.query)}`
        : compactWhitespace(args.query);
      return renderMuxToolCall(FIND_TOOLS_TOOL_NAME, detail, theme);
    },
    renderResult(result, options, theme, context) {
      return renderMuxFindToolsResult(
        result as UpstreamToolResult,
        options,
        theme,
        context,
      );
    },
    async execute(_toolCallId, params: FindToolsParams, _signal, _onUpdate, ctx) {
      try {
        const service = await servicePromise;
        const results = await service.findTools(
          params.query,
          params.limit ?? DEFAULT_FIND_LIMIT,
          params.provider,
          ctx,
        );
        return createToolTextResult({ results });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return {
          content: [{ type: "text", text: message }],
          isError: true,
          details: { error: message },
        };
      }
    },
  });

  pi.registerTool({
    name: GET_TOOL_DETAILS_TOOL_NAME,
    label: "Get Tool Details",
    description:
      "Returns the full details for a tool, including its provider, input schema, and, when available from the upstream provider, its output schema. Use this after find_tools and before call_tool so you know the exact arguments and expected result shape. This tool can still be used when a tool is unavailable. If the tool is unavailable, do not call it. Ask the user to connect the provider with /mux connect <provider> instead.",
    promptSnippet:
      "Inspect a discovered provider tool's description, availability, and input/output schemas after you pick a tool_id.",
    promptGuidelines: [
      "After find_tools returns a candidate tool_id, use get_tool_details before call_tool so you know the exact input schema and expected result shape.",
    ],
    parameters: getToolDetailsParameters,
    renderCall(args, theme) {
      return renderMuxToolCall(GET_TOOL_DETAILS_TOOL_NAME, args.tool_id, theme);
    },
    renderResult(result, options, theme, context) {
      return renderMuxSummaryToolResult(
        GET_TOOL_DETAILS_TOOL_NAME,
        result as UpstreamToolResult,
        options,
        theme,
        context,
      );
    },
    async execute(_toolCallId, params: GetToolDetailsParams, _signal, _onUpdate, ctx) {
      try {
        const service = await servicePromise;
        const details = await service.getToolDetails(params.tool_id, ctx);
        return createToolTextResult({
          tool_id: details.toolId,
          provider: details.provider,
          name: details.nativeToolName,
          description: details.description,
          available: details.available,
          input_schema: details.inputSchema,
          ...(details.outputSchema ? { output_schema: details.outputSchema } : {}),
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return {
          content: [{ type: "text", text: message }],
          isError: true,
          details: { error: message },
        };
      }
    },
  });

  pi.registerTool({
    name: CALL_TOOL_TOOL_NAME,
    label: "Call Tool",
    description:
      "Calls a tool through the mux using the provided arguments. Use this only after you have identified the correct tool with find_tools and inspected it with get_tool_details. If the tool has an output schema, the returned result will conform to that schema. If you do not yet know which tool to use, call find_tools first. If you do not yet know the exact arguments or expected result shape, call get_tool_details first. If the tool is unavailable, this call will fail. Ask the user to connect the provider with /mux connect <provider> instead.",
    promptSnippet:
      "Call a discovered provider tool by tool_id using arguments that match its input schema.",
    promptGuidelines: [
      "Only use call_tool after you have identified the tool_id with find_tools and inspected its schema with get_tool_details.",
      "If get_tool_details shows the tool is unavailable, do not call it. Ask the user to run /mux connect <provider> instead.",
    ],
    parameters: callToolParameters,
    renderCall(args, theme) {
      return renderCallToolCall(args, theme);
    },
    renderResult(result, options, theme, context) {
      return renderMuxSummaryToolResult(
        CALL_TOOL_TOOL_NAME,
        result as UpstreamToolResult,
        options,
        theme,
        context,
      );
    },
    async execute(_toolCallId, params: CallToolParams, signal, onUpdate, ctx) {
      const service = await servicePromise;
      const result = await service.callTool(
        params.tool_id,
        params.arguments,
        ctx,
        signal,
        onUpdate,
      );
      return createToolTextResult(result);
    },
  });
}
