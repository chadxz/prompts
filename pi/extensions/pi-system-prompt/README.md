# pi-system-prompt

Expose a `/system-prompt` command that prints pi's current system prompt.

## Use

Load the extension in pi and reload resources. Run `/system-prompt` to show the
current effective system prompt via an info notification.

This reads the prompt through `ctx.getSystemPrompt()`, so it reflects pi's
current system prompt string at the time the command runs.

## Development

- `npm test`
- `npm run lint`
- `npm run check`
