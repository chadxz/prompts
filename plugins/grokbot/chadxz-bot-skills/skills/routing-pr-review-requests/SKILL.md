---
name: routing-pr-review-requests
description: >-
  Use when a pull request needs a Convergint GitHub team's review: handing the
  request to Doc Brown, the review coordinator, and, for Doc Brown, finding
  which team owns a repo or path, which Slack channel to ping, and when a PR
  pass may send review requests.
---

# Routing PR review requests to Slack

Use this map to send a PR's review request to the Slack channel of the team that
owns it. It covers the convergint GitHub org and the convergint-techteam Slack
workspace. Chad confirmed it on Oct 27, 2026. The research behind it is in
`/workspace/doc-brown/codeowner-slack-map-org.md` on the shared box.

## Doc Brown sends every review request

Doc Brown is the review coordinator. It's the only bot that posts review
requests to humans, in Slack channels or DMs, and the only one that @-mentions
people or teams on a PR to ask for review. One sender can dedupe the requests,
so a team gets one batch a day and a PR isn't pinged twice.

Every other bot that needs a review on a PR hands it to Doc Brown with
SendToAgent, using priority: true. Give the PR URL, the owning team if you know
it (section 1), whether it's urgent and why, and anything reviewers should know.
Then stop: don't post the request yourself. Doc Brown tells you when it goes
out.

An ADR's LGTM ask to Chad isn't a team review request, so it keeps its own path.

## 1. Find the owning team

1. **CODEOWNERS first.** Read `.github/CODEOWNERS` (also `CODEOWNERS` and
   `docs/CODEOWNERS`) on the default branch. Match the PR's changed files,
   remembering that the last matching rule wins. When a PR touches paths owned
   by several teams, every team that hasn't approved yet is a target. Skip teams
   that already approved.
2. **No CODEOWNERS, or a path it doesn't cover:** use the teams with write or
   admin access to the repo (`gh api repos/{owner}/{repo}/teams`). The PR's
   pending team review requests (`reviewRequests`) also count.
3. Engineering Enablement has admin access on every repo, so count it only where
   CODEOWNERS names it.
4. **Permission groups are never pinged:** isuite-repo-admins,
   isuite-deployment-approvers and all-engineering. For those repos, use the
   real owning team instead.

## 2. Team to channel

| GitHub team(s)                                                                                                                                                                                                            | Slack channel                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| engineering-enablement                                                                                                                                                                                                    | #team-eng-enablement-internal (C08MGCF1FHN) |
| bizops-enablement, mulesoft-integration-leads, mulesoft-integration-contributors, salesforce-integration-leads, salesforce-integration-contributors, marketing-salesforce-contributors, oracle-leads, oracle-contributors | #team-bizops-enablement (C07GJ7PFKEJ)       |
| gamma, profisee-contributors                                                                                                                                                                                              | #team-gamma (C07SZ8YTSBZ)                   |
| alpha, qa-automation                                                                                                                                                                                                      | #team-alpha (C07T4J8CQ7L)                   |
| customer-portal-developers, ce-reviewers                                                                                                                                                                                  | #team-tech-enabled-services (C07GQS4J4D8)   |
| idesign, idesign-approvers                                                                                                                                                                                                | #team-idesign (C09207KJEKC)                 |
| infrastructure                                                                                                                                                                                                            | #team-infrastructure (C07GXTS5YP8)          |
| internal-tools, one, vertex, ctc-financials                                                                                                                                                                               | #team-internal-tools (C0AQHKE74MT)          |
| data-engineering, data-analytics, data-analytics-pipeline                                                                                                                                                                 | #team-data (C07G8F0GZDE)                    |
| security                                                                                                                                                                                                                  | #team-security (C07RMDCQBJQ)                |
| help-desk                                                                                                                                                                                                                 | #colleague-support (C07UDU866BB)            |

- Don't use outward-facing support channels for a team's own PRs, such as
  #team-eng-enablement, which is EE's help channel. Don't use the "-internal"
  variants of alpha or iDesign either, or GitHub activity feed channels like
  #team-*-github.
- When a past ping went somewhere else, go by the GitHub ownership.
- **A repo with no owning team, or a team not in this table:** don't ping. List
  it in the report so the map can be extended. When a new team shows up, add it
  here after the owner confirms its channel.

## 3. When a PR pass may ping

These rules are Doc Brown's. They cover its own PR passes and every PR another
bot hands it.

1. Only the owner's own ready PRs (not drafts) that are still waiting on a
   code-owner or team review.
2. Never automation PRs (Renovate, Dependabot, release daemon).
3. Leave out PRs that aren't really ready for eyes: unaddressed review findings,
   an agent fix still in progress, an open question from the owner on the PR, or
   a change another bot is still making.
4. Send at most one batched review-request message per team channel per day, as
   the owner, in their voice. Fold the day's handoffs into that batch, and list
   a PR once even when several bots handed it over. There is no template: write
   it freeform and naturally, varying the wording each time. Just make sure each
   PR appears as a labeled link with its title, and never use "fam".
5. Before posting, search the channel for a review request from the owner
   earlier today (their own manual pings count). If there is one, hold the rest
   until the next weekday. Ping a PR at most once every 2 business days, so also
   search the channel for the PR's URL first.
6. Weekdays only. Never message humans on weekends.
7. Every message goes out under the owner's name, so follow the drafting and
   sending rules in your instructions. Record what you sent, so the next pass
   can respect rule 5, and tell each bot that handed you a PR when its request
   went out.

## 4. Keeping the map current

When the owner corrects a mapping, update this skill. To re-check it, re-run the
research method in section 1 across the org and compare. The owner's own past
bulk review requests in Slack are the best evidence of which channel a team
really uses.
