# EE platform primitives and technologies

What Engineering Enablement already runs, and where each piece lives. Paths are
in `convergint/ee-monorepo` on `main` unless a row names another repo. Read the
source path before you rely on a row; versions, counts, and which apps use what
live there, not here. ADR numbers point to why a primitive exists. The code at
the source path shows how we use it now.

## Find the current state

| To find                                             | Look at                                                                         |
| --------------------------------------------------- | ------------------------------------------------------------------------------- |
| Why a decision was made                             | `docs/adrs/`; read for reasons, not as precedent                                |
| The newest apps, which carry current patterns       | `git log --diff-filter=A --format='%as %s' -- 'apps/*/project.json' \| sort -r` |
| Repo-wide rules for code, secrets, Terraform, tests | `CONTRIBUTING.md` at the repo root                                              |
| Language rules                                      | `docs/go-development.md`, `docs/typescript-development.md`                      |
| How builds, tasks, and deploys fit together         | `docs/monorepo-language-ecosystems.md`                                          |
| Every manifest field a workload can set             | `tools/platform-deploy/schemas/<type>/schema.json`                              |
| Apps using a manifest feature                       | `rg -l '<field>: *true' apps --glob '*.yaml'`                                   |
| Known gaps we've chosen to live with                | `docs/known-technical-debt.md`                                                  |
| Retired apps and why                                | `docs/graveyard.md`                                                             |
| A working example per workload type and language    | `convergint/platform-examples`                                                  |

## Platform workload types

Teams describe a workload in a YAML manifest under the app's `deployment/`
folder, and `platform-deploy` turns it into a Helm release on the AKS clusters.
Pick the type that fits before reaching for raw Kubernetes.

| Type               | Use it for                                                    | Source                                                   |
| ------------------ | ------------------------------------------------------------- | -------------------------------------------------------- |
| `web-application`  | HTTP services, with an optional public hostname               | `tools/platform-deploy/charts/web-application`, ADR 0017 |
| `worker`           | Long-running background processes, including Temporal workers | `tools/platform-deploy/charts/worker`                    |
| `job`              | One-time or scheduled batch work                              | `tools/platform-deploy/charts/job`                       |
| `tcp-server`       | Non-HTTP servers other workloads dial                         | `tools/platform-deploy/charts/tcp-server`, ADR 0016      |
| `static-site`      | Prebuilt sites served by Cloudflare Workers static assets     | ADR 0024, `apps/static-site-operator`                    |
| `helm-application` | An app that needs its own chart; the escape hatch             | `tools/platform-deploy/docs/helm-applications.md`        |

Manifest features that replace work you'd otherwise build:

| Field                           | What the platform does                                                                                                                         | Source                                                                |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `useTemporal`                   | Mounts the mTLS client cert and injects Temporal Cloud connection variables for the team's namespace                                           | `docs/temporal-cloud-connectivity.md`, ADR 0010, ADR 0015 (dual auth) |
| `databases`                     | Injects connection variables for an existing Postgres, MySQL, SQL Server, or Redis, and turns on Datadog Database Monitoring                   | Schema `databases`, ADR 0015 (database monitoring), ADR 0028          |
| `databaseMigrationsCommand`     | Runs migrations before the release rolls out                                                                                                   | Schema                                                                |
| `authenticationGate`            | Puts the hostname behind Cloudflare Access with Entra sign-in and hands the app a signed principal in headers, plus session and sign-out paths | Schema description, ADR 0029, ADR 0055, ADR 0065                      |
| `deploymentGate`                | Bakes each production release and rolls back faulty ones                                                                                       | ADR 0021, `apps/release-gate-operator`                                |
| `env` with `op://` values       | Syncs 1Password items into the pod                                                                                                             | ADR 0003, `platform/external-secrets-operator`                        |
| `persistentStorage`             | Azure-backed volumes                                                                                                                           | Schema                                                                |
| `os`                            | Schedules Windows workloads                                                                                                                    | ADR 0026, ADR 0027                                                    |
| `buildArguments`, build secrets | Frontend and image build inputs                                                                                                                | ADR 0025, ADR 0044                                                    |

## Cross-cutting patterns

