import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export const SYSTEM_PROMPT_COMMAND = "system-prompt";

export default function registerSystemPrompt(pi: ExtensionAPI) {
	pi.registerCommand(SYSTEM_PROMPT_COMMAND, {
		description: "Print the current system prompt",
		handler: async (_args, ctx) => {
			const prompt = ctx.getSystemPrompt();
			ctx.ui.notify(prompt, "info");
		},
	});
}
