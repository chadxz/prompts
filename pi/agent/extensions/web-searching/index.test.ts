import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import registerExtension, {
	createFetchWebContentTool,
	createWebSearchTool,
	DEFAULT_COUNTRY,
	DEFAULT_SEARCH_COUNT,
	FETCH_WEB_CONTENT_TOOL_NAME,
	MAX_SEARCH_COUNT,
	normalizeCountry,
	normalizeFiletype,
	normalizeLanguage,
	normalizeSite,
	normalizeCount,
	runScript,
	buildSearchQuery,
	truncateForToolOutput,
	WEB_SEARCH_TOOL_NAME,
} from "./index.ts";

const cleanupPaths = new Set<string>();
const testTheme = {
	fg: (_token: string, text: string) => text,
	bold: (text: string) => text,
} as never;

afterEach(async () => {
	await Promise.all(
		[...cleanupPaths].map(async (path) => {
			await rm(path, { recursive: true, force: true });
		}),
	);
	cleanupPaths.clear();
});

describe("normalization helpers", () => {
	it("normalizes site, filetype, language, country, and count values", () => {
		expect(normalizeSite(" https://docs.python.org/3/library/dataclasses.html?x=1 ")).toBe(
			"docs.python.org",
		);
		expect(normalizeFiletype(" .PDF ")).toBe("pdf");
		expect(normalizeLanguage(" EN ")).toBe("en");
		expect(normalizeCountry(" us ")).toBe("US");
		expect(normalizeCountry()).toBe(DEFAULT_COUNTRY);
		expect(normalizeCount()).toBe(DEFAULT_SEARCH_COUNT);
		expect(normalizeCount(999)).toBe(MAX_SEARCH_COUNT);
		expect(normalizeCount(-3)).toBe(1);
	});

	it("builds an effective query with all supported first-class filters", () => {
		expect(
			buildSearchQuery({
				query: "python dataclasses",
				site: "https://docs.python.org/3/library/dataclasses.html",
				filetype: ".PDF",
				language: "EN",
			}),
		).toEqual({
			query: "python dataclasses",
			site: "docs.python.org",
			filetype: "pdf",
			language: "en",
			effectiveQuery: "python dataclasses site:docs.python.org filetype:pdf lang:en",
		});
	});

	it("rejects empty search queries", () => {
		expect(() =>
			buildSearchQuery({ query: "   ", site: undefined, filetype: undefined, language: undefined }),
		).toThrowError("Search query must not be empty.");
	});
});

describe("runScript", () => {
	it("executes scripts and returns stdout and stderr", async () => {
		const scriptDir = await mkdtemp(join(tmpdir(), "pi-web-search-script-success-"));
		cleanupPaths.add(scriptDir);
		const scriptPath = join(scriptDir, "success.mjs");
		await writeFile(
			scriptPath,
			[
				"process.stdout.write(`ok:${process.argv.slice(2).join(',')}`);",
				"process.stderr.write('warn');",
			].join("\n"),
			"utf8",
		);

		await expect(runScript(scriptPath, ["alpha", "beta"])).resolves.toEqual({
			stdout: "ok:alpha,beta",
			stderr: "warn",
		});
	});

	it("surfaces helpful messages when scripts fail", async () => {
		const scriptDir = await mkdtemp(join(tmpdir(), "pi-web-search-script-fail-"));
		cleanupPaths.add(scriptDir);
		const scriptPath = join(scriptDir, "fail.mjs");
		await writeFile(scriptPath, ["process.stderr.write('boom');", "process.exit(1);"].join("\n"), "utf8");

		await expect(runScript(scriptPath, [])).rejects.toThrowError("boom");
	});
});

describe("truncateForToolOutput", () => {
	it("returns original text when truncation is not needed", async () => {
		const result = await truncateForToolOutput("short output", "Search output", {
			maxLines: 10,
			maxBytes: 100,
		});

		expect(result.text).toBe("short output");
		expect(result.details).toEqual({});
	});

	it("writes the full output to a temp file when truncation is needed", async () => {
		const largeOutput = Array.from({ length: 12 }, (_, index) => `line ${index + 1}`).join("\n");
		const result = await truncateForToolOutput(largeOutput, "Search output", {
			maxLines: 3,
			maxBytes: 10_000,
			tempDirPrefix: "pi-web-search-test-",
		});

		expect(result.text).toContain("[Search output truncated:");
		expect(result.details.fullOutputPath).toBeTypeOf("string");
		const fullOutputPath = result.details.fullOutputPath as string;
		cleanupPaths.add(dirname(fullOutputPath));
		expect(await readFile(fullOutputPath, "utf8")).toBe(largeOutput);
	});
});

