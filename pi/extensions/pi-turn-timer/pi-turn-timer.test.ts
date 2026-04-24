import { afterEach, describe, expect, it, vi } from "vitest";
import registerTurnTimer, {
	buildTurnTimerContent,
	createTimedBashOperations,
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

function createMockBashOperations() {
	return {
		exec: vi.fn(),
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
	it("builds message content and details for agent and shell timing", () => {
		expect(buildTurnTimerContent(3_200)).toBe("Completed in 3.2s.");
		expect(buildTurnTimerContent(3_200, "cancelled")).toBe("Cancelled after 3.2s.");
		expect(createTurnTimerDetails(100, 1_600)).toEqual({
			elapsedMs: 1_500,
			startedAt: 100,
			finishedAt: 1_600,
			status: "completed",
			kind: "agent",
		});
		expect(
			createTurnTimerDetails(100, 1_600, "completed", "shell", {
				command: "git status",
				exitCode: 0,
			}),
		).toEqual({
			elapsedMs: 1_500,
			startedAt: 100,
			finishedAt: 1_600,
			status: "completed",
			kind: "shell",
			command: "git status",
			exitCode: 0,
		});
	});

	it("wraps bash operations and reports shell timing", async () => {
		vi.useFakeTimers();
		const onTiming = vi.fn();
		const baseOperations = createMockBashOperations();
		baseOperations.exec.mockResolvedValue({ exitCode: 0 });
		const nowSpy = vi.spyOn(Date, "now");

		nowSpy.mockReturnValueOnce(1_000);
		nowSpy.mockReturnValueOnce(1_450);
		const operations = createTimedBashOperations(baseOperations as never, {
			command: "git status",
			onTiming,
		});
		const result = await operations.exec("git status", "/tmp", {
			onData: vi.fn(),
		});

		expect(result).toEqual({ exitCode: 0 });
		expect(onTiming).toHaveBeenCalledWith({
			elapsedMs: 450,
			startedAt: 1_000,
			finishedAt: 1_450,
			status: "completed",
			kind: "shell",
			command: "git status",
			exitCode: 0,
		});
	});

	it("marks aborted shell commands as cancelled", async () => {
		const onTiming = vi.fn();
		const baseOperations = createMockBashOperations();
		baseOperations.exec.mockRejectedValue(new Error("aborted"));
		const nowSpy = vi.spyOn(Date, "now");

		nowSpy.mockReturnValueOnce(2_000);
		nowSpy.mockReturnValueOnce(2_900);
		const operations = createTimedBashOperations(baseOperations as never, {
			command: "sleep 30",
			onTiming,
		});

		await expect(
			operations.exec("sleep 30", "/tmp", {
				onData: vi.fn(),
				signal: new AbortController().signal,
			}),
		).rejects.toThrow("aborted");
		expect(onTiming).toHaveBeenCalledWith({
			elapsedMs: 900,
			startedAt: 2_000,
			finishedAt: 2_900,
			status: "cancelled",
			kind: "shell",
			command: "sleep 30",
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
				"user_bash",
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
					kind: "agent",
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
					kind: "agent",
				},
			},
			{ triggerTurn: false },
		);
	});

	it("sends a timing message when a user shell command completes", async () => {
		vi.useFakeTimers();
		const mockPi = createMockPi();
		const baseOperations = createMockBashOperations();
		baseOperations.exec.mockResolvedValue({ exitCode: 0 });
		registerTurnTimer(mockPi as never, {
			createUserBashOperations: () => baseOperations as never,
		});

		const userBash = getEventHandler(mockPi, "user_bash");
		const nowSpy = vi.spyOn(Date, "now");

		const bashResponse = (await userBash?.(
			{ type: "user_bash", command: "git status" } as never,
			{} as never,
		)) as { operations: { exec: (...args: unknown[]) => Promise<unknown> } };

		nowSpy.mockReturnValueOnce(10_000);
		nowSpy.mockReturnValueOnce(10_450);
		await bashResponse.operations.exec("git status", "/tmp", {
			onData: vi.fn(),
		});

		expect(mockPi.sendMessage).not.toHaveBeenCalled();
		await vi.runAllTimersAsync();

		expect(mockPi.sendMessage).toHaveBeenCalledWith(
			{
				customType: TURN_TIMER_MESSAGE_TYPE,
				content: "Completed in 450ms.",
				display: true,
				details: {
					elapsedMs: 450,
					startedAt: 10_000,
					finishedAt: 10_450,
					status: "completed",
					kind: "shell",
					command: "git status",
					exitCode: 0,
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
					kind: "agent",
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
					kind: "shell",
					command: "git status",
					exitCode: 0,
				},
			},
			{ expanded: true },
			theme,
		);

		expect(compactComponent?.render(120).join("\n")).toContain(
			"<i>Completed in 3.2s.</i>",
		);
		const expandedRender = expandedComponent?.render(120).join("\n") ?? "";
		expect(expandedRender).toContain("<i>Completed in 3.2s.</i>");
		expect(expandedRender).toContain("$ git status");
		expect(expandedRender).toContain("exit 0");
		expect(expandedRender).toContain("3200 ms");
	});
});
