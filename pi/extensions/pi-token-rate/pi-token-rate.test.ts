import { afterEach, describe, expect, it, vi } from "vitest";

import registerTokenRate, {
	buildTokenRateLabel,
	calculateTokenRate,
	formatTokenRate,
	readOutputTokens,
} from "./pi-token-rate.ts";

const theme = {
	fg: (_token: string, text: string) => text,
};

function createMockPi() {
	return {
		on: vi.fn(),
		getThinkingLevel: vi.fn(() => "high"),
	};
}

function createMockCtx() {
	return {
		ui: {
			setFooter: vi.fn(),
		},
		sessionManager: {
			getCwd: vi.fn(() => "/Users/chad/src/personal/prompts"),
			getEntries: vi.fn(() => []),
			getSessionName: vi.fn(() => undefined),
		},
		model: {
			id: "gpt-5.5",
			provider: "openai-codex",
			contextWindow: 262_000,
			reasoning: true,
		},
		modelRegistry: {
			isUsingOAuth: vi.fn(() => false),
		},
		getContextUsage: vi.fn(() => ({ contextWindow: 262_000, percent: 6.1 })),
	};
}

function mountFooter(ctx: ReturnType<typeof createMockCtx>) {
	const factory = ctx.ui.setFooter.mock.calls.at(-1)?.[0];
	expect(factory).toBeTypeOf("function");

	const requestRender = vi.fn();
	const unsubscribe = vi.fn();
	const footerData = {
		getGitBranch: vi.fn(() => "main"),
		getExtensionStatuses: vi.fn(() => new Map<string, string>()),
		getAvailableProviderCount: vi.fn(() => 1),
		onBranchChange: vi.fn(() => unsubscribe),
	};
	const footer = factory({ requestRender }, theme, footerData);

	return { footer, requestRender };
}

function getEventHandler(mockPi: ReturnType<typeof createMockPi>, eventName: string) {
	const entry = mockPi.on.mock.calls.find(([event]) => event === eventName);
	return entry?.[1] as ((...args: unknown[]) => Promise<unknown>) | undefined;
}

afterEach(() => {
	vi.useRealTimers();
	vi.restoreAllMocks();
});

describe("token rate helpers", () => {
	it("reads output token usage from assistant messages", () => {
		expect(readOutputTokens({ role: "assistant", usage: { output: 128 } })).toBe(128);
		expect(readOutputTokens({ role: "assistant", usage: { output: "128" } })).toBeUndefined();
		expect(readOutputTokens({ role: "user", usage: { output: 128 } })).toBeUndefined();
	});

	it("calculates tokens per second using first token time when available", () => {
		expect(calculateTokenRate(120, 1_000, 5_000, 2_000)).toEqual({
			outputTokens: 120,
			startedAt: 1_000,
			firstTokenAt: 2_000,
			finishedAt: 5_000,
			elapsedMs: 3_000,
			tokensPerSecond: 40,
		});
	});

	it("formats token rates for small and large values", () => {
		expect(formatTokenRate(4.567)).toBe("4.57");
		expect(formatTokenRate(42.345)).toBe("42.3");
		expect(formatTokenRate(142.345)).toBe("142");
		expect(buildTokenRateLabel({
			outputTokens: 120,
			startedAt: 1_000,
			firstTokenAt: 2_000,
			finishedAt: 5_000,
			elapsedMs: 3_000,
			tokensPerSecond: 40,
		})).toBe("40.0 tok/s");
	});
});

