---
name: managing-temporal-cloud-resources
description:
  Manage Convergint Temporal Cloud resources from a local machine using Chad's
  configured Temporal CLI profiles and Temporal Cloud API keys. Use when the
  user asks to list, inspect, start, signal, query, cancel, or terminate
  workflows; inspect schedules, task queues, workers, namespaces, API keys, or
  service accounts; refresh Temporal CLI profiles; or install and authenticate
  the Temporal and Temporal Cloud CLIs with mise.
---

# Managing Temporal Cloud Resources

## Overview

Use the `temporal` CLI for namespace-scoped operations such as workflows,
schedules, task queues, workers, and batches. Use the Temporal Cloud CLI
surface (`temporal cloud ...` when available, or `tcld ...` on Chad's current
machine) for account-level resources such as namespaces, API keys, service
accounts, and users.

For SDK code, worker implementation, workflow determinism, and application
development, use the `developing-temporal-applications` skill instead. This
skill is for operating Temporal Cloud from the command line.

## Local setup

Start by checking the local tools and profiles:

```bash
command -v temporal
temporal --version
temporal config list
```

The configured profile convention is:

- profile name: the Temporal namespace without the `.sajb4` account suffix
- namespace: the fully-qualified namespace, including `.sajb4`
- address: `us-east-2.aws.api.temporal.io:7233`
- auth: profile-local `api_key`

Examples:

```text
engineering-enablement-staging -> engineering-enablement-staging.sajb4
internal-tools-production      -> internal-tools-production.sajb4
platform-staging               -> platform-staging.sajb4
```

Use the profile name directly:

```bash
temporal --profile engineering-enablement-staging workflow list --limit 10
```

Do not add `--namespace` for normal use. The shorthand profiles already carry
the namespace. Use `--namespace` only when intentionally overriding a profile or
debugging an incomplete profile.

Inspect profile contents safely by redacting the API key:

```bash
temporal --profile engineering-enablement-staging config get \
  --output json |
  jq 'del(.api_key)'
```

Never paste API keys into chat, saved files, or command output unless the user
explicitly asks to reveal a token. Turn off shell tracing before commands that
touch tokens.

## Common operations

Prefer `--output json` when the result will be parsed or summarized.

```bash
# Workflows
temporal --profile <profile> workflow list --limit 10
temporal --profile <profile> workflow describe --workflow-id <workflow_id>
temporal --profile <profile> workflow show --workflow-id <workflow_id>
temporal --profile <profile> workflow query --workflow-id <workflow_id> \
  --type <query_type>
temporal --profile <profile> workflow signal --workflow-id <workflow_id> \
  --name <signal_name> --input '<json>'
temporal --profile <profile> workflow cancel --workflow-id <workflow_id>
temporal --profile <profile> workflow terminate --workflow-id <workflow_id> \
  --reason '<reason>'

# Schedules
temporal --profile <profile> schedule list
temporal --profile <profile> schedule describe --schedule-id <schedule_id>
temporal --profile <profile> schedule trigger --schedule-id <schedule_id>

# Task queues and workers
temporal --profile <profile> task-queue describe --task-queue <task_queue>
temporal --profile <profile> worker deployment list
```

Before destructive operations such as `terminate`, `delete`, schedule updates,
or API key deletion, confirm the profile, namespace, workflow ID, and expected
impact with the user unless the request already names them clearly.

## Install and authenticate

If `temporal` is missing, lacks `config --profile`, or the user asks for fresh
setup, follow the Temporal CLI access instructions from the Notion page titled
`Durable Execution with Temporal`. Use the Notion connector to fetch the page
when exact current wording matters.

Install with mise in the repo or directory where the user wants the tools
pinned:

```bash
mise use --pin "aqua:temporalio/cli" "github:temporalio/cloud-cli"
temporal --version
```

If mise reports an untrusted config in a new directory, run `mise trust` rather
than working around mise.

Authenticate to Temporal Cloud and create a personal API key. The Notion doc
uses this command form:

```bash
temporal cloud login
temporal cloud apikey create-for-me \
  --display-name "$(whoami)" \
  --description "Personal CLI access" \
  --expiry-duration 365d \
  --output json
```

If the installed Cloud CLI exposes `tcld` instead, use the equivalent commands:

```bash
tcld login
tcld apikey create \
  --name "$(whoami)" \
  --description "Personal CLI access" \
  --duration 365d
```

The API key secret is printed once. Store it before closing the terminal. Use
the regional endpoint for API-key access; namespace endpoints such as
`engineering-enablement-staging.sajb4.tmprl.cloud:7233` are mTLS endpoints and
expect client certificates.

## Configure profiles

For a single namespace, configure the shorthand profile like this:

```bash
export TEMPORAL_API_KEY='<token from Temporal Cloud>'
profile='engineering-enablement-staging'
namespace='engineering-enablement-staging.sajb4'
address='us-east-2.aws.api.temporal.io:7233'

temporal --profile "$profile" config set --prop address --value "$address"
temporal --profile "$profile" config set --prop namespace --value "$namespace"
temporal --profile "$profile" config set --prop api_key \
  --value "$TEMPORAL_API_KEY"
```

To refresh profiles for every namespace, use an existing profile's API key or a
newly created token. `tcld namespace list` accepts the same API key through
`TEMPORAL_CLOUD_API_KEY`.

```bash
source_profile='engineering-enablement-staging-api-key'
api_key=$(
  temporal --profile "$source_profile" config get --output json |
    jq -r '.api_key'
)
address='us-east-2.aws.api.temporal.io:7233'

TEMPORAL_CLOUD_API_KEY="$api_key" tcld namespace list |
  jq -r '.namespaces[]' |
  while IFS= read -r namespace; do
    profile="${namespace%.sajb4}"

    temporal --profile "$profile" config set --prop address \
      --value "$address"
    temporal --profile "$profile" config set --prop namespace \
      --value "$namespace"
    temporal --profile "$profile" config set --prop api_key \
      --value "$api_key"
    temporal --profile "$profile" config delete --prop tls >/dev/null 2>&1 \
      || true
  done
```

Verify one profile before reporting success:

```bash
temporal --profile engineering-enablement-staging workflow list --limit 1
```
