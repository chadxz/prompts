import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const packageJson = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf-8")) as {
  pi: {
    extensions: string[];
    skills?: string[];
  };
};

describe("package.json", () => {
  it("declares pi metadata so the package loads as an extension", () => {
    expect(packageJson.pi.extensions).toEqual(["./extensions/pi-notion-mcp.ts"]);
    expect(packageJson.pi.skills).toBeUndefined();
  });
});
