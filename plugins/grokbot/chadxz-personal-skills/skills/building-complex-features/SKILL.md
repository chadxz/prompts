---
name: building-complex-features
description: >-
  Use before implementation starts on a non-trivial or major feature that spans
  multiple components (services, infrastructure, configuration, docs, or agent
  tooling). Runs the work as a Cursor Project and guides research, a simple
  reviewed plan, the build, PR review, CI babysitting, and end-to-end
  verification.
---

# Building complex features

A workflow for shipping features that touch several components. Each step has a
short rationale. Skip a step only when it clearly doesn't apply, and say so;
never skip research, docs, review, or verification.

## Run it as a Cursor Project

Do all complex work in a Cursor Project, not a single cloud agent or a local
session. Launch the Project on the work's repository (for a Grok Bot, the
CloudAgent tool's launch with `project: true`), give the coordinator the
outcome you want, and let it plan, delegate this workflow's steps to its
agents, and bring the results back. Send follow-ups to the same Project
rather than starting new agents beside it. A Project only goes one level
deep, so its agents can't start Projects of their own. _Why:_ a Project keeps
shared context across months of work and many PRs, runs agents in parallel,
and can follow the PRs and CI it opens.

## Workflow

1. **Research first, read-only.** Build a full mental map of the feature area
   before changing anything: architecture, components, data flow, config,
   deployment, agent/tool interactions, limitations, open questions, and prior
   docs and decisions. _Why:_ most rework comes from building on a wrong
   assumption about how the system already works.

2. **Document major features and architectural decisions as an ADR first.** Open
   the ADR in its own pull request, with no implementation in it, and label it
   `requires-review-by-chad` (see the `creating-pull-requests` skill). Don't
   start implementation until Chad posts LGTM on the ADR, unless he explicitly
   says to proceed without it. _Why:_ Chad reviews major decisions before
   they're built, and a standalone ADR is quick to review and easy to find
   later.

3. **Design public interfaces up front.** Explicitly design every public
   interface the feature adds or changes, in whatever form it takes: shared
   library APIs, public REST APIs, CLI commands and flags, JSON or YAML schemas
   and config formats, events and message payloads, and similar. Put the
   concrete shapes (signatures, endpoints, fields, types, examples) in the ADR
   or plan so they get reviewed before implementation starts. Don't let an
   interface first appear in the implementation PR. When the feature adds or
   changes Temporal workflows, activities, signals, child workflows, schedules
   or their triggers, include a Mermaid `stateDiagram-v2` in the ADR or plan
   that shows how the workflows and activities flow, using the names they'll
   have in code, so the flow is reviewed before implementation. That diagram
   later carries into the PR's `How?` section (see the `creating-pull-requests`
   skill). _Why:_ public interfaces and Temporal workflow flows are expensive to
   change once others depend on them, so they need review while they're still
   cheap to change.

4. **Write a simple, high-level plan.** Capture requirements and research
   findings, not implementation details. Keep both the plan and the intended
   implementation simple, with no over-engineering, and make it legible to peer
   agents and humans. Use the `building-implementation-plans` skill if it is
   available. If the plan needs more than a short paragraph to explain, cut it
   to the simple version and build that. _Why:_ a short plan is easy to review
   and hard to hide complexity in.

5. **Get independent plan reviews.** Ask several strong models, from different
   model families where possible, to review the plan. Tell reviewers explicitly
   not to over-engineer and to protect simplicity. If only one model is
   available, say so in the plan. _Why:_ different models catch different blind
   spots; unconstrained reviewers tend to add scope.

6. **Evaluate the feedback once.** Incorporate only what you agree with, and
   record what you declined and why (in the plan or PR description). Don't
   request another review round. _Why:_ you own the design; repeated rounds
   drift toward complexity.

7. **Build it, docs included.** Implement the plan, update user and developer
   docs, and add any new pattern to the agent rules at the right repo level.
   _Why:_ undocumented features and patterns get rediscovered or broken by the
   next contributor.

8. **Ship a working example.** The pull request includes a working example or
   demo of the feature. _Why:_ reviewers can see it work instead of inferring it
   from the diff.

9. **Request bot reviews, as the human.** Ask the code-review bots used in the
   repo to review the PR by commenting with each bot's trigger phrase. Post
   those trigger comments (and any other PR comment that needs posting)
   automatically from the human owner's own GitHub account, through their GitHub
   connector, not from a bot or coding-agent account, and don't ask first each
   time. _Why:_ cheap, fast extra eyes before human review; review bots often
   ignore triggers from bot accounts and skip draft PRs.

10. **Babysit the PR.** Watch CI and address every bot comment and failing check
    until checks pass and every comment has a fix or a reply explaining why it
    doesn't apply. _Why:_ a red or noisy PR wastes reviewer time.

11. **Verify end to end.** Exercise the feature as a user would, in a real
    environment (a realistic one only if real is impossible, and say which). If
    testing is blocked, report the problem to the human instead of guessing or
    claiming success. _Why:_ passing checks are not proof that the feature
    works.

## Principles

- **Simplicity over cleverness.** Default to the smallest change that solves the
  problem in front of you. A reusable pattern is the simplest one others can
  copy, not a framework. Before adding config, options, exemptions, enforcement
  or new abstractions, ask yourself whether a real case needs them today. If
  not, leave them out and note them as later work.
- **Scale complexity to the stakes.** Doing it right is fine, but you don't have
  to build for every possible edge case. Match the solution's complexity,
  including error handling, to the situation and how critical the code is. A
  helper tool needs less error handling than production code serving customers.
  Tools should help the team without becoming a byzantine labyrinth of fragile
  software, so in low-stakes tools, handle rare edge cases by hand and note them
  instead of coding for them.
- **Simplicity wins ties.** When best practice or a reusable-pattern goal
  conflicts with simplicity, pick simplicity. Decide this yourself; don't
  escalate it.
- **No shortcuts.** Don't skip research, docs, review, or verification to finish
  faster.
- **Evidence over assumptions.** Back claims with code you read, output you ran,
  or behavior you observed.
- **Name work descriptively.** When talking with the human, in chat or voice,
  refer to work by a short descriptive name ("the static site auth gate", "the
  release bootstrap fix"), never by a bare ticket ID or pull request number,
  which are meaningless and easy to mix up. Label ticket and PR links by
  description too.

This skill is expected to evolve. Update it when a step proves unnecessary or a
missing step keeps causing problems.
