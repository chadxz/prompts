# pi-token-rate

Manage pi's footer status line with a focus on response speed and current
context usage.

## Use

Load the extension in pi and reload resources. It replaces the default footer
stats line with a compact status view that shows:

- total reported cost for the current session state
- current context size and context window, for example
  `100k/272k (52.2%)`
- the last measured assistant output token rate, for example `42.3 tok/s`

The context display comes from pi's automatic context usage estimate. Pi uses
its last valid assistant usage plus trailing message estimates, so the footer
shows the current live context size instead of cumulative input or cache usage
counters.

The token rate is based on the assistant message's reported output token usage
and how long the streamed response took. When pi can observe the first streamed
assistant update, it measures from that first token. Otherwise it falls back to
whole-message elapsed time.

Responses without output token usage do not publish a rate.

## Development

- `npm test`
- `npm run lint`
- `npm run check`
