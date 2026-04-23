import { describe, expect, it } from "vitest";

import {
  buildAuthorizationUrl,
  buildPreviewLines,
  buildSlackCallSummary,
  normalizeMcpToolResult,
  parseSlackTokenBundle,
} from "./extensions/pi-slack-mcp";

describe("buildAuthorizationUrl", () => {
  it("includes the Slack MCP user scopes and PKCE parameters", () => {
    const url = new URL(
      buildAuthorizationUrl(
        "123.456",
        "http://127.0.0.1:8315/oauth/callback",
        "challenge",
        "state-123",
      ),
    );

    expect(url.origin + url.pathname).toBe("https://slack.com/oauth/v2/authorize");
    expect(url.searchParams.get("client_id")).toBe("123.456");
    expect(url.searchParams.get("redirect_uri")).toBe("http://127.0.0.1:8315/oauth/callback");
    expect(url.searchParams.get("code_challenge")).toBe("challenge");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("user_scope")).toContain("chat:write");
    expect(url.searchParams.get("user_scope")).toContain("users:read.email");
  });
});

describe("parseSlackTokenBundle", () => {
  it("prefers authed_user tokens when Slack returns both bot and user tokens", () => {
    const bundle = parseSlackTokenBundle({
      ok: true,
      access_token: "xoxe.xoxb-root",
      refresh_token: "xoxe-root-refresh",
      expires_in: 43200,
      team: { id: "T123", name: "Convergint" },
      authed_user: {
        id: "U123",
        access_token: "xoxe.xoxp-user",
        refresh_token: "xoxe-user-refresh",
        expires_in: 43200,
      },
    });

    expect(bundle.accessToken).toBe("xoxe.xoxp-user");
    expect(bundle.refreshToken).toBe("xoxe-user-refresh");
    expect(bundle.teamId).toBe("T123");
    expect(bundle.teamName).toBe("Convergint");
    expect(bundle.userId).toBe("U123");
    expect(bundle.expiresAt).toBeGreaterThan(Date.now());
  });
});

describe("buildSlackCallSummary", () => {
  it("summarizes Slack searches compactly", () => {
    expect(
      buildSlackCallSummary("slack_search_messages", {
        query: "incident review",
        channel_id: "C123",
        limit: 25,
      }),
    ).toEqual({
      primary: "incident review",
      meta: ["channel=C123", "limit=25"],
    });
  });

  it("includes a text preview for send and post style tools", () => {
    const summary = buildSlackCallSummary("slack_send_message", {
      channel: "C123",
      text: "hello from pi",
    });

    expect(summary.primary).toBe("C123");
    expect(summary.meta).toContain("text=hello from pi");
  });
});

describe("normalizeMcpToolResult", () => {
  it("joins text content items", () => {
    expect(
      normalizeMcpToolResult({
        content: [
          { type: "text", text: "first" },
          { type: "text", text: "second" },
        ],
      }),
    ).toBe("first\nsecond");
  });

  it("falls back to structuredContent when no text content exists", () => {
    expect(
      normalizeMcpToolResult({
        structuredContent: { ok: true, items: 3 },
      }),
    ).toContain('"items": 3');
  });
});

describe("buildPreviewLines", () => {
  it("returns non-empty preview lines only", () => {
    expect(buildPreviewLines("one\n\n two \nthree", 5)).toEqual(["one", "two", "three"]);
  });
});
