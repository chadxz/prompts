import { afterEach, describe, expect, it, vi } from "vitest";
import registerTurnTimer, {
	buildTurnTimerContent,
	createTurnTimerDetails,
	formatElapsed,
	TURN_TIMER_MESSAGE_TYPE,
} from "./pi-turn-timer.ts";

function createMockPi() {
	return {
		on: vi.fn(),
		registerMessageRenderer: vi.fn(),
		sendMessage: vi.fn(),
	};
}

function getEventHandler(mockPi: ReturnType<typeof createMockPi>, eventName: string) {
	const entry = mockPi.on.mock.calls.find(([event]) => event === eventName);
	return entry?.[1] as ((...args: unknown[]) => Promise<unknown>) | undefined;
}

afterEach(() => {
	vi.useRealTimers();
});

describe("formatElapsed", () => {
	it("formats millisecond, second, minute, and hour ranges", () => {
		expect(formatElapsed(750)).toBe("750ms");
		expect(formatElapsed(3_200)).toBe("3.2s");
		expect(formatElapsed(15_000)).toBe("15s");
		expect(formatElapsed(65_000)).toBe("1m 5s");
		expect(formatElapsed(3_665_000)).toBe("1h 1m 5s");
	});
});

describe("turn timer helpers", () => {
	it("builds message content and details", () => {
		expect(buildTurnTimerContent(3_200)).toBe("Completed in 3.2s.");
		expect(buildTurnTimerContent(3_200, "cancelled")).toBe("Cancelled after 3.2s.");
		expect(createTurnTimerDetails(100, 1_600)).toEqual({
			elapsedMs: 1_500,
			startedAt: 100,
			finishedAt: 1_600,
			status: "completed",
		});
	});
});

