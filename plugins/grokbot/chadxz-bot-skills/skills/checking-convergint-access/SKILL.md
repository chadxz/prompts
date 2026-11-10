---
name: checking-convergint-access
description: >-
  Use whenever Chad asks about a Convergint employee's access, onboarding,
  membership, seat, tier, or team for a company tool (Cursor, GitHub, Linear,
  Datadog, 1Password, ChatGPT, Claude, Tailscale, SendGrid), whether to check it
  or change it. The onboard CLI is the tool for these questions.
---

# Checking and changing Convergint employee access

Use the `onboard` CLI from ee-monorepo for every question about whether a
Convergint employee has access to a tool, what tier or team they're in, or
getting them added. Don't answer from memory, the vendor's web dashboard, or an
Entra group lookup when the CLI covers the tool. Those are fallbacks only when
the CLI has no command for what's asked.

## Where it runs

- It runs on Chad's Mac, where its credentials live, from the ee-monorepo main
  worktree at `~/src/convergint/ee-monorepo/main`.
- Run it with `mise //tools/onboard:run -- <tool> <command> ...`. That builds the
  binary first. The built binary is at `tools/onboard/dist/onboard`.
- If a command is missing or behaves oddly, fast-forward the main worktree and
  try again. The repo's shared git config has `core.bare=true`, so git there
  needs `GIT_DIR` set to `.../ee-monorepo/.git/worktrees/main` and
  `GIT_WORK_TREE` set to the worktree.
- Run `onboard --help` and `onboard <tool> --help` to see current commands.
  Don't assume a flag exists.

## Tools it covers

`1password`, `chatgpt`, `claude`, `cursor`, `datadog`, `github`, `linear`,
`sendgrid`, and `tailscale`. Most have:

- `status EMAIL...` to show whether someone is onboarded and at what tier.
- `list-members` (or `list-teams`, `list-roles`) to see who's in a group.
- `add-users EMAIL...` to add someone.
- `set-tier TIER EMAIL` for tools with spend tiers (Cursor, ChatGPT).

## Reading versus changing

- Status and list commands are read-only. Run them whenever asked, without
  asking first.
- Commands that add, remove, or change access (`add-users`, `set-tier`,
  `add-role`, `remove-role`, `set-access`, `remove-users-from-team`, GitHub
  onboarding) change real access. Run them only when Chad asked for that change
  for that person, and confirm the exact email and tier or team if anything is
  unclear.
- GitHub onboarding opens a Terraform pull request. Access lands only after that
  PR merges and `mise //infrastructure/github:apply` runs.
- Use the person's Convergint email (usually `first.last@convergint.com`). If
  you had to guess it and status reports the user isn't found, say so rather
  than reporting that they lack access.

## Reporting back

Lead with the yes or no, then the status, tier, or team the CLI returned, and
any warnings or errors it printed.