| Need                                                            | Established pattern                                                                                                                                       | Source                                                                                                                     |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Durable workflows, retries, timers, schedules                   | Temporal Cloud, one namespace per team per environment. A web workload receives events and signals a worker. Register Schedules with an idempotent upsert | `infrastructure/temporal-cloud`, `docs/temporal-development.md`, `libraries/temporal-schedule`, `apps/sox-merge-readiness` |
| Relational data                                                 | Azure Database for PostgreSQL Flexible Server, provisioned by Terraform in the app's own `infrastructure/` folder                                         | `apps/*/infrastructure/database`, `apps/pr-notifier/infrastructure`                                                        |
| Secrets                                                         | 1Password, synced by External Secrets Operator through 1Password Connect only                                                                             | `CONTRIBUTING.md` "1Password secrets", `platform/1password-connect-server`                                                 |
| Secret and key rotation reminders                               | A Date field and expiry alert on the 1Password item                                                                                                       | `CONTRIBUTING.md` "1Password secrets"                                                                                      |
| Who the user is                                                 | The platform principal headers behind `authenticationGate`; verify the signed assertion when you need proof                                               | ADR 0055, ADR 0065                                                                                                         |
| Group-based access to gated apps                                | The SCIM reference registry                                                                                                                               | ADR 0030, ADR 0033, ADR 0039, `infrastructure/web-application-scim`                                                        |
| Pod access to Azure                                             | Azure Workload Identity                                                                                                                                   | ADR 0005                                                                                                                   |
| A workflow in another repo needs an EE app's GitHub permissions | The workflow calls an EE platform app with its GitHub Actions OIDC token; only the app holds the private key                                              | `docs/oidc-calls-to-platform-apps.md`, ADR 0046, ADR 0053                                                                  |
| Acting on GitHub                                                | A dedicated GitHub App per service, with keys listed for rotation                                                                                         | `docs/github-app-key-rotation.md`                                                                                          |
| Metrics, pprof, and admin-only routes                           | Port 9090, never the public port                                                                                                                          | `docs/internal-endpoints.md`                                                                                               |
| Kubernetes-native automation                                    | A controller-runtime operator with its own CRD                                                                                                            | `apps/web-application-endpoint-operator`, ADR 0018, ADR 0057                                                               |
| Public endpoints, DNS, TLS                                      | The endpoint operator owns Ingress and certificates; F5 NGINX Ingress Controller; external-dns; cert-manager                                              | ADR 0013, ADR 0018, `platform/`                                                                                            |
| Cloudflare zone settings and hand-written DNS records           | `convergint/it-monorepo`, not ee-monorepo                                                                                                                 | ADR 0035                                                                                                                   |
| Cloudflare API access from a cluster                            | One account-owned token per cluster component                                                                                                             | `docs/cloudflare-api-tokens.md`                                                                                            |
| Observability                                                   | OpenTelemetry API in code, Datadog as the backend. Go uses `libraries/dd-otel-bootstrap` and `libraries/otel-error-tracking`                              | `docs/go-development.md`, `libraries/`                                                                                     |
| Monitors, dashboards, SLOs, synthetics                          | JSON definitions in `datadog/`, applied on merge to `main`                                                                                                | ADR 0058, `datadog/README.md`                                                                                              |
| Datadog credentials                                             | One API key per consumer; application keys only on service accounts                                                                                       | `docs/datadog-keys.md`                                                                                                     |
| Operator tools for staging workloads                            | A Datadog App                                                                                                                                             | ADR 0056, `apps/platform-operations`                                                                                       |
| Slack apps and notifications                                    | A Go platform app per Slack integration                                                                                                                   | `apps/pr-notifier`, `apps/m365-group-calendar-slack`                                                                       |
| Storage protection                                              | Blob versioning plus delete locks, never irreversible policy locks                                                                                        | ADR 0043                                                                                                                   |
| Infrastructure as code                                          | Terraform with an Azure Storage backend, colocated with the app                                                                                           | `CONTRIBUTING.md` "Terraform", `infrastructure/terraform-backend`                                                          |
| Private Terraform registry                                      | Terrakube                                                                                                                                                 | `infrastructure/terrakube`, `platform/terrakube`                                                                           |
| CI                                                              | Nx for affected detection, mise for tasks, one CI workflow                                                                                                | ADR 0006, `.github/workflows/ci-nx.yml`                                                                                    |
| CD                                                              | `deploy` targets in `project.json`, including mise-task targets and ordered phases                                                                        | ADR 0009, ADR 0015 (mise tasks), ADR 0019                                                                                  |
| Self-hosted runners                                             | Actions Runner Controller on AKS                                                                                                                          | ADR 0011, `docs/self-hosted-runners.md`                                                                                    |
| Dependency updates                                              | Self-hosted Renovate, auto-approved through the dependency approver                                                                                       | ADR 0014, ADR 0032, ADR 0046, `docs/renovate.md`                                                                           |
| Releasing a product                                             | Changesets, announced in the releases channel by a shared action                                                                                          | `CONTRIBUTING.md` "Product releases"                                                                                       |
| Pull request review gates                                       | review-policy tiers and Ship auto-approval                                                                                                                | ADR 0041, ADR 0048, `tools/review-policy`, `tools/ship-auto-approve`                                                       |

## Languages and frameworks

| Area                               | Established choice                                                                                                                                                                                             | Source                                                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Platform services, operators, CLIs | Go, standard library `net/http`, `slog` JSON logs, cobra for CLIs, controller-runtime for operators, `pgx` for Postgres, `go-github` with `ghinstallation` for GitHub                                          | `docs/go-development.md`, each app's `go.mod`                                              |
| Go linting and module layout       | The shared policy in `tools/go-quality` and the module recipe                                                                                                                                                  | `docs/go-development.md#module-recipe`                                                     |
| Web UIs and Node services          | TypeScript on Node's current Active LTS in one pnpm workspace. Svelte and SvelteKit for app UIs, Kysely with `pg` for data, Better Auth with `libraries/better-auth-entra-id` when an app runs its own sign-in | `docs/typescript-development.md`, `pnpm-workspace.yaml`, `apps/charon`, ADR 0007, ADR 0038 |
| TypeScript tooling                 | vitest, oxlint, oxfmt, `tsc --noEmit` type checks                                                                                                                                                              | `pnpm-workspace.yaml` catalog, `docs/typescript-development.md`                            |
| Temporal SDKs                      | Go SDK with `contrib/opentelemetry`; TypeScript SDK with `libraries/temporal-interceptors-opentelemetry-v2`                                                                                                    | `docs/temporal-development.md`, `docs/go-development.md`                                   |
| Task runner and toolchain pins     | mise, with hk for git hooks                                                                                                                                                                                    | `mise.toml`, `docs/git-hooks.md`                                                           |
| Python, Ruby, .NET                 | Supported by the platform with examples; not EE's default for new services                                                                                                                                     | `convergint/platform-examples`, `apps/hermes` (owned outside EE)                           |

## Picking between Go and TypeScript

Go is the default for platform services, operators, webhook receivers, and CLIs.
Svelte is the default for UIs: a SvelteKit app in TypeScript when the UI is the
app, as in `apps/charon`, or a Svelte app embedded in the Go service when a Go
service needs a UI, as in `apps/actions-values-sync`.