describe("web_search tool", () => {
	it("exposes the full first-class search parameter surface", () => {
		const tool = createWebSearchTool();
		const schema = tool.parameters as { properties: Record<string, unknown> };

		expect(tool.name).toBe(WEB_SEARCH_TOOL_NAME);
		expect(Object.keys(schema.properties)).toEqual([
			"query",
			"site",
			"filetype",
			"language",
			"count",
			"includeContent",
			"country",
			"freshness",
		]);
	});

	it("executes searches with normalized filters and rich details", async () => {
		const runScript = vi.fn().mockResolvedValue({
			stdout: "--- Result 1 ---\nTitle: dataclasses\nLink: https://docs.python.org/3/library/dataclasses.html",
			stderr: "",
		});
		const truncateOutput = vi.fn().mockResolvedValue({
			text: "formatted search results",
			details: { formatter: "test-double" },
		});
		const tool = createWebSearchTool({
			runScript,
			truncateOutput,
			searchScriptPath: "/tmp/search.js",
		});
		const onUpdate = vi.fn();

		const result = await tool.execute(
			"tool-call-1",
			{
				query: "python dataclasses",
				site: "https://docs.python.org/3/library/dataclasses.html",
				filetype: ".PDF",
				language: "EN",
				count: 99,
				includeContent: true,
				country: "gb",
				freshness: "pm",
			},
			undefined,
			onUpdate,
		);

		expect(onUpdate).toHaveBeenCalledWith({
			content: [
				{
					type: "text",
					text: "Searching the web for: python dataclasses site:docs.python.org filetype:pdf lang:en",
				},
			],
			details: {
				phase: "searching",
				site: "docs.python.org",
				filetype: "pdf",
				language: "en",
			},
		});
		expect(runScript).toHaveBeenCalledWith(
			"/tmp/search.js",
			[
				"python dataclasses site:docs.python.org filetype:pdf lang:en",
				"-n",
				String(MAX_SEARCH_COUNT),
				"--country",
				"GB",
				"--content",
				"--freshness",
				"pm",
			],
			undefined,
		);
		expect(truncateOutput).toHaveBeenCalledWith(
			"--- Result 1 ---\nTitle: dataclasses\nLink: https://docs.python.org/3/library/dataclasses.html",
			"Search output",
		);
		expect(result).toEqual({
			content: [{ type: "text", text: "formatted search results" }],
			details: {
				query: "python dataclasses",
				effectiveQuery: "python dataclasses site:docs.python.org filetype:pdf lang:en",
				site: "docs.python.org",
				filetype: "pdf",
				language: "en",
				count: MAX_SEARCH_COUNT,
				includeContent: true,
				country: "GB",
				freshness: "pm",
				resultCount: 1,
				outputLineCount: 3,
				formatter: "test-double",
			},
		});
	});

	it("uses sensible defaults when optional parameters are omitted", async () => {
		const runScript = vi.fn().mockResolvedValue({ stdout: "", stderr: "" });
		const tool = createWebSearchTool({
			runScript,
			truncateOutput: vi.fn().mockResolvedValue({ text: "No results found.", details: {} }),
			searchScriptPath: "/tmp/search.js",
		});

		const result = await tool.execute("tool-call-2", { query: "plain query" });

		expect(runScript).toHaveBeenCalledWith(
			"/tmp/search.js",
			["plain query", "-n", String(DEFAULT_SEARCH_COUNT), "--country", DEFAULT_COUNTRY],
			undefined,
		);
		expect(result.details).toMatchObject({
			query: "plain query",
			effectiveQuery: "plain query",
			site: undefined,
			filetype: undefined,
			language: undefined,
			count: DEFAULT_SEARCH_COUNT,
			includeContent: false,
			country: DEFAULT_COUNTRY,
			freshness: undefined,
			resultCount: 0,
			outputLineCount: 1,
		});
	});

	it("renders compact UI summaries instead of raw search output", async () => {
		const tool = createWebSearchTool({
			runScript: vi.fn(),
			truncateOutput: vi.fn(),
		});
		const renderedCall = tool.renderCall?.(
			{ query: "python dataclasses", site: "https://docs.python.org/3/library/dataclasses.html" },
			testTheme,
			{},
		);
		const renderedResult = tool.renderResult?.(
			{
				content: [{ type: "text", text: "--- Result 1 ---\nTitle: dataclasses\nSnippet: do not show me" }],
				details: {
					resultCount: 1,
					outputLineCount: 3,
					site: "docs.python.org",
					includeContent: true,
				},
			},
			{ expanded: false, isPartial: false },
			testTheme,
			{ isError: false },
		);

		expect(renderedCall?.render(120).join("\n")).toContain("web_search python dataclasses");
		expect(renderedResult?.render(120).join("\n")).toContain("1 result with page content");
		expect(renderedResult?.render(120).join("\n")).not.toContain("Snippet: do not show me");
	});

	it("renders partial, error, and expanded metadata states for search", () => {
		const tool = createWebSearchTool({ runScript: vi.fn(), truncateOutput: vi.fn() });

		expect(
			tool.renderResult?.(
				{ content: [], details: {} },
				{ expanded: false, isPartial: true },
				testTheme,
				{ isError: false },
			)?.render(120).join("\n"),
		).toContain("Searching...");

		expect(
			tool.renderResult?.(
				{ content: [{ type: "text", text: "catastrophic search failure" }], details: {} },
				{ expanded: false, isPartial: false },
				testTheme,
				{ isError: true },
			)?.render(120).join("\n"),
		).toContain("catastrophic search failure");

		expect(
			tool.renderResult?.(
				{
					content: [{ type: "text", text: "hidden body" }],
					details: {
						resultCount: 2,
						outputLineCount: 7,
						site: "docs.python.org",
						filetype: "pdf",
						language: "en",
						freshness: "pm",
						country: "US",
						truncation: { truncated: true },
					},
				},
				{ expanded: true, isPartial: false },
				testTheme,
				{ isError: false },
			)?.render(120).join("\n"),
		).toContain("site: docs.python.org");
	});
});

