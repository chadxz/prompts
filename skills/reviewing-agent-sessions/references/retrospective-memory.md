# Retrospective memory

This reference preserves decisions that future session reviews should not have
to rediscover. Newer explicit instructions from Chad override it.

## Interpretation rules

- Treat an explicit correction or stated preference as stronger evidence than a
  frequency metric.
- Distinguish a recommendation Chad rejected from one he has not discussed or
  has not actioned yet.
- Treat a requested implementation as acceptance of that recommendation.
- Give each recommendation a stable `YYYY-MM-short-name` ID and preserve it
  across status changes.
- Preserve the reason behind a decision, not only its final status.
- Reopen a settled decision only when new evidence changes the tradeoff.
- Propose changes to this reference in the monthly report. Do not edit it
  automatically.

## Standing preferences

### Primary model and delegation

Keep the smartest available primary model at xhigh. Chad does not want to pay a
model-selection tax on every task. When subagents are authorized, the primary
agent should route bounded mechanical extraction to Terra low or medium and
retain architecture, security, ambiguous diagnosis, synthesis, mutations, and
final verification with Sol high or xhigh.

This supersedes the July 2026 recommendation to make high the global default.

### Writing voice

Preserve the broad `writing-in-my-voice` skill and its detailed guidance. Chad
gets high first-pass acceptance and values that it avoids recognizable AI
writing patterns.

Evaluate changes through first-pass acceptance, edit distance, factual
preservation, and AI-tell avoidance. Aggregate context volume alone is not a
reason to narrow the skill.

### Browser interaction

Safari is Chad's primary browser. Prefer Codex Computer Use with Safari over
Chrome or extension-driven browser control.

## July 2026 recommendation ledger

### Implemented

- `2026-07-zsh-safety`: Harden zsh shell guidance for reserved parameters,
  quoted GitHub API paths, and explicit Bash execution. Commit `afb70cb`.
- `2026-07-worktree-resolver`: Add a deterministic worktree resolver. Commit
  `1853340`.
- `2026-07-main-sync`: Automatically fast-forward a clean, strictly behind main
  worktree when staleness is observed. Commit `e3a32f3`.
- `2026-07-go-skill-routing`: Split `building-go-applications` into a small core
  with routed references and remove duplicated Temporal guidance. Commit
  `58ec413`.
- `2026-07-github-alerts`: Fold `formatting-github-alerts` into the PR-writing
  skills and retire the standalone skill. Commit `fdaa8ea`.
- `2026-07-notifications`: Remove `sending-notifications`. Commit `1b6dc9d`.
  This replaces the audit's recommendation to keep and revise it.
- `2026-07-onboard-entrypoint`: Add a stable noninteractive `onboard` entrypoint
  and remove the zsh function. Commit `9db8c6a`.
- `2026-07-safari-computer-use`: Record the Safari and Computer Use preference
  in global instructions. Commit `9ac7051`.
- `2026-07-temporal-links`: Repair nine broken language-to-core links in
  `developing-temporal-applications` after verifying upstream had not fixed
  them. Commit `205c3a1`.

### Accepted and open

- `2026-07-datadog-ci-visibility`: Add CI Visibility guidance to
  `managing-datadog` as an on-demand reference, initially with one narrow
  comparison script. Chad agreed that this was worth adding, but it had not been
  implemented when this ledger was created.

### Not discussed or not actioned

- `2026-07-platform-pr-review`: Add `reviewing-platform-pull-requests`.
- `2026-07-github-org-terraform`: Add `managing-github-organization-terraform`.
- `2026-07-terraform-pr-apply`: Add manual-only
  `applying-terraform-pull-requests`.
- `2026-07-long-task-phases`: Formalize long-task modes, phase-boundary
  handoffs, and decision inventories.
- `2026-07-codex-version-check`: Automate Codex version checks.
- `2026-07-local-diagnostics`: Add the proposed optional local diagnostics and
  benchmarking tools.

Lack of action is not evidence that these recommendations were unhelpful.
Compare them with later sessions and direct feedback before changing status.
