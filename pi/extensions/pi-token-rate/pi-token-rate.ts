import type {
	ExtensionAPI,
	ExtensionContext,
	ReadonlyFooterDataProvider,
	Theme,
} from "@mariozechner/pi-coding-agent";
import type { Component, TUI } from "@mariozechner/pi-tui";
import { truncateToWidth, visibleWidth } from "@mariozechner/pi-tui";

export interface ActiveAssistantState {
	startedAt: number;
	firstTokenAt?: number;
}

export interface TokenRateMeasurement {
	outputTokens: number;
	startedAt: number;
	firstTokenAt?: number;
	finishedAt: number;
	elapsedMs: number;
	tokensPerSecond: number;
}

interface AssistantMessageLike {
	role?: unknown;
	usage?: unknown;
}

interface StatsPart {
	plain: string;
	style?: (text: string) => string;
}

export function isAssistantMessage(message: unknown): message is AssistantMessageLike {
	if (typeof message !== "object" || message === null) {
		return false;
	}

	return Reflect.get(message, "role") === "assistant";
}

export function readOutputTokens(message: unknown) {
	if (!isAssistantMessage(message)) {
		return undefined;
	}

	const usage = Reflect.get(message, "usage");
	if (typeof usage !== "object" || usage === null) {
		return undefined;
	}

	const output = Reflect.get(usage, "output");
	return typeof output === "number" && Number.isFinite(output) ? output : undefined;
}

export function calculateTokenRate(
	outputTokens: number,
	startedAt: number,
	finishedAt: number,
	firstTokenAt?: number,
): TokenRateMeasurement | undefined {
	if (!Number.isFinite(outputTokens) || outputTokens <= 0) {
		return undefined;
	}

	const effectiveStart =
		typeof firstTokenAt === "number" && firstTokenAt >= startedAt && firstTokenAt < finishedAt
			? firstTokenAt
			: startedAt;
	const elapsedMs = Math.max(finishedAt - effectiveStart, 1);

	return {
		outputTokens,
		startedAt,
		firstTokenAt,
		finishedAt,
		elapsedMs,
		tokensPerSecond: outputTokens / (elapsedMs / 1_000),
	};
}

export function formatTokenRate(tokensPerSecond: number) {
	if (tokensPerSecond >= 100) {
		return tokensPerSecond.toFixed(0);
	}

	if (tokensPerSecond >= 10) {
		return tokensPerSecond.toFixed(1);
	}

	return tokensPerSecond.toFixed(2);
}

export function buildTokenRateLabel(measurement: TokenRateMeasurement) {
	return `${formatTokenRate(measurement.tokensPerSecond)} tok/s`;
}

function sanitizeStatusText(text: string) {
	return text
		.replace(/[\r\n\t]/g, " ")
		.replace(/ +/g, " ")
		.trim();
}

function formatTokens(count: number) {
	if (count < 1000) {
		return count.toString();
	}
	if (count < 10000) {
		return `${(count / 1000).toFixed(1)}k`;
	}
	if (count < 1000000) {
		return `${Math.round(count / 1000)}k`;
	}
	if (count < 10000000) {
		return `${(count / 1000000).toFixed(1)}M`;
	}
	return `${Math.round(count / 1000000)}M`;
}

