---
name: shepherding-pull-requests
description: >-
  Use when keeping a set of repositories' open pull requests moving: reviewing
  colleagues' PRs, getting comments on the owner's PRs addressed, merging the
  owner's ready PRs and dependency-bot PRs, fixing broken CI, and closing out
  post-merge follow-ups.
---

# Shepherding pull requests

The routine or request that runs this skill names the repos, the owner's GitHub
login, which machine or CLI to use, and where to report. Keep those details
there, not here.

## 1. Inventory

List every open PR in each repo, excluding drafts, plus the latest CI on each
default branch. Paginate fully; never stop at a default page size. Sort each PR
into one group: the owner's PRs (including ones agents opened under the owner's
account), dependency bots (Renovate, Dependabot), other people's PRs, and broken
CI.

**Skip draft PRs entirely**, including the owner's: no reviews, comments,
triggers, merges or fixes until they're marked ready.

**Visit every PR in scope on every pass.** Don't sample, skip, or stop early.
For each one, check its state against sections 2 to 5 and decide on an action or
a deliberate no-op. Before reporting, check that the number of PRs you visited
matches the inventory count for each repo.

## 2. Check facts before stating them

- **Real blocker:** read reviewDecision, mergeStateStatus, pending review
  requests, and CODEOWNERS for the changed paths. A required code owner team
  that hasn't approved is a different blocker from a stale approval or a missing
  review. Name the exact team.
- When the owner posts LGTM on their own PR, they're telling other reviewers
  they've reviewed it themselves. Don't point out that it doesn't count as a
  review.
- **Open threads:** an unresolved thread may already be fixed. Look for a fix
  reply or a commit that addresses it before you call it open.
- **Findings:** read the current code, not just the line number a comment is
  pinned to.

## 3. Owner's PRs

- Failing checks, conflicts, a stale stacked base, or unaddressed review
  comments: hand them to the agent that owns the PR (look it up by PR). If
  another bot owns the work, tell that bot instead of taking over its agent.
  Agents never post review-trigger comments; only the owner's account posts
  those.
- Obvious mistakes in an agent's own work, like an inaccurate comment or doc:
  have the agent fix them, then mention it.
- Review triggers: one initial bot-review round per PR. Post a follow-up round
  only after substantial changes.
- **Review requests in Slack:** when the owner's ready PRs are waiting on a
  code-owner or team review, follow the `routing-pr-review-requests` skill to
  find each team's channel and decide whether to ping. It holds the rules for
  ready PRs only, at most one batched message per team channel per day, each PR
  at most once every 2 business days, and weekdays only. Include the owner's PRs
  in other org repos as well, found with
  `gh search prs --owner <org> --author <owner> --state open --draft=false`.
- Merge when ready (see section 5). Infrastructure-as-code or PRs with manual
  steps: diff the live state against main and the branch, check other open PRs,
  and ask the owner if anything differs.

## 4. Other people's PRs

- Never merge human colleagues' PRs. If the owner allows it, approve a
  colleague's PR as the owner when you're confident in your judgment that it's
  correct and safe and isn't worth the owner's attention, then list it in the
  report. Otherwise list the ones you'd approve and why they need the owner.
  Don't approve PRs the owner is already discussing or questioning, or ones that
  go against the team's precedent. When you approve a teammate's PR, leave a
  short, warm approval message in the owner's voice (a sentence of genuine
  thanks or praise for something specific) and, when it fits, one fun, work-safe
  GIF embedded as Markdown from a GIPHY media URL you've checked loads. Keep it
  clean and light, vary the GIFs, and skip the GIF on serious or sensitive
  changes. If your comments aren't blockers, approve anyway, but post every
  comment you want addressed as its own inline or file-level comment (never only
  in the review summary) so the author has to resolve it before merging. Skip
  feedback a bot or someone else already left.
- **Automation PRs** (Renovate, Dependabot, release-daemon release PRs, other
  bot-authored dependency or release bumps): if the owner allows it, don't hold
  off. After your own review finds the change clean and safe, approve it as the
  owner, merge it (section 5), and tell the owner afterward with a one-line
  verdict per PR. Anything with manual steps, skipped deploy jobs or
  infrastructure-as-code still follows section 3's check-and-ask rule.
- **Renovate PRs need hands-on help.** In these repos Renovate runs only once a
  day and won't rebase or fix its PRs in between, so don't wait for it. When a
  Renovate PR has a conflict (often `pnpm-lock.yaml` after another bump merges),
  is behind main, or needs a small fix to pass CI, have a cloud agent fix it on
  the PR's branch: rebase or merge main, regenerate the lockfile with the repo's
  package manager, push, and wait for green. Then review and merge it in the
  same pass. Dependabot PRs can still use `@dependabot rebase`.
