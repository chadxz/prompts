import { describe, expect, it } from "vitest";
import { applyToolDefaults } from "./providers/notion/pi-notion-mcp.ts";

describe("Notion provider defaults", () => {
  it("adds workspace_search for notion-search when query_type is omitted", () => {
    expect(
      applyToolDefaults("notion-search", {
        query: "incident review",
        filters: {},
      }),
    ).toMatchObject({
      query: "incident review",
      filters: {},
      content_search_mode: "workspace_search",
    });
  });

  it("does not add content_search_mode for notion user searches", () => {
    expect(
      applyToolDefaults("notion-search", {
        query: "chad",
        query_type: "user",
        filters: {},
      }),
    ).toEqual({
      query: "chad",
      query_type: "user",
      filters: {},
    });
  });

  it("preserves an explicit content_search_mode", () => {
    expect(
      applyToolDefaults("notion-search", {
        query: "incident review",
        query_type: "content",
        content_search_mode: "ai_search",
        filters: {},
      }),
    ).toEqual({
      query: "incident review",
      query_type: "content",
      content_search_mode: "ai_search",
      filters: {},
    });
  });
});
