# pi-mux

`pi-mux` gives pi a small, stable model-facing tool surface over multiple
providers.

It exposes exactly three tools to the model:

- `find_tools`
- `get_tool_details`
- `call_tool`

At runtime, `pi-mux` discovers its internal provider modules dynamically.

The bundled providers are Cloudflare, Datadog, Notion, and Slack. Cloudflare
uses the official code-mode API MCP endpoint, which keeps its approximately
2,500 API operations behind three compact server tools.

The human control plane stays outside the model-facing tool API. Authentication
and connection state are managed through `/mux` commands.

## Commands

`pi-mux` adds this command surface:

- `/mux`
- `/mux status`
- `/mux tools <provider>`
- `/mux connect <provider>`
- `/mux disconnect <provider>`

`/mux` and `/mux status` show the current provider connection state.

`/mux tools <provider>` lists the provider's discovered tools with their tool
ids, native names, availability, and short descriptions.

## Tool behavior

### `find_tools`

Use this first when the model needs a capability and does not yet know which
underlying provider tool to call.

`find_tools`:

- searches a lightweight catalog over tool id, provider, native tool name,
  normalized display name, and a short normalized description
- returns tools whether or not they are currently available
- ranks available tools ahead of unavailable tools when the matches are
  otherwise similar

### `get_tool_details`

Use this after `find_tools` and before `call_tool`.

It returns:

- `tool_id`
- `provider`
- `name`
- `description`
- `available`
- `input_schema`
- `output_schema` when the upstream provider exposes one

Unknown tool ids fail plainly.

### `call_tool`

Use this only after `find_tools` and `get_tool_details`.

`call_tool`:

- validates arguments against the discovered input schema
- calls the provider tool through `pi-mux`
- returns `ok: false` when the tool is unavailable, unknown, or fails
- validates `result` against the upstream output schema when one exists
- returns the raw upstream result when an upstream raw result is available

If a provider tool is unavailable, the model should ask the user to run
`/mux connect <provider>`.

## Availability behavior

Unavailable tools remain discoverable. `pi-mux` caches discovered provider
catalogs in `pi-mux-state.json` under `PI_CODING_AGENT_DIR` (by default,
`~/.pi/agent/pi-mux-state.json`), so a provider can disconnect later without
disappearing from tool discovery.

That means the model can still:

1. discover the right tool
2. inspect its schema
3. ask the user to connect the provider

This avoids hiding useful capabilities while still letting the model plan
correctly.

## Internal provider code

`pi-mux` replaces the old direct MCP-backed provider extensions in normal use.

The provider implementations it needs now live directly inside the `pi-mux`
package under `pi/extensions/pi-mux/providers/`. `pi-mux` discovers those
provider modules dynamically rather than hardcoding a provider list. They are
internal implementation details and are not auto-loaded as standalone pi
extensions.

### Cloudflare Codex adapter

Cloudflare currently omits an OAuth issuer parameter that its metadata says it
will return. Codex rejects that callback, so the Cloudflare provider includes a
small stdio adapter based on the official MCP TypeScript SDK. It keeps an
independent OAuth grant in `~/.codex/cloudflare-mcp-auth.json`.

From the `pi-mux` package directory, authenticate it once:

```bash
node providers/cloudflare/cloudflare-mcp-stdio.ts --authenticate
```

Then configure Codex with the adapter's absolute path:

```bash
codex mcp add cloudflare-api -- node \
  "$PWD/providers/cloudflare/cloudflare-mcp-stdio.ts"
```

The adapter should be removed in favor of Codex's native streamable HTTP
transport after Cloudflare's callback includes the advertised issuer.

Each provider module is meant to feel like a normal pi extension first:

- `providers/<name>/index.ts` exports the extension as its default export
- `pi-mux` infers the provider id from the directory name by default
- `pi-mux` infers the provider command when the extension registers exactly one
  command
- `pi-mux` expects the standard control tool names `<provider>_mcp_connect`,
  `<provider>_mcp_disconnect`, and `<provider>_mcp_status`
- if a provider needs non-standard command or control tool names, it can export
  an optional `muxProvider` object from `index.ts`

That keeps the mux/provider boundary small and familiar. Providers stay close to
ordinary pi extensions, and only the provider-specific control-plane details
need to be declared when they differ from the defaults.

When a provider's connect tool needs interactive setup before it can succeed, it
should signal that through the normal tool result details with
`requiresInteractiveSetup: true`. That keeps bootstrap behavior inside the
provider's normal tool contract instead of adding another mux-specific knob.

If a provider does need overrides, use the helper exported by the package:

```ts
import { defineMuxProvider } from "pi-mux";

export { default } from "./my-provider.ts";

export const muxProvider = defineMuxProvider({
  commandName: "my-provider",
  controls: {
    connect: "open_connection",
    disconnect: "close_connection",
    status: "connection_status",
  },
});
```

`pi-web` is separate again and loads as its own standalone extension.

## Quick verification

Check provider status from the command line:

```bash
pi -p "/mux status" --no-session
```

From RPC mode, `get_commands` should show only the `mux` extension command for
this integration layer, not the old provider-specific command set.

## Development

Install dependencies for the mux package:

```bash
cd pi/extensions/pi-mux
npm install
```

Run tests:

```bash
npm test
```

Run lint:

```bash
npm run lint
```

The repo setup script also installs the dependencies needed by `pi-mux` and its
internal provider code:

```bash
./setup_pi.sh
```
