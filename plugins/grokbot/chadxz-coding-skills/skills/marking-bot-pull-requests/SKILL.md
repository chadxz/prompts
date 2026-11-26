---
name: marking-bot-pull-requests
description: >-
  Use whenever you open or work on a GitHub pull request for Chad, whether
  you're one of Chad's bots or a Cursor cloud agent working on Chad's behalf
  through one, so the PR carries the bot marker and `bot:` label and links its
  Linear ticket.
---

# Marking bot pull requests

Every GitHub pull request a bot opens, or has a cloud agent open, for Chad
carries an HTML comment in its body naming that bot, on its own line, in exactly
this form:

```markdown
<!-- opened-by-bot: <name> -->
```

That comment is how a bot tells whether it opened a PR. Decide ownership from
it, not from labels. The PR shows Chad as the author, the same way Linear does.

If you're a cloud agent working on Chad's behalf, `<name>` is the bot you're
working through, the one your brief names, not yourself.

- Use the bot's name in lowercase with hyphens for spaces: `cully`,
  `doc-brown`, `samwise`, `soxy`, `coach-lasso`, `kaizen`, `scotty`, `marty`,
  or `mrs-frizzle`. Mr. Miyagi uses `kaizen` and Ms. Frizzle uses
  `mrs-frizzle`, matching their labels.
- Also add a `bot:` label with the same name, such as `bot:marty`, when the
  repository allows it, so people can see at a glance which bot did the work.
  It's for humans. Bots don't decide ownership from it.
- Link the PR to its Linear ticket by referencing the ticket ID in the PR title
  or body. A cloud agent uses the ticket from its brief. Work in
  `chadxz/prompts` never has a ticket.
- Don't merge a PR you didn't open unless you're specifically asked to. Chad's
  standing asks count, such as the one that lets any bot merge release-version
  bump PRs (see `shepherding-pull-requests`). A cloud agent never merges.
- Add the label when the PR is created, or right after with
  `gh pr edit <url> --add-label bot:<name>`. If you pick up an existing PR, add
  your label next to any that are already on it, and leave its marker alone.
- If the repository doesn't have the label yet, adding it to the PR through
  GitHub's add-labels API (a cloud agent's PR label tool does this) creates it
  on the fly, and that's fine. It doesn't need a description. Don't stop and ask
  about a missing label. If the repository won't take the label at all, the
  marker is enough.
- ADR and architecture-decision PRs also get the `requires-review-by-chad`
  label. Don't treat those PRs as ready to merge until Chad posts LGTM.
  Editorial fixes that don't change an ADR's meaning or decision (typos,
  casing, formatting, broken links) skip the label and need only the usual
  Engineering Enablement approval.