describe("fetch_web_content tool", () => {
	it("exposes the fetch URL parameter and executes fetches", async () => {
		const runScript = vi.fn().mockResolvedValue({ stdout: "# Article\n\nBody", stderr: "" });
		const truncateOutput = vi.fn().mockResolvedValue({
			text: "formatted page content",
			details: { extracted: true },
		});
		const tool = createFetchWebContentTool({
			runScript,
			truncateOutput,
			contentScriptPath: "/tmp/content.js",
		});
		const onUpdate = vi.fn();

		const result = await tool.execute(
			"tool-call-3",
			{ url: " https://example.com/article " },
			undefined,
			onUpdate,
		);

		expect(tool.name).toBe(FETCH_WEB_CONTENT_TOOL_NAME);
		expect(onUpdate).toHaveBeenCalledWith({
			content: [{ type: "text", text: "Fetching page content: https://example.com/article" }],
			details: { phase: "fetching" },
		});
		expect(runScript).toHaveBeenCalledWith(
			"/tmp/content.js",
			["https://example.com/article"],
			undefined,
		);
		expect(result).toEqual({
			content: [{ type: "text", text: "formatted page content" }],
			details: {
				url: "https://example.com/article",
				outputLineCount: 2,
				characterCount: 15,
				extracted: true,
			},
		});
	});

	it("rejects empty URLs", async () => {
		const tool = createFetchWebContentTool({
			runScript: vi.fn(),
			truncateOutput: vi.fn(),
		});

		await expect(tool.execute("tool-call-4", { url: "   " })).rejects.toThrowError(
			"URL must not be empty.",
		);
	});

	it("renders compact UI summaries instead of fetched content", () => {
		const tool = createFetchWebContentTool({
			runScript: vi.fn(),
			truncateOutput: vi.fn(),
		});
		const renderedCall = tool.renderCall?.({ url: "https://example.com/article" }, testTheme, {});
		const renderedResult = tool.renderResult?.(
			{
				content: [{ type: "text", text: "# Title\n\nVery long fetched content that should stay hidden" }],
				details: {
					url: "https://example.com/article",
					outputLineCount: 3,
					characterCount: 55,
				},
			},
			{ expanded: true, isPartial: false },
			testTheme,
			{ isError: false },
		);

		expect(renderedCall?.render(160).join("\n")).toContain("fetch_web_content https://example.com/article");
		expect(renderedResult?.render(160).join("\n")).toContain("Content fetched (3 lines, 55 chars)");
		expect(renderedResult?.render(160).join("\n")).toContain("https://example.com/article");
		expect(renderedResult?.render(160).join("\n")).not.toContain("Very long fetched content");
	});

	it("renders partial, error, and truncated fetch states without leaking body text", () => {
		const tool = createFetchWebContentTool({ runScript: vi.fn(), truncateOutput: vi.fn() });

		expect(
			tool.renderResult?.(
				{ content: [], details: {} },
				{ expanded: false, isPartial: true },
				testTheme,
				{ isError: false },
			)?.render(120).join("\n"),
		).toContain("Fetching...");

		expect(
			tool.renderResult?.(
				{ content: [{ type: "text", text: "fetch exploded badly" }], details: {} },
				{ expanded: false, isPartial: false },
				testTheme,
				{ isError: true },
			)?.render(120).join("\n"),
		).toContain("fetch exploded badly");

		expect(
			tool.renderResult?.(
				{
					content: [{ type: "text", text: "hidden fetch body" }],
					details: {
						outputLineCount: 4,
						characterCount: 80,
						truncation: { truncated: true },
					},
				},
				{ expanded: false, isPartial: false },
				testTheme,
				{ isError: false },
			)?.render(120).join("\n"),
		).toContain("[truncated]");
	});
});

describe("extension registration", () => {
	it("registers both public tools with pi", () => {
		const registerTool = vi.fn();

		registerExtension({ registerTool } as never);

		expect(registerTool).toHaveBeenCalledTimes(2);
		expect(registerTool.mock.calls[0]?.[0]?.name).toBe(WEB_SEARCH_TOOL_NAME);
		expect(registerTool.mock.calls[1]?.[0]?.name).toBe(FETCH_WEB_CONTENT_TOOL_NAME);
	});
});
