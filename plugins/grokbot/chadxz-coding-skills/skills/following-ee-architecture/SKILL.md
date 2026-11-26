---
name: following-ee-architecture
description: >-
  Checks a design against what Convergint's Engineering Enablement (EE) team
  already runs before you propose it: platform primitives, architectural
  patterns, and the languages, frameworks, libraries, and services already in
  use. Use whenever you design a feature or service, write or review an ADR or
  RFC, pick a language, framework, library, datastore, queue, scheduler,
  workflow engine, auth method, or hosting option, reject an alternative, or
  review a pull request tagged Design, in ee-monorepo or any repo that deploys
  to the EE platform.
---

# Following EE architecture

EE's platform already gives teams a lot for free: workload types, secrets,
databases, Temporal, auth, observability, and deploys. A design that builds its
own version of one of those, or rejects one for the wrong reason, makes the
platform harder to run and harder to learn. Before you propose anything, find
out what's already there and start from it. Existing code is the default
starting point, not a rule. When a different approach fits the problem better,
use it and say why.

## The code is the precedent, not the ADRs

ADRs are a snapshot of a decision at the time it was made. The code has usually
moved on since then, so an ADR doesn't tell you how we build things today. Read
an ADR only to understand why a decision was made. Never cite one as precedent
for a new design.

Precedent comes from the code that's running now, and most of all from the apps
built most recently. They carry the latest version of each pattern. When an ADR
and the code disagree, follow the code.

The inventory in [references/primitives.md](references/primitives.md) lists the
established primitives and technologies, each with the path that owns it. Treat
it as a map, not the truth. The code is the truth, so check each entry you rely
on against its source path.

## Check before you propose

Do this before you write the Approach or Decision section of a design, ADR, or
RFC, and again before you write any "Rejected because" line.

1. **Name the need in plain terms.** Say what the design has to do, not which
   tool does it: "run something on a schedule", "retry an HTTP call for 15
   minutes", "know who the signed-in user is", "store a few tables".
2. **Look it up in the inventory.** Open
   [references/primitives.md](references/primitives.md) and find the rows that
   cover the need.
3. **Find the apps that already do it.** Run `rg` across `apps/`, `libraries/`,
   `tools/`, `platform/`, and `infrastructure/` on `main` of
   `convergint/ee-monorepo` for the need's keywords and for the manifest field
   or library that would serve it. List every app that does the thing.
4. **Pick the most recent one as the model.** Sort those apps by when they were
   created, for example with
   `git log --diff-filter=A --format=%as -- apps/<app>/project.json | tail -1`,
   and read the newest one or two closely. Where older apps do it differently,
   the newer way is the current pattern.
5. **Check the other repos that deploy to the platform** when the need isn't
   specific to ee-monorepo. `convergint/platform-examples` shows the supported
   shape for each workload type and language. Use GitHub code search across the
   `convergint` organization for the manifest field or library name.
6. **Read the related ADRs for the why.** Search `docs/adrs/` for decisions that
   touch the need, and read them to learn what problem each one solved and what
   it traded away. Use that to judge whether the same reasons apply to your
   case. Don't treat an ADR's decision or its rejected alternatives as binding;
   the code from steps 3 and 4 is what we do now.
7. **Start from the existing pattern.** Build it the way the newest app does,
   unless a different approach fits this problem better.
8. **If you diverge, say so in the design.** See the next section.

## When you diverge from what's there

Diverging is fine when another approach suits the problem better. An
architectural divergence from an existing pattern is an architectural decision,
so it gets an ADR. Follow the repo's ADR process in `docs/adrs/README.md` and
the "Architecture decisions" section of `CONTRIBUTING.md` in ee-monorepo. In the
ADR:

1. Name the existing primitive or pattern you're not using, and link the most
   recent app that uses it.
2. Say plainly why something else fits better here, for example "this needs a
   synchronous answer inside the caller's HTTP request, and a workflow would
   make the caller poll."
3. Compare against what the existing primitive really costs on our platform, not
   what it would cost from scratch.
4. Mention anything the divergence adds for others, such as a new runtime or
   library to maintain.

## Example: Temporal

Two ADRs for a Go web app rejected Temporal for debounce timers and short
retries. Both counted "a Temporal namespace, mTLS certificates, and a new worker
deployment" as the cost. On our platform that cost is close to zero:

- Every team already has a Temporal Cloud namespace in each environment, managed
  in `infrastructure/temporal-cloud/main.tf`.
- `useTemporal: true` in a deployment manifest makes the chart mount the
  workload's mTLS client certificate and inject the connection variables.
- Several EE apps already run a web workload that signals a Temporal worker,
  including `apps/sox-merge-readiness`, `apps/m365-group-calendar-slack`, and
  `apps/charon`, and `libraries/temporal-schedule` and
  `docs/temporal-development.md` cover Schedules.

The second ADR also leaned on the first one's rejection as precedent. Steps 3
and 4 above would have turned up the apps that show what we actually do. The
real trade-off was narrower: workflow determinism rules and a second deployment,
against hand-rolled timers, retries, and a delivery log in Postgres. That's a
fair debate to have, but it has to start from what the platform already gives
you.

## Writing it into an ADR or RFC

- In Context, name the existing primitives the design builds on, with links to
  the apps that use them and to their docs.
- In Decision, use the platform's own names for things: manifest fields such as
  `useTemporal`, `authenticationGate`, `databases`, and `deploymentGate`,
  workload types such as `web-application` and `worker`, and library paths.
- In Alternatives, if you don't use an existing primitive, name it and say why
  something else fits better, as in the divergence steps above.
- Follow the `writing-rfcs` skill for RFCs. For ADRs, follow the `writing-adrs`
  skill and the ADR process in `docs/adrs/README.md` in ee-monorepo, including
  when a decision also needs an RFC.

## When an ADR contradicts the code

Expect this. An accepted ADR records what we decided then, and the code keeps
changing after it. When an ADR's decision doesn't match current code, docs, or
`CONTRIBUTING.md`:

1. Follow the code. You don't need a new ADR to supersede the old one first.
2. Note the mismatch in your design or pull request, with the ADR, the path that
   shows what we do now, and one line on the difference, and mention it to the
   person you're working for.
3. Don't edit the ADR as a side effect of other work.

## Keep the inventory honest

When an entry in [references/primitives.md](references/primitives.md) no longer
matches the repo, or a primitive you relied on is missing from it, tell the
person you're working for which entry is wrong and what the repo shows, so the
skill gets updated. Keep entries to what something is and where it lives. Leave
out counts, version numbers, and status that will go stale; point at the file
that holds them.
