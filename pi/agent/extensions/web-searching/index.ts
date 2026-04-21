import { execFile } from "node:child_process";
import { access, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import {
	DEFAULT_MAX_BYTES,
	DEFAULT_MAX_LINES,
	formatSize,
	truncateHead,
} from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type, type Static } from "@sinclair/typebox";

const execFileAsync = promisify(execFile);

export const WEB_SEARCH_TOOL_NAME = "web_search";
export const FETCH_WEB_CONTENT_TOOL_NAME = "fetch_web_content";
export const DEFAULT_SEARCH_COUNT = 5;
export const MAX_SEARCH_COUNT = 20;
export const DEFAULT_COUNTRY = "US";

export interface ScriptExecutionResult {
	stdout: string;
	stderr: string;
}

export interface TextContentBlock {
	type: "text";
	text: string;
}

export interface ToolUpdatePayload {
	content: TextContentBlock[];
	details?: Record<string, unknown>;
}

export interface ToolExecutionResult {
	content: TextContentBlock[];
	details: Record<string, unknown>;
}

export type ToolUpdateCallback = (payload: ToolUpdatePayload) => void;
export type ScriptRunner = (
	scriptPath: string,
	args: string[],
	signal?: AbortSignal,
) => Promise<ScriptExecutionResult>;

export interface TruncateOptions {
	maxLines?: number;
	maxBytes?: number;
	tempDirPrefix?: string;
}

export interface CreateToolOptions {
	runScript?: ScriptRunner;
	truncateOutput?: typeof truncateForToolOutput;
	searchScriptPath?: string;
	contentScriptPath?: string;
}

export const webSearchParameters = Type.Object({
	query: Type.String({ minLength: 1, description: "Search query" }),
	site: Type.Optional(
		Type.String({
			description: "Restrict results to a specific site or domain, e.g. docs.python.org or github.com.",
		}),
	),
	filetype: Type.Optional(
		Type.String({
			description: "Restrict results to a specific file type or extension, e.g. pdf, html, or md.",
		}),
	),
	language: Type.Optional(
		Type.String({
			description: "Restrict results to a language code, e.g. en, de, fr, or ja.",
		}),
	),
	count: Type.Optional(
		Type.Integer({
			minimum: 1,
			maximum: MAX_SEARCH_COUNT,
			description: `Number of results to return. Default: ${DEFAULT_SEARCH_COUNT}, max: ${MAX_SEARCH_COUNT}.`,
		}),
	),
	includeContent: Type.Optional(
		Type.Boolean({ description: "Whether to fetch readable page content for each result." }),
	),
	country: Type.Optional(
		Type.String({ description: `Two-letter country code. Default: ${DEFAULT_COUNTRY}.` }),
	),
	freshness: Type.Optional(
		Type.String({ description: "Freshness filter: pd, pw, pm, py, or YYYY-MM-DDtoYYYY-MM-DD." }),
	),
});

export const fetchWebContentParameters = Type.Object({
	url: Type.String({ minLength: 1, description: "The URL to fetch and extract readable content from." }),
});

export type WebSearchParams = Static<typeof webSearchParameters>;
export type FetchWebContentParams = Static<typeof fetchWebContentParameters>;

const extensionDir = dirname(fileURLToPath(import.meta.url));
const searchScriptPath = join(extensionDir, "search.js");
const contentScriptPath = join(extensionDir, "content.js");

function readErrorProperty(error: unknown, key: "stdout" | "stderr" | "message") {
	if (typeof error !== "object" || error === null) return undefined;
	const value = Reflect.get(error, key);
	return typeof value === "string" ? value.trim() : undefined;
}

function getErrorMessage(error: unknown) {
	return (
		readErrorProperty(error, "stderr") ??
		readErrorProperty(error, "stdout") ??
		readErrorProperty(error, "message") ??
		"Unknown error"
	);
}

