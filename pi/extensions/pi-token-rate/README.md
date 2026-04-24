# pi-token-rate

Show the last measured assistant output token rate in pi's footer stats line.

## Use

Load the extension in pi and reload resources. After an assistant response
finishes, pi appends a dim value like `42.3 tok/s` to the footer line that
shows token usage and context usage.

The rate is based on the assistant message's reported output token usage and
how long the streamed response took. When pi can observe the first streamed
assistant update, it measures from that first token. Otherwise it falls back to
whole-message elapsed time.

Responses without output token usage do not publish a rate.

## Development

- `npm test`
- `npm run lint`
- `npm run check`
