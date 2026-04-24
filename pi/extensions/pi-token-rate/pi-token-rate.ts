import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export const TOKEN_RATE_WIDGET_KEY = "token-rate";

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

function setTokenRateWidget(
	ctx: {
		ui: {
			setWidget: (
				key: string,
				widget?: string[],
				options?: { placement?: "belowEditor" | "aboveEditor" },
			) => void;
			theme: { fg: (token: string, text: string) => string };
		};
	},
	measurement?: TokenRateMeasurement,
) {
	if (!measurement) {
		ctx.ui.setWidget(TOKEN_RATE_WIDGET_KEY, undefined);
		return;
	}

	ctx.ui.setWidget(
		TOKEN_RATE_WIDGET_KEY,
		[ctx.ui.theme.fg("dim", buildTokenRateLabel(measurement))],
		{ placement: "belowEditor" },
	);
}

export default function registerTokenRate(pi: ExtensionAPI) {
	let activeAssistant: ActiveAssistantState | undefined;

	function clearState(ctx?: {
		ui?: {
			setWidget?: (
				key: string,
				widget?: string[],
				options?: { placement?: "belowEditor" | "aboveEditor" },
			) => void;
		};
	}) {
		activeAssistant = undefined;
		ctx?.ui?.setWidget?.(TOKEN_RATE_WIDGET_KEY, undefined);
	}

	pi.on("session_start", async (_event, ctx) => {
		clearState(ctx);
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		clearState(ctx);
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

	pi.on("message_end", async (event, ctx) => {
		if (!isAssistantMessage(event.message)) {
			return;
		}

		const currentAssistant = activeAssistant;
		activeAssistant = undefined;

		if (!currentAssistant) {
			setTokenRateWidget(ctx);
			return;
		}

		const finishedAt = Date.now();
		const outputTokens = readOutputTokens(event.message);
		const measurement =
			outputTokens === undefined
				? undefined
				: calculateTokenRate(
						outputTokens,
						currentAssistant.startedAt,
						finishedAt,
						currentAssistant.firstTokenAt,
				  );

		setTokenRateWidget(ctx, measurement);
	});
}
