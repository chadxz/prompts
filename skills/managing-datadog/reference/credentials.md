# Datadog Credentials Setup

This plugin loads Datadog API credentials from 1Password at command
invocation time using `op run`. This means you authenticate once per
command, and the resolved keys are used for all API calls within that
session.

## Setup

### 1. Store credentials in 1Password

Ensure your Datadog API key and Application key are stored in
1Password. Note the vault, item, and field names — you'll need them
in the next step.

### 2. Configure environment variables

Set environment variables with 1Password secret references so that
`op run` can resolve them. Add these to your shell profile
(`.zshrc`, `.bashrc`, etc.):

```bash
export DATADOG_API_KEY="op://vault-name/Datadog/api-key"
export DATADOG_APP_KEY="op://vault-name/Datadog/app-key"
export DD_SITE="us3.datadoghq.com"
```

Both `DD_API_KEY`/`DD_APP_KEY` and `DATADOG_API_KEY`/`DATADOG_APP_KEY`
are supported. The skill checks both variants.

Replace `vault-name` and the field paths with your actual 1Password
item references. The `op://` URI format is:
`op://vault/item/[section/]field`.

### 3. Verify

```bash
op run -- bash -c 'echo "API key loaded: ${DD_API_KEY:0:4}..."'
```

You should see the first 4 characters of your API key.

## Datadog site

The default site is `us3.datadoghq.com`. To use a different Datadog
site, set `DD_SITE` accordingly. Both `DD_SITE` and `DATADOG_SITE`
are supported.

## Troubleshooting

| Symptom                        | Fix                                                                      |
|--------------------------------|--------------------------------------------------------------------------|
| `op: command not found`        | Install the [1Password CLI](https://developer.1password.com/docs/cli/get-started/) |
| `isn't a secret reference`     | Ensure values use `op://` format                                         |
| `could not resolve secret`     | Verify the vault/item/field path in 1Password                            |
| Prompted repeatedly            | Ensure 1Password desktop app is running and unlocked                     |
| Keys show as literal `op://`   | Env vars aren't exported — check your shell profile                      |
