import { describe, expect, it } from "vitest";
import {
  CALLBACK_PATH,
  CLOUDFLARE_MCP_URL,
  CloudflareMCPClient,
  getConnectionStatusText,
  isExpectedAuthorizationIssuer,
  isSafeAuthorizationUrl,
} from "./providers/cloudflare/pi-cloudflare-mcp.ts";

describe("Cloudflare provider defaults", () => {
  it("uses Cloudflare's compact code-mode MCP endpoint", () => {
    expect(CLOUDFLARE_MCP_URL).toBe("https://mcp.cloudflare.com/mcp");
    expect(CALLBACK_PATH).toBe("/oauth/callback");
  });

  it("only opens authorization URLs on Cloudflare's HTTPS host", () => {
    expect(
      isSafeAuthorizationUrl(
        new URL("https://mcp.cloudflare.com/authorize?client_id=example"),
      ),
    ).toBe(true);
    expect(
      isSafeAuthorizationUrl(
        new URL("https://mcp.cloudflare.com.evil.example/authorize"),
      ),
    ).toBe(false);
    expect(
      isSafeAuthorizationUrl(
        new URL("http://mcp.cloudflare.com/authorize"),
      ),
    ).toBe(false);
  });

  it("rejects a conflicting OAuth issuer while tolerating Cloudflare's omission", () => {
    expect(isExpectedAuthorizationIssuer(null)).toBe(true);
    expect(isExpectedAuthorizationIssuer("https://mcp.cloudflare.com")).toBe(true);
    expect(isExpectedAuthorizationIssuer("https://example.com")).toBe(false);
  });

  it("reports disconnected state without contacting Cloudflare", () => {
    const client = new CloudflareMCPClient();

    expect(getConnectionStatusText(client)).toContain("- Connected: No");
    expect(getConnectionStatusText(client)).toContain(
      "Run /mux connect cloudflare to connect.",
    );
  });
});