export function normalizeSite(site: string) {
	return site
		.trim()
		.replace(/^[a-z]+:\/\//i, "")
		.replace(/[/?#].*$/, "")
		.replace(/\/$/, "");
}

export function normalizeFiletype(filetype: string) {
	return filetype.trim().replace(/^\./, "").toLowerCase();
}

export function normalizeLanguage(language: string) {
	return language.trim().toLowerCase();
}

export function normalizeCountry(country?: string) {
	return country?.trim() ? country.trim().toUpperCase() : DEFAULT_COUNTRY;
}

export function normalizeCount(count?: number) {
	return Math.min(Math.max(count ?? DEFAULT_SEARCH_COUNT, 1), MAX_SEARCH_COUNT);
}

export function buildSearchQuery(params: Pick<WebSearchParams, "query" | "site" | "filetype" | "language">) {
	const query = params.query.trim();
	if (!query) {
		throw new Error("Search query must not be empty.");
	}

	const site = params.site?.trim() ? normalizeSite(params.site) : undefined;
	const filetype = params.filetype?.trim() ? normalizeFiletype(params.filetype) : undefined;
	const language = params.language?.trim() ? normalizeLanguage(params.language) : undefined;

	const parts = [query];
	if (site) parts.push(`site:${site}`);
	if (filetype) parts.push(`filetype:${filetype}`);
	if (language) parts.push(`lang:${language}`);

	return {
		query,
		site,
		filetype,
		language,
		effectiveQuery: parts.join(" "),
	};
}

export function truncateDisplayText(text: string, maxLength = 72) {
	return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

export function countSearchResults(output: string) {
	return output.match(/^--- Result \d+ ---$/gm)?.length ?? 0;
}

export function countOutputLines(output: string) {
	return output.split("\n").filter((line) => line.trim()).length;
}

async function ensureToolFiles() {
	await Promise.all([access(searchScriptPath), access(contentScriptPath)]);
}

export async function runScript(
	scriptPath: string,
	args: string[],
	signal?: AbortSignal,
): Promise<ScriptExecutionResult> {
	await ensureToolFiles();

	try {
		const result = await execFileAsync(process.execPath, [scriptPath, ...args], {
			cwd: extensionDir,
			signal,
			env: process.env,
			maxBuffer: 20 * 1024 * 1024,
		});
		return {
			stdout: result.stdout,
			stderr: result.stderr,
		};
	} catch (error) {
		throw new Error(getErrorMessage(error));
	}
}

export async function truncateForToolOutput(
	output: string,
	prefix: string,
	options: TruncateOptions = {},
) {
	const truncation = truncateHead(output, {
		maxLines: options.maxLines ?? DEFAULT_MAX_LINES,
		maxBytes: options.maxBytes ?? DEFAULT_MAX_BYTES,
	});

	const details: Record<string, unknown> = {};
	let text = truncation.content;

	if (truncation.truncated) {
		const tempDir = await mkdtemp(join(tmpdir(), options.tempDirPrefix ?? "pi-web-search-"));
		const tempFile = join(tempDir, "output.txt");
		await writeFile(tempFile, output, "utf8");

		details.truncation = truncation;
		details.fullOutputPath = tempFile;

		text += `\n\n[${prefix} truncated: showing ${truncation.outputLines} of ${truncation.totalLines} lines`;
		text += ` (${formatSize(truncation.outputBytes)} of ${formatSize(truncation.totalBytes)}).`;
		text += ` Full output saved to: ${tempFile}]`;
	}

	return { text, details };
}

export function createWebSearchTool(options: CreateToolOptions = {}) {
	const scriptRunner = options.runScript ?? runScript;
	const truncateOutput = options.truncateOutput ?? truncateForToolOutput;
	const scriptPath = options.searchScriptPath ?? searchScriptPath;

	return {
		name: WEB_SEARCH_TOOL_NAME,
		label: "Web Search",
		description: `Search the web using Brave Search. Supports current info, documentation lookup, and fact checking. Output is truncated to ${DEFAULT_MAX_LINES} lines or ${formatSize(DEFAULT_MAX_BYTES)}.`,
		promptSnippet:
			"Search the web for current information, docs, facts, and references. Optionally include readable page content in the results.",
		promptGuidelines: [
			"Use web_search when the user needs current information, web documentation, or fact checking.",
			"Prefer web_search before fetching a full page unless the user already provided a specific URL.",
			"Use the site parameter when the user wants results from only one website or domain.",
			"Use the filetype parameter when the user wants a PDF, manual, whitepaper, or another specific document format.",
			"Use the language parameter when the user wants results in a specific language.",
		],
		parameters: webSearchParameters,
		renderCall(args, theme) {
			let text = theme.fg("toolTitle", theme.bold("web_search "));
			text += theme.fg("accent", truncateDisplayText(args.query));
			const filters: string[] = [];
			if (args.site) filters.push(`site=${normalizeSite(args.site)}`);
			if (args.filetype) filters.push(`type=${normalizeFiletype(args.filetype)}`);
			if (args.language) filters.push(`lang=${normalizeLanguage(args.language)}`);
			if (filters.length > 0) {
				text += theme.fg("dim", ` (${filters.join(", ")})`);
			}
			return new Text(text, 0, 0);
		},
		renderResult(result, { expanded, isPartial }, theme, context) {
			if (isPartial) {
				return new Text(theme.fg("warning", "Searching..."), 0, 0);
			}

			const details = result.details as Record<string, unknown> | undefined;
			if (context.isError) {
				const content = result.content[0];
				const errorText = content?.type === "text" ? truncateDisplayText(content.text, 120) : "Search failed";
				return new Text(theme.fg("error", errorText), 0, 0);
			}

			const resultCount = typeof details?.resultCount === "number" ? details.resultCount : 0;
			const lineCount = typeof details?.outputLineCount === "number" ? details.outputLineCount : 0;
			let text = resultCount > 0 ? theme.fg("success", `${resultCount} result${resultCount === 1 ? "" : "s"}`) : theme.fg("dim", "No results");
			if (details?.includeContent) {
				text += theme.fg("muted", " with page content");
			}
			if (details?.truncation && typeof details.truncation === "object" && details.truncation !== null) {
				text += theme.fg("warning", " [truncated]");
			}
			if (expanded) {
				const meta: string[] = [];
				if (typeof details?.site === "string") meta.push(`site: ${details.site}`);
				if (typeof details?.filetype === "string") meta.push(`filetype: ${details.filetype}`);
				if (typeof details?.language === "string") meta.push(`language: ${details.language}`);
				if (typeof details?.freshness === "string") meta.push(`freshness: ${details.freshness}`);
				if (typeof details?.country === "string") meta.push(`country: ${details.country}`);
				if (lineCount > 0) meta.push(`output lines: ${lineCount}`);
				if (meta.length > 0) {
					text += `\n${theme.fg("dim", meta.join("\n"))}`;
				}
			}
			return new Text(text, 0, 0);
		},
		async execute(
			_toolCallId: string,
			params: WebSearchParams,
			signal?: AbortSignal,
			onUpdate?: ToolUpdateCallback,
		): Promise<ToolExecutionResult> {
			const { query, site, filetype, language, effectiveQuery } = buildSearchQuery(params);
			const count = normalizeCount(params.count);
			const country = normalizeCountry(params.country);
			const freshness = params.freshness?.trim() || undefined;
			const includeContent = params.includeContent ?? false;

			onUpdate?.({
				content: [{ type: "text", text: `Searching the web for: ${effectiveQuery}` }],
				details: {
					phase: "searching",
					site,
					filetype,
					language,
				},
			});

			const args = [effectiveQuery, "-n", String(count), "--country", country];
			if (includeContent) args.push("--content");
			if (freshness) args.push("--freshness", freshness);

			const { stdout, stderr } = await scriptRunner(scriptPath, args, signal);
			const rawOutput = stdout.trim() || stderr.trim() || "No results found.";
			const resultCount = countSearchResults(rawOutput);
			const outputLineCount = countOutputLines(rawOutput);
			const { text, details } = await truncateOutput(rawOutput, "Search output");

			return {
				content: [{ type: "text", text }],
				details: {
					query,
					effectiveQuery,
					site,
					filetype,
					language,
					count,
					includeContent,
					country,
					freshness,
					resultCount,
					outputLineCount,
					...details,
				},
			};
		},
	};
}

export function createFetchWebContentTool(options: CreateToolOptions = {}) {
	const scriptRunner = options.runScript ?? runScript;
	const truncateOutput = options.truncateOutput ?? truncateForToolOutput;
	const scriptPath = options.contentScriptPath ?? contentScriptPath;

	return {
		name: FETCH_WEB_CONTENT_TOOL_NAME,
		label: "Fetch Web Content",
		description: `Fetch readable markdown-like content from a specific URL. Good for reading documentation pages and articles. Output is truncated to ${DEFAULT_MAX_LINES} lines or ${formatSize(DEFAULT_MAX_BYTES)}.`,
		promptSnippet:
			"Fetch readable content from a specific URL when the user provides one or when a search result needs deeper reading.",
		promptGuidelines: [
			"Use fetch_web_content for a specific URL or when a search snippet is not enough.",
		],
		parameters: fetchWebContentParameters,
		renderCall(args, theme) {
			let text = theme.fg("toolTitle", theme.bold("fetch_web_content "));
			text += theme.fg("accent", truncateDisplayText(args.url, 84));
			return new Text(text, 0, 0);
		},
		renderResult(result, { expanded, isPartial }, theme, context) {
			if (isPartial) {
				return new Text(theme.fg("warning", "Fetching..."), 0, 0);
			}

			const details = result.details as Record<string, unknown> | undefined;
			if (context.isError) {
				const content = result.content[0];
				const errorText = content?.type === "text" ? truncateDisplayText(content.text, 120) : "Fetch failed";
				return new Text(theme.fg("error", errorText), 0, 0);
			}

			const lineCount = typeof details?.outputLineCount === "number" ? details.outputLineCount : 0;
			const characterCount = typeof details?.characterCount === "number" ? details.characterCount : 0;
			let text = theme.fg("success", "Content fetched");
			if (lineCount > 0 || characterCount > 0) {
				text += theme.fg("muted", ` (${lineCount} lines, ${characterCount} chars)`);
			}
			if (details?.truncation && typeof details.truncation === "object" && details.truncation !== null) {
				text += theme.fg("warning", " [truncated]");
			}
			if (expanded && typeof details?.url === "string") {
				text += `\n${theme.fg("dim", details.url)}`;
			}
			return new Text(text, 0, 0);
		},
		async execute(
			_toolCallId: string,
			params: FetchWebContentParams,
			signal?: AbortSignal,
			onUpdate?: ToolUpdateCallback,
		): Promise<ToolExecutionResult> {
			const url = params.url.trim();
			if (!url) {
				throw new Error("URL must not be empty.");
			}

			onUpdate?.({
				content: [{ type: "text", text: `Fetching page content: ${url}` }],
				details: { phase: "fetching" },
			});

			const { stdout, stderr } = await scriptRunner(scriptPath, [url], signal);
			const rawOutput = stdout.trim() || stderr.trim();
			const outputLineCount = countOutputLines(rawOutput);
			const characterCount = rawOutput.length;
			const { text, details } = await truncateOutput(rawOutput, "Page content");

			return {
				content: [{ type: "text", text }],
				details: {
					url,
					outputLineCount,
					characterCount,
					...details,
				},
			};
		},
	};
}

export default function (pi: ExtensionAPI) {
	pi.registerTool(createWebSearchTool());
	pi.registerTool(createFetchWebContentTool());
}