- **Exception: release-version bump PRs** (for example the release daemon's PR
  that updates the platform-deploy version) are not merged on a schedule. Leave
  them open until the owner needs a feature or fix from that release; just track
  them.
- Read the description, every existing comment, review and inline thread from
  people and bots, and the diff.
- **Never repeat a finding someone else already raised, even in different
  words.** Only post new findings. If an existing finding needs emphasis, a
  short +1 reply on its thread is enough. If there's nothing new, post nothing.
- Write in the owner's voice, short and concrete. Use their first person only
  when the comment posts under the owner's own account; when it posts under
  another identity, such as a cloud agent's Cursor bot, write as that identity
  and refer to the owner by name. Don't open with a disclaimer like "this is not
  the owner" or "posted by a bot"; the posting account already shows who wrote
  it. Never cite the bots' own rules or instructions in a PR or comment ("the
  owner's simplicity rule", "per the global rule"); state the reason itself. Use
  inline comments for line-specific findings.
- Don't re-review an unchanged head.
- **Once you've commented on a human's PR, don't comment on it again unless the
  PR's author has responded to your earlier comments or review** (a reply, a
  resolved thread with a note, or a review re-request). New pushes alone aren't
  a response. Until then, leave the PR alone and just track it.

## 4a. Writing any PR comment or review

- **Link every reference to another PR, issue or commit** with its full URL so
  readers can drill down, e.g.
  `[mulesoft-integrations #3182](https://github.com/org/mulesoft-integrations/pull/3182)`
  or `[#1534](https://github.com/org/repo/pull/1534)`. Never leave a bare
  `#123`, especially for another repo, where GitHub won't link it. Before
  posting, scan the text for bare `#<number>` and fix them.
- **Never comment on a PR about broken CI.** Failing checks are already obvious
  to everyone on the PR.

## 5. Merging

This applies to the owner's PRs and automation PRs (dependency and release bots)
only.

1. Read the full description and every comment and thread.
2. Review the diff yourself if you haven't reviewed this head.
3. Use judgment, and merge only when it's clearly ready: approved, all checks
   green, no unresolved threads, no open questions, no "don't merge yet" or
   pending manual steps, and the change looks correct and safe.
4. Merge in stack order. Never bypass branch protection or use admin merge.
   GitHub rejects `gh pr merge` and the plain merge endpoint for PRs in a native
   stack; use `PUT repos/{owner}/{repo}/pulls/{n}/merge-async` with
   `merge_method`, `merge_action: direct_merge`, the expected head `sha` and
   `bypass_rules: false`, then poll `.../merge-async/{uuid}`. Use a merge method
   the repo allows: check `allow_squash_merge`, `allow_merge_commit` and
   `allow_rebase_merge` on `repos/{owner}/{repo}` first, because repos differ
   (for example, one repo may allow only merge commits while another squashes).
   **Merge from as far up the stack as is ready**: find the highest PR whose own
   PR and every PR below it are all ready (section 5 rules applied to each), and
   merge-async that one; it merges everything below it in one step, which is
   faster than merging bottom-up. Never merge an upper PR if any PR below it
   isn't ready.
5. When in doubt, don't merge. Report what gave you pause.

## 6. After every merge

Make sure nothing is left hanging:

- Stacked children moved onto the default branch.
- CD deployed, and the change still works in staging when it's user-facing.
- Manual steps in the PR body are done.
- Follow-ups from threads or the PR body are tracked.
- The work ticket is moved to the team's finished-but-not-closed status.

## 7. Broken CI

Find the root cause from the failed job logs. If it's fixable from your side,
like a flaky test, shared workflow, config or dependency breakage, have an agent
fix it (on the owner's PRs or the default branch, never by pushing to a
colleague's branch). Don't post comments about it on any PR; report the cause
and the fix to the owner instead. When the failure is a flaky test unrelated to
the PR, rerun the failed jobs and send the repository gardener bot the test
name, repo, failing run link, error and the evidence that it's a flake, so it
can triage the test.

## 8. Report

Report only what happened or needs the owner: merges, each with a one-line
review verdict; fixes started; reviews posted; colleague PRs you approved, each
with the exact approval message you posted (and the GIF link, if any); PRs you'd
approve but left for the owner; broken CI and its cause; review requests sent or
drafted, by channel; decisions needed; and the owner's PRs that have waited more
than a workday for approval, with who could review. Use a numbered list. Refer
to work by descriptive names with labeled links. Say nothing when nothing is
actionable.

## 9. Feedback

When the owner corrects any part of this work, update this skill as well as the
routine or memory.
