import { describe, expect, it, vi } from "vitest";

import registerSystemPrompt, { SYSTEM_PROMPT_COMMAND } from "./pi-system-prompt.ts";

function createMockPi() {
	return {
		registerCommand: vi.fn(),
	};
}

describe("pi-system-prompt", () => {
	it("registers the system prompt command", () => {
		const mockPi = createMockPi();

		registerSystemPrompt(mockPi as never);

		expect(mockPi.registerCommand).toHaveBeenCalledWith(
			SYSTEM_PROMPT_COMMAND,
			expect.objectContaining({
				description: "Print the current system prompt",
				handler: expect.any(Function),
			}),
		);
	});

	it("prints the current system prompt via a notification", async () => {
		const mockPi = createMockPi();
		registerSystemPrompt(mockPi as never);

		const command = mockPi.registerCommand.mock.calls[0]?.[1] as
			| { handler: (args: string, ctx: { getSystemPrompt(): string; ui: { notify: typeof vi.fn } }) => Promise<void> }
			| undefined;
		const notify = vi.fn();
		const ctx = {
			getSystemPrompt: vi.fn(() => "You are a helpful assistant."),
			ui: {
				notify,
			},
		};

		await command?.handler("", ctx);

		expect(ctx.getSystemPrompt).toHaveBeenCalledOnce();
		expect(notify).toHaveBeenCalledWith("You are a helpful assistant.", "info");
	});
});
