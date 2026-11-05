---
name: cloud-agent-brief-checklist
description: >-
  Use whenever you (one of Chad's bots) write a brief for a Cursor cloud agent,
  including delegated code reviews. Lists what every brief must carry before
  you launch the agent.
---

# Cloud agent brief checklist

Check the brief against every item before you launch the agent. A missing item
means the agent will guess, and its guess shows up under Chad's name.

1. **Ticket first.** Open or find the Linear ticket before you write the brief
   (see `tracking-bot-work-in-linear`). Put the ticket ID in the brief and tell
   the agent to reference it in the PR title or body. Name the `bot:<label>` PR
   label to apply.
2. **Babysit the PR.** Tell the agent to keep watching CI and review comments
   after it opens the PR, and to fix what comes up until the PR is ready to
   merge. It never merges.
3. **Merge conflicts.** Tell the agent to resolve merge conflicts itself without
   asking.
4. **Stacked work.** When the work spans several PRs, tell the agent to use
   GitHub's native stacked PRs (`gh stack`), not hand-chained bases.
5. **Who it posts as.** The PR title, body, and commits show up under Chad's
   GitHub account (chadxz), so they're in Chad's first person. Comments the
   agent posts under its own Cursor bot identity are written as itself. Any
   GitHub comment posted as chadxz ends with a hidden `<!-- bot:<label> -->`
   marker on its own last line. No bot disclaimers, and no citing the bots' own
   rules.
6. **Docs go to Notion.** Tell the agent that user and team documentation goes
   to Notion, not Git.
7. **Check the live target.** Tell the agent to check the live state it's about
   to change (the deployed config, the current PR, the real API response) before
   acting, not just the repo or the brief.
8. **Carry review rules.** When the brief delegates a review, copy the caller's
   review rules into it: what to check, what not to repeat, where to post, and
   whose voice to use.
9. **ADR PRs.** When the work is an ADR or documents a major feature or
   architectural decision, tell the agent the PR must contain only the ADR, with
   no implementation bundled in, and must carry the `requires-review-by-chad`
   label. It never merges that PR; babysitting stops once the PR is ready for
   Chad's LGTM.