function readUsageNumber(usage: unknown, key: string) {
	if (typeof usage !== "object" || usage === null) {
		return 0;
	}

	const value = Reflect.get(usage, key);
	return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function readUsageCostTotal(usage: unknown) {
	if (typeof usage !== "object" || usage === null) {
		return 0;
	}

	const cost = Reflect.get(usage, "cost");
	if (typeof cost !== "object" || cost === null) {
		return 0;
	}

	const total = Reflect.get(cost, "total");
	return typeof total === "number" && Number.isFinite(total) ? total : 0;
}

function buildPwdLine(ctx: ExtensionContext, footerData: ReadonlyFooterDataProvider) {
	let pwd = ctx.sessionManager.getCwd();
	const home = process.env.HOME || process.env.USERPROFILE;

	if (home && pwd.startsWith(home)) {
		pwd = `~${pwd.slice(home.length)}`;
	}

	const branch = footerData.getGitBranch();
	if (branch) {
		pwd = `${pwd} (${branch})`;
	}

	const sessionName = ctx.sessionManager.getSessionName();
	if (sessionName) {
		pwd = `${pwd} • ${sessionName}`;
	}

	return pwd;
}

function collectStatsParts(
	ctx: ExtensionContext,
	theme: Theme,
	measurement: TokenRateMeasurement | undefined,
) {
	let totalInput = 0;
	let totalOutput = 0;
	let totalCacheRead = 0;
	let totalCacheWrite = 0;
	let totalCost = 0;

	for (const entry of ctx.sessionManager.getEntries()) {
		if (entry.type !== "message" || !isAssistantMessage(entry.message)) {
			continue;
		}

		const usage = entry.message.usage;
		totalInput += readUsageNumber(usage, "input");
		totalOutput += readUsageNumber(usage, "output");
		totalCacheRead += readUsageNumber(usage, "cacheRead");
		totalCacheWrite += readUsageNumber(usage, "cacheWrite");
		totalCost += readUsageCostTotal(usage);
	}

	const statsParts: StatsPart[] = [];
	if (totalInput) {
		statsParts.push({ plain: `↑${formatTokens(totalInput)}` });
	}
	if (totalOutput) {
		statsParts.push({ plain: `↓${formatTokens(totalOutput)}` });
	}
	if (totalCacheRead) {
		statsParts.push({ plain: `R${formatTokens(totalCacheRead)}` });
	}
	if (totalCacheWrite) {
		statsParts.push({ plain: `W${formatTokens(totalCacheWrite)}` });
	}

	const usingSubscription = ctx.model ? ctx.modelRegistry.isUsingOAuth(ctx.model) : false;
	if (totalCost || usingSubscription) {
		statsParts.push({ plain: `$${totalCost.toFixed(3)}${usingSubscription ? " (sub)" : ""}` });
	}

	const contextUsage = ctx.getContextUsage();
	const contextWindow = contextUsage?.contextWindow ?? ctx.model?.contextWindow ?? 0;
	const contextPercentValue = contextUsage?.percent ?? 0;
	const contextPercent = contextUsage?.percent === null ? "?" : contextPercentValue.toFixed(1);
	const contextPercentDisplay =
		contextPercent === "?"
			? `?/${formatTokens(contextWindow)} (auto)`
			: `${contextPercent}%/${formatTokens(contextWindow)} (auto)`;

	if (contextPercentValue > 90) {
		statsParts.push({ plain: contextPercentDisplay, style: (text) => theme.fg("error", text) });
	} else if (contextPercentValue > 70) {
		statsParts.push({ plain: contextPercentDisplay, style: (text) => theme.fg("warning", text) });
	} else {
		statsParts.push({ plain: contextPercentDisplay });
	}

	if (measurement) {
		statsParts.push({ plain: buildTokenRateLabel(measurement) });
	}

	return statsParts;
}

function renderStatsLeft(theme: Theme, parts: StatsPart[]) {
	return parts
		.map((part) => (part.style ? part.style(part.plain) : theme.fg("dim", part.plain)))
		.join(theme.fg("dim", " "));
}

function buildRightSide(
	ctx: ExtensionContext,
	footerData: ReadonlyFooterDataProvider,
	getThinkingLevel: () => string,
	width: number,
	statsLeftWidth: number,
) {
	const modelName = ctx.model?.id || "no-model";
	let rightSideWithoutProvider = modelName;

	if (ctx.model?.reasoning) {
		const thinkingLevel = getThinkingLevel();
		rightSideWithoutProvider =
			thinkingLevel === "off" ? `${modelName} • thinking off` : `${modelName} • ${thinkingLevel}`;
	}

	let rightSide = rightSideWithoutProvider;
	if (footerData.getAvailableProviderCount() > 1 && ctx.model) {
		const rightSideWithProvider = `(${ctx.model.provider}) ${rightSideWithoutProvider}`;
		if (statsLeftWidth + 2 + visibleWidth(rightSideWithProvider) <= width) {
			rightSide = rightSideWithProvider;
		}
	}

	return rightSide;
}

function renderStatsLine(
	ctx: ExtensionContext,
	theme: Theme,
	footerData: ReadonlyFooterDataProvider,
	measurement: TokenRateMeasurement | undefined,
	getThinkingLevel: () => string,
	width: number,
) {
	const statsParts = collectStatsParts(ctx, theme, measurement);
	const statsLeftPlain = statsParts.map((part) => part.plain).join(" ");
	const statsLeftWidth = visibleWidth(statsLeftPlain);

	if (statsLeftWidth > width) {
		return theme.fg("dim", truncateToWidth(statsLeftPlain, width, "..."));
	}

	const rightSide = buildRightSide(ctx, footerData, getThinkingLevel, width, statsLeftWidth);
	const rightSideWidth = visibleWidth(rightSide);
	const styledStatsLeft = renderStatsLeft(theme, statsParts);

	if (statsLeftWidth + 2 + rightSideWidth <= width) {
		const padding = " ".repeat(width - statsLeftWidth - rightSideWidth);
		return styledStatsLeft + theme.fg("dim", `${padding}${rightSide}`);
	}

	const availableForRight = width - statsLeftWidth - 2;
	if (availableForRight <= 0) {
		return styledStatsLeft;
	}

	const truncatedRight = truncateToWidth(rightSide, availableForRight, "");
	const padding = " ".repeat(Math.max(0, width - statsLeftWidth - visibleWidth(truncatedRight)));

	return styledStatsLeft + theme.fg("dim", `${padding}${truncatedRight}`);
}

export function renderTokenRateFooter(
	ctx: ExtensionContext,
	theme: Theme,
	footerData: ReadonlyFooterDataProvider,
	measurement: TokenRateMeasurement | undefined,
	getThinkingLevel: () => string,
	width: number,
) {
	const pwdLine = truncateToWidth(
		theme.fg("dim", buildPwdLine(ctx, footerData)),
		width,
		theme.fg("dim", "..."),
	);
	const statsLine = renderStatsLine(ctx, theme, footerData, measurement, getThinkingLevel, width);
	const lines = [pwdLine, statsLine];

	const extensionStatuses = footerData.getExtensionStatuses();
	if (extensionStatuses.size > 0) {
		const statusLine = Array.from(extensionStatuses.entries())
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([, text]) => sanitizeStatusText(text))
			.join(" ");
		lines.push(truncateToWidth(statusLine, width, theme.fg("dim", "...")));
	}

	return lines;
}

