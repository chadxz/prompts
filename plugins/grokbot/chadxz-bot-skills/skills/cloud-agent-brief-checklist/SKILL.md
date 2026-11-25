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

1. **Existing work first.** Before you open a PR or launch a cloud agent, check
   for an open PR or running cloud agent on the same file or question. If one
   exists, hand the work to it or coordinate instead of starting a second one.
2. **Ticket first.** Open or find the Linear ticket before you write the brief
   (see `tracking-bot-work-in-linear`). Put the ticket ID in the brief and tell
   the agent to reference it in the PR title or body. Give it the exact
   `<!-- opened-by-bot: <name> -->` line to put on its own line in the PR body,
   which is how you'll tell later that you opened the PR, and name the
   `bot:<name>` PR label to apply when the repo allows it.
3. **Babysit the PR, then report back.** Tell the agent to keep watching CI
   and review comments after it opens the PR, and to fix what comes up until
   the PR is ready to merge: approved, checks green, no merge conflicts, and
   no unresolved review comments. It never merges. As soon as the PR is ready,
   the agent ends its run with a final report that says the PR is ready to
   merge and links it. Ending the run is what wakes the bot that launched it,
   so the bot can merge and take care of follow-up work right away. Tell the
   agent not to keep polling an already-ready PR, and not to end its run early
   while the PR still needs work. Tell it never to ask people or teams for
   review, in Slack or by @-mentioning them on the PR. If the PR needs a team's
   review, you hand it to Doc Brown (see `routing-pr-review-requests`), except
   in convergint/ee-monorepo and convergint/platform-examples, where the PR
   notifier posts it and no request is needed.
4. **Merge conflicts.** Tell the agent to resolve merge conflicts itself without
   asking.
5. **Stacked work.** When the work spans several PRs, tell the agent to use
   GitHub's native stacked PRs (`gh stack`), not hand-chained bases. This
   includes an ADR PR and the implementation that depends on it: the ADR goes at
   the bottom of the stack.
6. **Who it posts as.** The PR title, body, and commits show up under Chad's
   GitHub account (chadxz), so they're in Chad's first person. Comments the
   agent posts under its own Cursor bot identity are written as itself. Any
   GitHub comment posted as chadxz ends with a hidden `<!-- bot:<label> -->`
   marker on its own last line. No bot disclaimers, and no citing the bots' own
   rules. Cloud agents can't post as chadxz: their GitHub token belongs to the
   Cursor app and only covers the launch repo, and Linear's review tools strip
   HTML comments and re-host images. For reviews or comments that must appear as
   chadxz, have the agent return the text (item 9) and post it yourself with
   your own `gh`. Never let an agent test which account a tool posts as on a
   live PR.
7. **Docs go to Notion.** Tell the agent that user and team documentation goes
   to Notion, not Git.
8. **Check the live target.** Tell the agent to check the live state it's about
   to change (the deployed config, the current PR, the real API response) before
   acting, not just the repo or the brief.
9. **Carry review rules.** When the brief delegates a review, copy the caller's
   review rules into it: what to check, what not to repeat, where to post, and
   whose voice to use. Tell the agent not to post anything to GitHub, to Linear,
   or through its PR tool. For each PR, it ends its run with a JSON review
   payload:

   ```json
   {
     "repo": "<owner>/<repo>",
     "number": 123,
     "commit_id": "<head commit SHA>",
     "event": "APPROVE|REQUEST_CHANGES|COMMENT",
     "body": "<review summary>",
     "comments": [
       {
         "path": "<file path>",
         "line": 42,
         "start_line": 40,
         "side": "RIGHT",
         "body": "<inline comment>"
       }
     ]
   }
   ```

   `start_line` is optional; include it only for a comment that spans several
   lines. Every `body` is final Markdown that ends with the
   `<!-- bot:<label> -->` marker, and any GIF is a GIPHY media URL the agent
   checked returns 200. You then post the payload with your own `gh`:
   `gh api repos/<owner>/<repo>/pulls/<n>/reviews --input payload.json`.

   Include the approval rule in every review brief: when each problem is spelled
   out in an inline or file-level review comment the author can fix and resolve,
   set `event` to `APPROVE` instead of `REQUEST_CHANGES`, since resolving those
   threads under the repo's conversation-resolution requirement gates the merge
   without making the author wait on another review. **Any change expected
   before merge MUST be posted in `comments` as an inline or file-level review
   comment**, because GitHub's conversation-resolution rule only requires those
   to be resolved. Never put a required change only in the approval `body` or a
   top-level PR comment, since the author can miss it and merge without
   addressing it. The review summary may point to the inline comments, but it
   must never be the only place a required fix appears. Blocking
   (`REQUEST_CHANGES` or withholding approval) is only for real safety, security
   or correctness problems, or design disagreements the author needs to discuss;
   a broken CI check with an obvious fix, such as a stale `CODEOWNERS` line,
   isn't one of those, and non-blocking design feedback never holds an approval.
10. **ADR PRs.** When the work is an ADR, or needs one (a major feature, an
    architectural decision, or a change the repo's review policy would tag
    Design), tell the agent to write the ADR first and stack any implementation
    PR on it with `gh stack`. The ADR PR must contain only the ADR, with no
    implementation bundled in, and must carry the `requires-review-by-chad`
    label. The ADR has no decided-by, approved-by, or deciders line and credits
    no person or team with the decision. Its status line is just the status
    ("Status: Accepted"), with no repeated date or attribution. The agent never
    merges that PR; babysitting stops once the PR is ready for Chad's LGTM.
    Editorial fixes that don't change an ADR's meaning or decision (typos,
    casing, formatting, broken links) skip the label and need only the usual
    Engineering Enablement approval.
11. **Model for deep work.** When the work is architecture, design, an ADR, a
    complex feature, or deep problem solving (an investigation, a root cause,
    hard debugging), launch the agent with `claude-fable-5-2` and
    `model_params.effort: medium`.
12. **Steps outside the repo are yours.** A cloud agent can't reach Chad's Mac
    or vendor consoles. Before launching, list any console or live setup step
    the work needs, plan to do it yourself (see
    `using-codex-for-mac-browser-work`), and do it before the agent finishes if
    you can, so the PR ships with real values. If the agent must use
    placeholders, tell it to name each one in its final report, not to call
    them a manual or human step, and not to leave a review thread saying so.
    Then fill them in yourself.
