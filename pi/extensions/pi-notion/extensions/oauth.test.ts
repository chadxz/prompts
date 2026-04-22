import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildAuthorizationUrl,
  exchangeCodeForTokens,
  executeOAuthFlow,
  extractCallbackParams,
  FileTokenStorage,
  generateCodeChallenge,
  generateCodeVerifier,
  generateState,
  getAuthorizationErrorHtml,
  getAuthorizationSuccessHtml,
  getStateMismatchHtml,
  getValidAccessToken,
  handleCallbackParams,
  parseQueryParams,
  processCallbackChunk,
  refreshTokens,
  writeHtmlResponse,
  writeOutcomeResponse,
  type OAuthConfig,
  type OAuthTokens,
  type TokenStorage,
} from "./oauth.js";

const config: OAuthConfig = {
  clientId: "client-id",
  clientSecret: "client-secret",
  redirectUri: "http://localhost:3000/callback",
};

describe("oauth.ts", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("generates PKCE values and builds authorization URLs", () => {
    const verifier = generateCodeVerifier();
    expect(verifier).toBeTruthy();
    expect(verifier).not.toMatch(/[+/=]/);
    expect(verifier.length).toBeGreaterThanOrEqual(32);

    const challenge = generateCodeChallenge(verifier);
    expect(challenge).toBeTruthy();
    expect(challenge).not.toMatch(/[+/=]/);
    expect(generateCodeChallenge("test-verifier-string")).toBe(generateCodeChallenge("test-verifier-string"));

    const state = generateState();
    expect(state).toMatch(/^[0-9a-f]{32}$/);

    const url = buildAuthorizationUrl(config, "challenge", "state");
    expect(url).toContain("https://api.notion.com/v1/oauth/authorize");
    expect(url).toContain("response_type=code");
    expect(url).toContain("owner=user");
    expect(url).toContain(`client_id=${config.clientId}`);
    expect(url).toContain(`redirect_uri=${encodeURIComponent(config.redirectUri)}`);
  });

  it("parses callback requests and renders callback HTML responses", () => {
    expect(parseQueryParams("http://localhost/callback?code=abc&state=xyz")).toEqual({ code: "abc", state: "xyz" });
    expect(extractCallbackParams("GET /callback?code=abc&state=xyz HTTP/1.1\r\nHost: localhost\r\n\r\n")).toEqual({
      code: "abc",
      state: "xyz",
    });
    expect(extractCallbackParams("GET /other HTTP/1.1\r\n\r\n")).toBeNull();

    expect(getStateMismatchHtml()).toContain("State mismatch");
    expect(getAuthorizationErrorHtml({ error: "denied", error_description: "nope" })).toContain("denied");
    expect(getAuthorizationSuccessHtml()).toContain("Authorization successful");
  });

  it("handles callback outcomes and writes socket responses", () => {
    expect(handleCallbackParams({ state: "bad" }, "good")).toMatchObject({ type: "reject" });
    expect(handleCallbackParams({ state: "good", error: "denied" }, "good")).toMatchObject({
      type: "resolve",
      result: { error: "denied" },
    });
    expect(handleCallbackParams({ state: "good", code: "abc" }, "good")).toMatchObject({
      type: "resolve",
      result: { code: "abc", state: "good" },
    });
    expect(handleCallbackParams({ state: "good" }, "good")).toMatchObject({ type: "ignore" });

    const socket = { write: vi.fn(), end: vi.fn() } as unknown as NodeJS.WritableStream;
    writeHtmlResponse(socket, "HTTP/1.1 200 OK", "<html>ok</html>");
    expect((socket as unknown as { write: ReturnType<typeof vi.fn> }).write).toHaveBeenCalled();

    writeOutcomeResponse(socket as unknown as NodeJS.Socket, {
      type: "resolve",
      html: "<html>ok</html>",
      result: { code: "abc", state: "good" },
    });
    expect((socket as unknown as { end: ReturnType<typeof vi.fn> }).end).toHaveBeenCalled();

    const first = processCallbackChunk("", Buffer.from("GET /callback?state=good"), "good");
    expect(first.outcome.type).toBe("ignore");

    const second = processCallbackChunk(
      first.buffer,
      Buffer.from("&code=abc HTTP/1.1\r\nHost: localhost\r\n\r\n"),
      "good",
    );
    expect(second.outcome).toMatchObject({ type: "resolve", result: { code: "abc" } });
  });

  it("persists, reads, and clears OAuth token storage", async () => {
    const baseDir = mkdtempSync(join(tmpdir(), "pi-notion-oauth-storage-"));
    const basePath = join(baseDir, "notion.json");
    const storage = new FileTokenStorage(basePath);

    const tokens = {
      accessToken: "access",
      refreshToken: "refresh",
      tokenType: "Bearer",
      expiresAt: Date.now() + 1000,
    };
    const userInfo = {
      workspaceId: "ws",
      workspaceName: "Workspace",
      botId: "bot",
    };

    await storage.save(tokens, userInfo);
    const raw = readFileSync(basePath.replace(/\.json$/, "-tokens.json"), "utf-8");
    expect(raw).toContain("access");
    expect(await storage.load()).toEqual(tokens);
    expect(await storage.getUserInfo()).toEqual(userInfo);

    await storage.clear();
    expect(await storage.load()).toBeNull();
    expect(await storage.getUserInfo()).toBeNull();
  });

  it("exchanges auth codes for tokens and refreshes them", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          access_token: "access-token",
          refresh_token: "refresh-token",
          token_type: "bearer",
          workspace_id: "ws-1",
          workspace_name: "Workspace",
          workspace_icon: "📝",
          bot_id: "bot-1",
          owner: {
            user: {
              name: "Test User",
              person: { email: "user@example.com" },
            },
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          access_token: "new-access",
          token_type: "bearer",
        }),
      });

    global.fetch = fetchMock as typeof fetch;

    const exchanged = await exchangeCodeForTokens(config, "auth-code", "verifier");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/oauth/token"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          grant_type: "authorization_code",
          code: "auth-code",
          redirect_uri: config.redirectUri,
          client_id: config.clientId,
          client_secret: config.clientSecret,
          code_verifier: "verifier",
        }),
      }),
    );
    expect(exchanged.owner).toEqual({
      workspaceId: "ws-1",
      workspaceName: "Workspace",
      workspaceIcon: "📝",
      botId: "bot-1",
      ownerEmail: "user@example.com",
      ownerName: "Test User",
    });

    const refreshed = await refreshTokens(config, "existing-refresh");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/oauth/token"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          grant_type: "refresh_token",
          refresh_token: "existing-refresh",
          client_id: config.clientId,
          client_secret: config.clientSecret,
        }),
      }),
    );
    expect(refreshed.accessToken).toBe("new-access");
    expect(refreshed.refreshToken).toBe("existing-refresh");
  });

  it("returns an existing valid access token without refreshing", async () => {
    const storage: TokenStorage = {
      save: vi.fn(),
      load: vi.fn(
        async () =>
          ({
            accessToken: "still-valid",
            refreshToken: "refresh",
            tokenType: "bearer",
            expiresAt: Date.now() + 60 * 60 * 1000,
          }) satisfies OAuthTokens,
      ),
      clear: vi.fn(),
      getUserInfo: vi.fn(async () => null),
    };

    expect(await getValidAccessToken(config, storage)).toBe("still-valid");
  });

  it("refreshes expiring tokens through storage and clears storage on refresh failure", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          access_token: "refreshed-access",
          refresh_token: "refreshed-refresh",
          token_type: "bearer",
        }),
      })
      .mockRejectedValueOnce(new Error("refresh failed")) as typeof fetch;

    const save = vi.fn();
    const refreshableStorage: TokenStorage = {
      save,
      load: vi.fn(
        async () =>
          ({
            accessToken: "old-access",
            refreshToken: "old-refresh",
            tokenType: "bearer",
            expiresAt: Date.now() + 60 * 1000,
          }) satisfies OAuthTokens,
      ),
      clear: vi.fn(),
      getUserInfo: vi.fn(async () => ({ workspaceId: "ws", workspaceName: "WS", botId: "bot" })),
    };

    expect(await getValidAccessToken(config, refreshableStorage)).toBe("refreshed-access");
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ accessToken: "refreshed-access", refreshToken: "refreshed-refresh" }),
      expect.objectContaining({ workspaceId: "ws" }),
    );

    const clear = vi.fn();
    const failingStorage: TokenStorage = {
      save: vi.fn(),
      load: vi.fn(
        async () =>
          ({
            accessToken: "old-access",
            refreshToken: "old-refresh",
            tokenType: "bearer",
            expiresAt: Date.now() - 1000,
          }) satisfies OAuthTokens,
      ),
      clear,
      getUserInfo: vi.fn(async () => null),
    };

    await expect(getValidAccessToken(config, failingStorage)).rejects.toThrow("Token refresh failed: refresh failed");
    expect(clear).toHaveBeenCalled();
  });

  it("returns null when no token is stored and executes the full OAuth flow", async () => {
    const emptyStorage: TokenStorage = {
      save: vi.fn(),
      load: vi.fn(async () => null),
      clear: vi.fn(),
      getUserInfo: vi.fn(async () => null),
    };
    expect(await getValidAccessToken(config, emptyStorage)).toBeNull();

    const flowStorage: TokenStorage = {
      save: vi.fn(),
      load: vi.fn(async () => null),
      clear: vi.fn(),
      getUserInfo: vi.fn(async () => null),
    };
    const openBrowser = vi.fn();
    const notify = vi.fn();

    const result = await executeOAuthFlow(config, flowStorage, openBrowser, notify, {
      generateCodeVerifierFn: () => "verifier",
      generateCodeChallengeFn: () => "challenge",
      generateStateFn: () => "state-123",
      startCallbackServerFn: async () => ({ code: "auth-code", state: "state-123" }),
      exchangeCodeForTokensFn: async () => ({
        accessToken: "access-token",
        refreshToken: "refresh-token",
        tokenType: "bearer",
        expiresAt: Date.now() + 3600 * 1000,
        owner: {
          workspaceId: "ws-1",
          workspaceName: "Workspace",
          botId: "bot-1",
          ownerEmail: "user@example.com",
          ownerName: "Test User",
        },
      }),
    });

    expect(openBrowser).toHaveBeenCalled();
    expect(flowStorage.save).toHaveBeenCalled();
    expect(notify).toHaveBeenCalledWith("OAuth authorization successful!", "success");
    expect(result.tokens.accessToken).toBe("access-token");
    expect(result.userInfo.workspaceId).toBe("ws-1");
  });
});
