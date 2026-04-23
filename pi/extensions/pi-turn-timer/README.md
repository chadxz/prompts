# pi-turn-timer

Display the elapsed time for each completed pi agent response as a custom
message after the response output.

## Use

Load the extension in pi and reload resources. After each completed agent
response, pi appends a subtle italic timing line like `Completed in 3.2s.` If
the run is cancelled, it appends `Cancelled after 3.2s.`

The extension also filters its own timing messages out of future model context,
so the timing annotations stay visible in the session without polluting later
prompts.

## Development

- `npm test`
- `npm run lint`
- `npm run check`
