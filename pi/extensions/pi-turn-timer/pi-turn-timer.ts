import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";

export const TURN_TIMER_MESSAGE_TYPE = "turn-timer";

export type TurnTimerStatus = "completed" | "cancelled";

export interface TurnTimerDetails {
	elapsedMs: number;
	startedAt: number;
	finishedAt: number;
	status: TurnTimerStatus;
}

interface CustomMessageLike {
	role?: unknown;
	customType?: unknown;
	content?: unknown;
	details?: unknown;
}

interface TextContentLike {
	type?: unknown;
	text?: unknown;
}

interface AssistantMessageLike {
	role?: unknown;
	stopReason?: unknown;
}

export function formatElapsed(ms: number) {
	if (ms < 1_000) {
		return `${ms}ms`;
	}

	const totalSeconds = ms / 1_000;
	if (totalSeconds < 60) {
		return totalSeconds < 10 ? `${totalSeconds.toFixed(1)}s` : `${Math.round(totalSeconds)}s`;
	}

	const totalWholeSeconds = Math.round(totalSeconds);
	const hours = Math.floor(totalWholeSeconds / 3_600);
	const minutes = Math.floor((totalWholeSeconds % 3_600) / 60);
	const seconds = totalWholeSeconds % 60;
	const parts: string[] = [];

	if (hours > 0) {
		parts.push(`${hours}h`);
	}
	if (minutes > 0 || hours > 0) {
		parts.push(`${minutes}m`);
	}
	parts.push(`${seconds}s`);

	return parts.join(" ");
}

export function buildTurnTimerContent(
	elapsedMs: number,
	status: TurnTimerStatus = "completed",
) {
	if (status === "cancelled") {
		return `Cancelled after ${formatElapsed(elapsedMs)}.`;
	}

	return `Completed in ${formatElapsed(elapsedMs)}.`;
}

export function createTurnTimerDetails(
	startedAt: number,
	finishedAt: number,
	status: TurnTimerStatus = "completed",
): TurnTimerDetails {
	return {
		elapsedMs: finishedAt - startedAt,
		startedAt,
		finishedAt,
		status,
	};
}

export function isTurnTimerMessage(message: unknown): message is CustomMessageLike {
	if (typeof message !== "object" || message === null) {
		return false;
	}

	return (
		Reflect.get(message, "role") === "custom" &&
		Reflect.get(message, "customType") === TURN_TIMER_MESSAGE_TYPE
	);
}

function getMessageText(content: unknown) {
	if (typeof content === "string") {
		return content;
	}

	if (!Array.isArray(content)) {
		return "";
	}

	return content
		.filter((item): item is TextContentLike => typeof item === "object" && item !== null)
		.filter((item) => item.type === "text" && typeof item.text === "string")
		.map((item) => item.text)
		.join("\n");
}

function readDetails(details: unknown): TurnTimerDetails | undefined {
	if (typeof details !== "object" || details === null) {
		return undefined;
	}

	const elapsedMs = Reflect.get(details, "elapsedMs");
	const startedAt = Reflect.get(details, "startedAt");
	const finishedAt = Reflect.get(details, "finishedAt");
	const status = Reflect.get(details, "status");
	if (
		typeof elapsedMs !== "number" ||
		typeof startedAt !== "number" ||
		typeof finishedAt !== "number"
	) {
		return undefined;
	}

	return {
		elapsedMs,
		startedAt,
		finishedAt,
		status: status === "cancelled" ? "cancelled" : "completed",
	};
}

function readTurnTimerStatus(messages: unknown, signal?: AbortSignal): TurnTimerStatus {
	if (signal?.aborted) {
		return "cancelled";
	}

	if (!Array.isArray(messages)) {
		return "completed";
	}

	for (let index = messages.length - 1; index >= 0; index--) {
		const message = messages[index];
		if (typeof message !== "object" || message === null) {
			continue;
		}

		const assistantMessage = message as AssistantMessageLike;
		if (assistantMessage.role !== "assistant") {
			continue;
		}

		return assistantMessage.stopReason === "aborted" ? "cancelled" : "completed";
	}

	return "completed";
}

export default function registerTurnTimer(pi: ExtensionAPI) {
	let startedAt: number | undefined;
	let pendingMessageTimer: ReturnType<typeof setTimeout> | undefined;

	function clearPendingMessageTimer() {
		if (pendingMessageTimer !== undefined) {
			clearTimeout(pendingMessageTimer);
			pendingMessageTimer = undefined;
		}
	}

	function scheduleTimingMessage(details: TurnTimerDetails) {
		clearPendingMessageTimer();
		pendingMessageTimer = setTimeout(() => {
			pendingMessageTimer = undefined;
			pi.sendMessage(
				{
					customType: TURN_TIMER_MESSAGE_TYPE,
					content: buildTurnTimerContent(details.elapsedMs, details.status),
					display: true,
					details,
				},
				{ triggerTurn: false },
			);
		}, 0);
	}

	pi.registerMessageRenderer(TURN_TIMER_MESSAGE_TYPE, (message, { expanded }, theme) => {
		const details = readDetails((message as CustomMessageLike).details);
		const elapsedMs = details?.elapsedMs ?? 0;
		const content =
			getMessageText((message as CustomMessageLike).content) ||
			buildTurnTimerContent(elapsedMs, details?.status);
		const icon = theme.fg("muted", "⏱");
		let text = `${icon} ${theme.fg("dim", theme.italic(content))}`;

		if (expanded && details) {
			text += `\n${theme.fg("dim", theme.italic(`  ${details.elapsedMs} ms`))}`;
		}

		return new Text(text, 0, 0);
	});

	pi.on("context", async (event) => {
		return {
			messages: event.messages.filter((message) => !isTurnTimerMessage(message)),
		};
	});

	pi.on("session_start", async () => {
		startedAt = undefined;
		clearPendingMessageTimer();
	});

	pi.on("session_shutdown", async () => {
		startedAt = undefined;
		clearPendingMessageTimer();
	});

	pi.on("agent_start", async () => {
		startedAt = Date.now();
	});

	pi.on("agent_end", async (event, ctx) => {
		if (startedAt === undefined) {
			return;
		}

		const finishedAt = Date.now();
		const status = readTurnTimerStatus(event.messages, ctx.signal);
		const details = createTurnTimerDetails(startedAt, finishedAt, status);
		startedAt = undefined;
		scheduleTimingMessage(details);
	});
}
