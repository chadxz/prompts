import { describe, expect, it } from "vitest";
import {
  buildDatadogMcpUrl,
  buildDisconnectedMessage,
  getEffectiveConfig,
} from "./providers/datadog/pi-datadog-mcp.ts";

describe("Datadog provider defaults", () => {
  it("uses toolsets=all when toolsets are not configured", () => {
    const config = getEffectiveConfig(null, {});

    expect(config.toolsets).toEqual(["all"]);
    expect(config.mcpUrl).toBe(
      "https://mcp.us3.datadoghq.com/api/unstable/mcp-server/mcp?toolsets=all",
    );
  });

  it("adds toolsets=all to URL overrides when toolsets are not configured", () => {
    expect(
      buildDatadogMcpUrl("us3", "https://example.com/custom?foo=bar", []),
    ).toBe("https://example.com/custom?foo=bar&toolsets=all");
  });

  it("reports all as the default Datadog toolset", () => {
    const config = getEffectiveConfig(null, {});

    expect(buildDisconnectedMessage(config)).toContain(
      "- Toolsets: all (default)",
    );
  });
});
