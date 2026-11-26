---
name: writing-adrs
description: >-
  Writes and reviews architecture decision records (ADRs) so they stay short
  and stay true: one decision, the forces behind it, the options rejected and
  the consequences, with implementation detail left to the code, docs, and pull
  request. Use whenever you draft, revise, review, supersede, or amend an ADR,
  or turn a design, RFC, or pull request into one, in ee-monorepo or any repo
  with a docs/adrs directory.
---

# Writing ADRs

An ADR records one architectural decision and why we made it. It's a snapshot of
that moment. Later readers open it to learn why the code is the way it is. For
how to build something today, they follow the running code (see the
`following-ee-architecture` skill).

An ADR that describes how the decision gets built goes stale the first time the
code changes, and then it needs amending. Write only what stays true while the
implementation moves on: the problem, the forces, the choice, the trade-offs.

The repo owns the process. Read `docs/adrs/README.md` and the "Architecture
decisions" section of `CONTRIBUTING.md` in ee-monorepo before you start. They
cover when an ADR is needed (every major feature and architectural decision),
the pull request and review rules, statuses, attribution, and how to record
risks. This skill covers what goes in the ADR. If the two disagree, follow the
repo and tell the person you're working for.

## What goes in

- **The problem and its forces.** What we need, what constrains us, and which
  forces pull against each other (cost, security, operability, team skills,
  time). State facts without arguing for an option, and name the existing
  platform pieces the decision builds on.
- **One decision.** A few sentences starting "We will", stated at the level of
  the choice: which technology, pattern, boundary, contract, or ownership model,
  and what it covers. Leave out how to build it.
- **The options we didn't pick.** Each one in its strongest honest form, with a
  specific reason it lost. Follow the alternatives rules in the `writing-rfcs`
  skill; they apply here too.
- **Consequences, good and bad.** What gets easier, what gets harder, what we
  now have to run or maintain, and which follow-up decisions this creates.
- **Links to the detail.** The RFC, related ADRs, and the design doc, runbook,
  or pull request that holds the specifics.

## What stays out

Ask of every sentence: could the code change this without the decision changing?
If so, it doesn't belong in the ADR. Put it where it'll be kept current.

| Detail                                                          | Where it goes                                     |
| --------------------------------------------------------------- | ------------------------------------------------- |
| Config values, timeouts, retry counts, thresholds, env vars     | The code or config, with a comment if it's subtle |
| API endpoints, payload schemas, database schemas, field names   | The code, migrations, an OpenAPI file, or `docs/` |
| File paths, function names, library versions, permission scopes | The code or Terraform                             |
| Rollout order, cutover steps, task lists, runbooks              | The pull request, the Linear ticket, or `docs/`   |
| Test evidence, command output, review findings, in-flight PRs   | The pull request                                  |
| Open questions and later work                                   | Linear tickets                                    |

A number belongs only when the number is the decision, such as "We will keep one
Postgres database per application." Name the concept ("a short debounce window")
instead of the value ("a 90-second debounce").

When reviewers ask for more detail, put it in the design doc or pull request and
link it from the ADR. Detail added to satisfy a review comment is how ADRs grow
into specs that need amending.

## Length

Aim for one or two printed pages, roughly 40 to 120 lines of Markdown. A reader
should get the decision and its reasons in a few minutes.

Past two pages, the ADR is almost always carrying design detail or more than one
decision. Move the detail out, or split it:

- If the title needs "and", or the Decision section has its own subsections,
  it's more than one decision. Write one ADR per decision and link them.
- If the decision comes in phases (now, later, eventually), write one ADR per
  phase.

## Template

ee-monorepo scaffolds ADRs with [adr-tools](https://github.com/npryce/adr-tools)
(`adr new "Title"`), which uses Michael Nygard's format. Keep its sections and
add the ones the repo's README asks for:

```markdown
# 66. <Verb phrase that names the decision>

Date: YYYY-MM-DD

## Status

Proposed

## Context

Two to four paragraphs: the problem, the forces in tension, and the constraints,
with links to the platform pieces this builds on.

## Decision

We will <choice> because <the forces that decided it>.

At most a paragraph or two more on what the decision covers and what it doesn't.

## Risks and assumptions

Only unconfirmed risks or assumptions, each marked as the README asks.

## Consequences

What gets easier, what gets harder, what we now run or maintain, and which
decisions follow from this one.

## Alternatives

### <Option>

The strongest honest version in a sentence or two. Rejected because <specific,
verified reason>.
```

Title it as an action, like the repo's existing ADRs ("Use Helm instead of
Crossplane for our platform abstraction"). Drop "Risks and assumptions" when
there aren't any open ones.

## Once accepted, supersede instead of amending

While an ADR is Proposed, edit it as much as you like. Once it's Accepted, its
decision and consequences are frozen.

- **Only the implementation changed.** Leave the ADR alone. The code, docs, and
  pull request are the record of how it's built now.
- **The decision changed.** Write a new ADR. `adr new -s 48 "Title"` marks the
  new one "Supersedes ADR 48" and the old one "Superseded by" the new one. That
  status link is the only change to the old ADR.
- **A follow-up decision narrows or extends the old one.** Write a new ADR that
  links back with "Amends" (`adr new -l "48:Amends:Amended by" "Title"`). Don't
  rewrite the accepted one.
- **Typos, formatting, or broken links.** Fix them in place. The README treats
  these as editorial and they skip the extra review.

If an accepted ADR keeps needing edits, it's holding implementation detail.
Supersede it with a shorter one rather than patching it again.

## Check it before you open the pull request

Re-read the draft as a reviewer, and use the same list when you review someone
else's ADR:

1. **Will every paragraph still be true in six months?** Picture a routine
   change: a renamed endpoint, a new config value, a different rollout. If any
   paragraph would turn false, cut it or move it to the code, docs, or pull
   request.
2. Is it one decision, and does the title state it?
3. Does the Decision section stand on its own, without reading the code or the
   linked design doc?
4. Does every rejected option get its strongest version and a specific, verified
   reason?
5. Do the consequences include the costs, not only the benefits?
6. Is it within about two pages?
7. Does it build on what the platform already runs, per the
   `following-ee-architecture` skill?
8. Does it follow the repo's rules: no attribution, a status with no date, and
   no in-flight status such as "PR open" or "not yet tested"?
9. Is it written in plain words, per the `writing-in-my-voice` skill?

When you review, flag implementation detail as "move this to the code or the
pull request." Asking for more of it in the ADR makes the problem worse.

## Sources

This guidance follows the common ground across the standard ADR sources. See
[references/sources.md](references/sources.md) for what each one says and where
they differ.
