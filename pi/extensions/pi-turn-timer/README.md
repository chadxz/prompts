# pi-turn-timer

Display the elapsed time for each completed pi agent response and each user
shell command as a custom message after the output.

## Use

Load the extension in pi and reload resources. After each completed agent
response, pi appends a subtle italic timing line like `Completed in 3.2s.` If
an agent run is cancelled, it appends `Cancelled after 3.2s.`

The extension also times user shell commands run with `!` or `!!`, appending a
matching line like `Completed in 320ms.` after the command output. If a shell
command is cancelled or times out, it appends `Cancelled after 3.2s.`

The extension filters its own timing messages out of future model context, so
those annotations stay visible in the session without polluting later prompts.

## Development

- `npm test`
- `npm run lint`
- `npm run check`