describe("pi-token-rate runtime", () => {
	it("registers lifecycle and message handlers", () => {
		const mockPi = createMockPi();

		registerTokenRate(mockPi as never);

		expect(mockPi.on.mock.calls.map(([event]) => event)).toEqual(
			expect.arrayContaining([
				"session_start",
				"session_shutdown",
				"message_start",
				"message_update",
				"message_end",
			]),
		);
	});

	it("installs a custom footer on session start", async () => {
		const mockPi = createMockPi();
		const ctx = createMockCtx();
		registerTokenRate(mockPi as never);

		const sessionStart = getEventHandler(mockPi, "session_start");
		await sessionStart?.({ type: "session_start" } as never, ctx as never);

		expect(ctx.ui.setFooter).toHaveBeenCalledWith(expect.any(Function));
	});

	it("publishes the measured output token rate after an assistant message finishes", async () => {
		const mockPi = createMockPi();
		const ctx = createMockCtx();
		registerTokenRate(mockPi as never);

		const sessionStart = getEventHandler(mockPi, "session_start");
		await sessionStart?.({ type: "session_start" } as never, ctx as never);
		const { footer, requestRender } = mountFooter(ctx);

		const messageStart = getEventHandler(mockPi, "message_start");
		const messageUpdate = getEventHandler(mockPi, "message_update");
		const messageEnd = getEventHandler(mockPi, "message_end");
		const nowSpy = vi.spyOn(Date, "now");

		nowSpy.mockReturnValueOnce(1_000);
		await messageStart?.({ message: { role: "assistant" } } as never, ctx as never);

		nowSpy.mockReturnValueOnce(1_800);
		await messageUpdate?.({ message: { role: "assistant" } } as never, ctx as never);

		nowSpy.mockReturnValueOnce(4_800);
		await messageEnd?.(
			{ message: { role: "assistant", usage: { output: 150 } } } as never,
			ctx as never,
		);

		expect(footer.render(80).join("\n")).toContain("50.0 tok/s");
		expect(requestRender).toHaveBeenCalledOnce();
	});

	it("renders the token rate alongside the built-in token stats", async () => {
		const mockPi = createMockPi();
		const ctx = createMockCtx();
		ctx.sessionManager.getEntries.mockReturnValue([
			{
				type: "message",
				message: {
					role: "assistant",
					usage: {
						input: 32_000,
						output: 108,
						cacheRead: 0,
						cacheWrite: 0,
						cost: { total: 0 },
					},
				},
			},
		] as never);
		registerTokenRate(mockPi as never);

		const sessionStart = getEventHandler(mockPi, "session_start");
		await sessionStart?.({ type: "session_start" } as never, ctx as never);
		const { footer } = mountFooter(ctx);

		const messageStart = getEventHandler(mockPi, "message_start");
		const messageUpdate = getEventHandler(mockPi, "message_update");
		const messageEnd = getEventHandler(mockPi, "message_end");
		const nowSpy = vi.spyOn(Date, "now");

		nowSpy.mockReturnValueOnce(1_000);
		await messageStart?.({ message: { role: "assistant" } } as never, ctx as never);

		nowSpy.mockReturnValueOnce(1_800);
		await messageUpdate?.({ message: { role: "assistant" } } as never, ctx as never);

		nowSpy.mockReturnValueOnce(4_800);
		await messageEnd?.(
			{ message: { role: "assistant", usage: { output: 150 } } } as never,
			ctx as never,
		);

		expect(footer.render(120)[1]).toContain("↑32k ↓108 6.1%/262k (auto) 50.0 tok/s");
	});

	it("falls back to total elapsed time when no streaming update was observed", async () => {
		const mockPi = createMockPi();
		const ctx = createMockCtx();
		registerTokenRate(mockPi as never);

		const sessionStart = getEventHandler(mockPi, "session_start");
		await sessionStart?.({ type: "session_start" } as never, ctx as never);
		const { footer } = mountFooter(ctx);

		const messageStart = getEventHandler(mockPi, "message_start");
		const messageEnd = getEventHandler(mockPi, "message_end");
		const nowSpy = vi.spyOn(Date, "now");

		nowSpy.mockReturnValueOnce(2_000);
		await messageStart?.({ message: { role: "assistant" } } as never, ctx as never);

		nowSpy.mockReturnValueOnce(5_000);
		await messageEnd?.(
			{ message: { role: "assistant", usage: { output: 90 } } } as never,
			ctx as never,
		);

		expect(footer.render(80).join("\n")).toContain("30.0 tok/s");
	});

	it("clears the footer status when an assistant message has no output usage", async () => {
		const mockPi = createMockPi();
		const ctx = createMockCtx();
		registerTokenRate(mockPi as never);

		const sessionStart = getEventHandler(mockPi, "session_start");
		await sessionStart?.({ type: "session_start" } as never, ctx as never);
		const { footer } = mountFooter(ctx);

		const messageEnd = getEventHandler(mockPi, "message_end");
		await messageEnd?.({ message: { role: "assistant", usage: {} } } as never, ctx as never);

		expect(footer.render(80).join("\n")).not.toContain("tok/s");
	});

	it("ignores non-assistant messages", async () => {
		const mockPi = createMockPi();
		const ctx = createMockCtx();
		registerTokenRate(mockPi as never);

		const messageStart = getEventHandler(mockPi, "message_start");
		const messageUpdate = getEventHandler(mockPi, "message_update");
		const messageEnd = getEventHandler(mockPi, "message_end");

		await messageStart?.({ message: { role: "user" } } as never, ctx as never);
		await messageUpdate?.({ message: { role: "user" } } as never, ctx as never);
		await messageEnd?.({ message: { role: "user" } } as never, ctx as never);

		expect(ctx.ui.setFooter).not.toHaveBeenCalled();
	});

	it("drops any in-flight assistant state when the session shuts down", async () => {
		const mockPi = createMockPi();
		const ctx = createMockCtx();
		registerTokenRate(mockPi as never);

		const sessionStart = getEventHandler(mockPi, "session_start");
		await sessionStart?.({ type: "session_start" } as never, ctx as never);
		const { footer } = mountFooter(ctx);

		const messageStart = getEventHandler(mockPi, "message_start");
		const sessionShutdown = getEventHandler(mockPi, "session_shutdown");
		const messageEnd = getEventHandler(mockPi, "message_end");
		const nowSpy = vi.spyOn(Date, "now");

		nowSpy.mockReturnValueOnce(1_000);
		await messageStart?.({ message: { role: "assistant" } } as never, ctx as never);
		await sessionShutdown?.({ type: "session_shutdown" } as never, ctx as never);

		nowSpy.mockReturnValueOnce(4_000);
		await messageEnd?.(
			{ message: { role: "assistant", usage: { output: 60 } } } as never,
			ctx as never,
		);

		expect(ctx.ui.setFooter).toHaveBeenCalledWith(undefined);
		expect(footer.render(80).join("\n")).not.toContain("tok/s");
	});
});