function setTokenRateFooter(
	ctx: ExtensionContext,
	getThinkingLevel: () => string,
	getMeasurement: () => TokenRateMeasurement | undefined,
	onRenderReady: (requestRender: () => void) => void,
) {
	ctx.ui.setFooter((tui: TUI, theme: Theme, footerData: ReadonlyFooterDataProvider) => {
		const unsubscribe = footerData.onBranchChange(() => tui.requestRender());
		onRenderReady(() => tui.requestRender());

		return {
			dispose: unsubscribe,
			invalidate() {},
			render(width: number) {
				return renderTokenRateFooter(ctx, theme, footerData, getMeasurement(), getThinkingLevel, width);
			},
		} satisfies Component & { dispose(): void };
	});
}

export default function registerTokenRate(pi: ExtensionAPI) {
	let activeAssistant: ActiveAssistantState | undefined;
	let lastMeasurement: TokenRateMeasurement | undefined;
	let requestFooterRender: (() => void) | undefined;
	const getThinkingLevel = () => pi.getThinkingLevel();

	function renderFooter() {
		requestFooterRender?.();
	}

	function resetState() {
		activeAssistant = undefined;
		lastMeasurement = undefined;
		requestFooterRender = undefined;
	}

	pi.on("session_start", async (_event, ctx) => {
		resetState();
		setTokenRateFooter(ctx, getThinkingLevel, () => lastMeasurement, (requestRender) => {
			requestFooterRender = requestRender;
		});
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		resetState();
		ctx.ui.setFooter(undefined);
	});

	pi.on("message_start", async (event) => {
		if (!isAssistantMessage(event.message)) {
			return;
		}

		activeAssistant = { startedAt: Date.now() };
	});

	pi.on("message_update", async (event) => {
		if (!isAssistantMessage(event.message) || activeAssistant === undefined) {
			return;
		}

		activeAssistant.firstTokenAt ??= Date.now();
	});

	pi.on("message_end", async (event) => {
		if (!isAssistantMessage(event.message)) {
			return;
		}

		const currentAssistant = activeAssistant;
		activeAssistant = undefined;

		if (!currentAssistant) {
			lastMeasurement = undefined;
			renderFooter();
			return;
		}

		const finishedAt = Date.now();
		const outputTokens = readOutputTokens(event.message);
		lastMeasurement =
			outputTokens === undefined
				? undefined
				: calculateTokenRate(
						outputTokens,
						currentAssistant.startedAt,
						finishedAt,
						currentAssistant.firstTokenAt,
				  );

		renderFooter();
	});

	pi.on("model_select", async () => {
		renderFooter();
	});
}
