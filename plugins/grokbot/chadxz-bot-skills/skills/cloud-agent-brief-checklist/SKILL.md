---
name: cloud-agent-brief-checklist
description: >-
  Use whenever you (one of Chad's bots) write a brief for a Cursor cloud agent
  or Project, including delegated code reviews. Lists what every brief carries
  and what to leave out before you launch the agent.
---

# Cloud agent brief checklist

Cloud agents and Projects run strong models. Treat them as trusted
collaborators, not script runners: share the context, the goal, and any design
that's already decided, then let them work out how to solve it. Your job is to
check, support, and review the work, not to dictate each step.

The agent already has a lot. It loads skills by their descriptions, so it'll
pick up `chadxz-coding-skills` (commits, PRs, bot PR markers, writing in Chad's
voice, RFCs, docs, Notion) once it knows it's working for one of Chad's bots.
It reads the repository's root `AGENTS.md`. It has its own Linear, Slack,
Notion, Datadog, and GitHub tools, so it can fetch records itself.

## Before you write it

1. **Existing work first.** Check for an open PR or running cloud agent on the
   same file or question. If one exists, hand the work to it or coordinate
   instead of starting a second one.
2. **Ticket first.** Open or find the Linear ticket before you write the brief
   (see `tracking-bot-work-in-linear`). Work in `chadxz/prompts` never gets a
   ticket.
3. **Steps outside the repo are yours.** A cloud agent can't reach Chad's Mac
   or vendor consoles. List any console or live setup step the work needs and
   do it yourself (see `using-codex-for-mac-browser-work`), before the agent
   finishes if you can, so the PR ships with real values. If the agent must use
   placeholders, tell it to name each one in its final report, not to call them
   a manual or human step, and not to leave a review thread saying so.

## What every brief carries

1. **The goal.** What the work is and why it matters, what done looks like, and
   what's out of scope. Include any design that's already decided so the agent
   doesn't reopen it.
2. **Who it works for.** "You're working for <bot>, one of Chad's bots." That
   line is what tells the agent the coding skills apply to it. Don't list skill
   names. It may also see the bot and personal plugins' skills; those are
   yours, not its.
3. **The ticket, label, and marker.** The Linear ticket ID to reference in the
   PR, the exact `<!-- opened-by-bot: <name> -->` line for the PR body, and the
   `bot:<name>` label (see `marking-bot-pull-requests`). Add
   `requires-review-by-chad` for ADR PRs.
4. **Where side effects stop.** Say whether it's code and the PR only, or also
   Linear comments, Slack, or live services. By default it stays inside the
   repository.
5. **Pointers, not dumps.** Links and IDs for the ticket, threads, docs,
   dashboards, and PRs, which it fetches with its own tools. Name the app paths
   involved, so it opens their nested `AGENTS.md` files, which aren't loaded
   automatically. Tell it to check the live state it's changing (deployed
   config, real API response), not just the repo.
6. **Hard limits.**
   - Never merge with `--admin` or bypass branch protections or checks.
   - No secrets or tokens in output, commits, PRs, or comments.
   - Write as itself or the bot it works for, never as Chad, except the PR
     title, body, and commits, which appear under chadxz and use Chad's first
     person. Any GitHub comment posted as chadxz ends with a hidden
     `<!-- bot:<label> -->` marker on its own last line.
   - Never run `terraform apply` or other live writes unless the brief says so.
7. **Babysit the PR, then report back.** It watches CI and review comments and
   fixes what comes up, including merge conflicts, until the PR is ready to
   merge: approved, checks green, no conflicts, no unresolved comments. It never
   merges. As soon as the PR is ready, it ends its run with a final report that
   links the PR. Ending the run is what wakes you, so it shouldn't keep polling
   a ready PR or stop early while the PR still needs work. It never asks people
   or teams for review. If a team's review is needed, you hand it to Doc Brown
   (see `routing-pr-review-requests`), except in convergint/ee-monorepo and
   convergint/platform-examples, where the PR notifier posts it.

Add these when they apply:

- **Stacked work.** Several PRs use GitHub's native stacked PRs (`gh stack`),
  with an ADR at the bottom. An ADR PR holds only the ADR, and the agent stops
  babysitting once it's ready for Chad's LGTM.
- **Docs.** User and team documentation goes to Notion, not Git.
- **Model for deep work.** For architecture, design, an ADR, a complex
  feature, or deep problem solving, launch with `claude-fable-5-2` and
  `model_params.effort: medium`.
- **Delegated reviews.** See below.

## What to leave out

- Anything already in the repository's root `AGENTS.md` or `CONTRIBUTING.md`.
- Standard git, testing, and code hygiene.
- Pasted copies of tickets, threads, docs, or skill text. Link them instead.
- Step-by-step instructions for problems the agent can solve itself.

Keep the brief short. If it runs long, it's probably carrying dumps.

## Delegated reviews

Cloud agents can't post as chadxz: their GitHub token belongs to the Cursor app
and only covers the launch repository, and Linear's review tools strip HTML
comments and re-host images. So a review brief tells the agent what to check,
what not to repeat, and whose voice to use, and tells it not to post anything
to GitHub, Linear, or through its PR tool. Never let an agent test which
account a tool posts as on a live PR. For each PR, it ends its run with a JSON
review payload:

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
lines. Every `body` is final Markdown that ends with the `<!-- bot:<label> -->`
marker, and any GIF is a GIPHY media URL the agent checked returns 200. You
post the payload with your own `gh`:
`gh api repos/<owner>/<repo>/pulls/<n>/reviews --input payload.json`.

Include the approval rule in every review brief: when each problem is spelled
out in an inline or file-level review comment the author can fix and resolve,
set `event` to `APPROVE` instead of `REQUEST_CHANGES`, since the repo's
conversation-resolution requirement gates the merge on those threads. **Any
change expected before merge MUST be posted in `comments` as an inline or
file-level review comment**, never only in the approval `body` or a top-level
PR comment, since the author can miss it there. Blocking (`REQUEST_CHANGES` or
withholding approval) is only for real safety, security, or correctness
problems, or design disagreements the author needs to discuss. A broken CI
check with an obvious fix, such as a stale `CODEOWNERS` line, isn't one of
those, and non-blocking design feedback never holds an approval.
