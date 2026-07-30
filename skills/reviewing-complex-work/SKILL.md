---
name: reviewing-complex-work
description:
  Obtains an independent, read-only peer-agent review of complex completed work
  through an installed alternate CLI such as Claude Code, Codex CLI, or Cursor
  Agent, then verifies and reconciles the findings. Use automatically before
  finalizing substantial or high-risk code, architecture, infrastructure,
  migrations, security or authorization, concurrency, distributed systems,
  broad refactors, or long multi-step analysis where a second model could catch
  correctness gaps. Also use for explicit peer-review, second-opinion,
  adversarial-review, or cross-model-review requests. Skip routine mechanical
  edits and small low-risk changes.
---

# Reviewing Complex Work

Get one independent peer review after self-review and primary validation, while
there is still time to correct the work. Keep final judgment with the primary
agent.

## Decide When to Review

Review automatically when there is one high-risk signal or at least two
complexity signals.

High-risk signals include security, privacy, migrations, data loss, irreversible
state, concurrency, distributed behavior, public APIs, schemas, compatibility,
and infrastructure boundaries.

Complexity signals include work spanning components, substantial refactors with
behavior changes, interacting requirements or edge cases, unfamiliar systems,
important behavior that tests cannot cover, and nuanced analysis.

Skip mechanical, low-risk work covered by deterministic checks. Honor a user
request to skip or limit external review.

## Run the Review

1. Start a fresh, non-resumed session in another installed and authenticated
   agent CLI. Prefer a different provider:
   - Claude Code host: prefer Codex CLI.
   - Codex host: prefer Claude Code.
   - Cursor host: prefer the direct CLI from another provider.
   - Other hosts: choose the strongest available independent alternative.
2. Discover the current models rather than preserving model IDs here. Use the
   newest permitted flagship or coding model and the highest supported
   single-agent thinking level, commonly `max`. Do not use a mode that adds
   delegation unless the user asked for a panel.
3. Give the peer the task, review scope, repository instructions, raw diff or
   artifact, validation output, and relevant surrounding code. Do not include
   the primary agent's conclusions or suspected findings.
4. Run the peer from the actual worktree.

Use a 30-minute process timeout for an ordinary complex review. Choose 60
minutes up front for broad, high-risk, or unusually context-heavy work. Silence
is not evidence of slowness because agent CLIs often buffer output. Only after
the chosen window expires, try a faster tier, lower thinking by one step, or
switch peers. Do not silently fall back to an older model.

## Allow Investigation Without Mutation

Allow every useful read capability:

- source, history, documentation, dependency, and read-only shell inspection;
- web search, web fetch, and other read-only research tools;
- every non-mutating resource and action from every configured MCP connector.

Before and after the review, compare:

```bash
git rev-parse HEAD
git status --short
git stash list
```

Treat any unexpected mutation as a failed review. Keep the review one hop deep:
tell the peer not to apply this skill, delegate, or invoke another agent CLI.

## Reconcile and Report

Verify each finding against the task, source, and runtime behavior. Classify it
as confirmed, rejected with evidence, or unresolved. Fix confirmed in-scope
issues and rerun primary validation. Request at most one focused follow-up
review, and only when a consequential fix changes the risk surface or a material
finding remains unresolved. After that follow-up, resolve or report remaining
risk without requesting another review.

Report the peer model and thinking level, confirmed findings and fixes, and any
unresolved risks. A clean review is useful evidence, not proof of correctness.