describe("pi-turn-timer runtime", () => {
	it("registers a renderer and event handlers", () => {
		const mockPi = createMockPi();

		registerTurnTimer(mockPi as never);

		expect(mockPi.registerMessageRenderer).toHaveBeenCalledWith(
			TURN_TIMER_MESSAGE_TYPE,
			expect.any(Function),
		);
		expect(mockPi.on.mock.calls.map(([event]) => event)).toEqual(
			expect.arrayContaining([
				"context",
				"session_start",
				"session_shutdown",
				"agent_start",
				"agent_end",
			]),
		);
	});

	it("filters timing messages out of future model context", async () => {
		const mockPi = createMockPi();
		registerTurnTimer(mockPi as never);

		const contextHandler = getEventHandler(mockPi, "context");
		const timingMessage = {
			role: "custom",
			customType: TURN_TIMER_MESSAGE_TYPE,
			content: "Completed in 3.2s.",
		};
		const keepMessage = {
			role: "custom",
			customType: "other-extension",
			content: "Keep me",
		};
		const userMessage = { role: "user", content: "Hello" };

		await expect(
			contextHandler?.({ messages: [timingMessage, keepMessage, userMessage] } as never, {} as never),
		).resolves.toEqual({ messages: [keepMessage, userMessage] });
	});

	it("sends a non-triggering custom message when an agent run completes", async () => {
		vi.useFakeTimers();
		const mockPi = createMockPi();
		registerTurnTimer(mockPi as never);

		const agentStart = getEventHandler(mockPi, "agent_start");
		const agentEnd = getEventHandler(mockPi, "agent_end");
		const nowSpy = vi.spyOn(Date, "now");

		nowSpy.mockReturnValueOnce(1_000);
		await agentStart?.({ type: "agent_start" } as never, {} as never);

		nowSpy.mockReturnValueOnce(4_200);
		await agentEnd?.({ type: "agent_end", messages: [] } as never, {} as never);

		expect(mockPi.sendMessage).not.toHaveBeenCalled();

		await vi.runAllTimersAsync();

		expect(mockPi.sendMessage).toHaveBeenCalledWith(
			{
				customType: TURN_TIMER_MESSAGE_TYPE,
				content: "Completed in 3.2s.",
				display: true,
				details: {
					elapsedMs: 3_200,
					startedAt: 1_000,
					finishedAt: 4_200,
					status: "completed",
				},
			},
			{ triggerTurn: false },
		);
	});

	it("sends a cancelled message when the agent run is aborted", async () => {
		vi.useFakeTimers();
		const mockPi = createMockPi();
		registerTurnTimer(mockPi as never);

		const agentStart = getEventHandler(mockPi, "agent_start");
		const agentEnd = getEventHandler(mockPi, "agent_end");
		const nowSpy = vi.spyOn(Date, "now");
		const abortController = new AbortController();

		nowSpy.mockReturnValueOnce(1_000);
		await agentStart?.({ type: "agent_start" } as never, {} as never);

		abortController.abort();
		nowSpy.mockReturnValueOnce(2_500);
		await agentEnd?.(
			{ type: "agent_end", messages: [] } as never,
			{ signal: abortController.signal } as never,
		);
		await vi.runAllTimersAsync();

		expect(mockPi.sendMessage).toHaveBeenCalledWith(
			{
				customType: TURN_TIMER_MESSAGE_TYPE,
				content: "Cancelled after 1.5s.",
				display: true,
				details: {
					elapsedMs: 1_500,
					startedAt: 1_000,
					finishedAt: 2_500,
					status: "cancelled",
				},
			},
			{ triggerTurn: false },
		);
	});

	it("does not emit a message if no agent start was recorded", async () => {
		vi.useFakeTimers();
		const mockPi = createMockPi();
		registerTurnTimer(mockPi as never);

		const agentEnd = getEventHandler(mockPi, "agent_end");
		await agentEnd?.({ type: "agent_end", messages: [] } as never, {} as never);
		await vi.runAllTimersAsync();

		expect(mockPi.sendMessage).not.toHaveBeenCalled();
	});

	it("clears any pending timing message when the session restarts or shuts down", async () => {
		vi.useFakeTimers();
		const mockPi = createMockPi();
		registerTurnTimer(mockPi as never);

		const agentStart = getEventHandler(mockPi, "agent_start");
		const agentEnd = getEventHandler(mockPi, "agent_end");
		const sessionShutdown = getEventHandler(mockPi, "session_shutdown");
		const nowSpy = vi.spyOn(Date, "now");

		nowSpy.mockReturnValueOnce(1_000);
		await agentStart?.({ type: "agent_start" } as never, {} as never);
		nowSpy.mockReturnValueOnce(4_200);
		await agentEnd?.({ type: "agent_end", messages: [] } as never, {} as never);
		await sessionShutdown?.({ type: "session_shutdown" } as never, {} as never);
		await vi.runAllTimersAsync();

		expect(mockPi.sendMessage).not.toHaveBeenCalled();
	});

	it("renders a compact timing message with expandable details", () => {
		const mockPi = createMockPi();
		registerTurnTimer(mockPi as never);

		const renderer = mockPi.registerMessageRenderer.mock.calls[0]?.[1] as
			| ((...args: unknown[]) => { render: (width: number) => string[] })
			| undefined;
		const theme = {
			fg: (_token: string, text: string) => text,
			bg: (_token: string, text: string) => text,
			bold: (text: string) => text,
			italic: (text: string) => `<i>${text}</i>`,
		} as never;

		const compactComponent = renderer?.(
			{
				customType: TURN_TIMER_MESSAGE_TYPE,
				content: "Completed in 3.2s.",
				details: {
					elapsedMs: 3_200,
					startedAt: 1_000,
					finishedAt: 4_200,
					status: "completed",
				},
			},
			{ expanded: false },
			theme,
		);
		const expandedComponent = renderer?.(
			{
				customType: TURN_TIMER_MESSAGE_TYPE,
				content: "Completed in 3.2s.",
				details: {
					elapsedMs: 3_200,
					startedAt: 1_000,
					finishedAt: 4_200,
					status: "completed",
				},
			},
			{ expanded: true },
			theme,
		);

		expect(compactComponent?.render(120).join("\n")).toContain("<i>Completed in 3.2s.</i>");
		expect(expandedComponent?.render(120).join("\n")).toContain("<i>  3200 ms</i>");
	});
});
