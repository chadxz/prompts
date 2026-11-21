---
name: tracking-bot-work-in-linear
description: >-
  Use whenever you (one of Chad's bots) are about to start, hand off, pause, or
  finish a piece of work for Chad that lasts beyond the current reply, so it is
  tracked as a Linear ticket on the Engineering Enablement (EE) board. Also use
  when you want a ticket for work for later (send it to Marty), or when you open
  or work on a GitHub pull request for Chad, so the PR carries your bot label
  and links its ticket.
---

# Tracking bot work in Linear

Live since Oct 26, 2026. Chad approved it. We'll adjust it over time.

Chad's bots track the work they do for him on the Engineering Enablement (EE)
Linear team, the same board his human teammates use, so the team can see Chad's
work there.

## When to open a ticket

Open one when you are about to do any of these:

- Start work that keeps going after your current reply: background research, a
  cloud agent run, a long investigation, or a draft or Page you'll iterate on.
- Open a PR, or produce a draft that someone has to review.
- End a turn with the work unfinished.
- Wait on Chad or anyone else before you can continue.
- Work on follow-ups from a recurring job (a weekly review, a garden pass) right
  away. Use one ticket for that run's follow-ups. Follow-ups nobody plans to
  start soon go to Marty (see below). A run that produced nothing gets no
  ticket.

Don't open one for:

- Quick answers or lookups you finish in the same turn.
- Routine runs that end with nothing to do.
- Work that's already tracked on an existing ticket. Comment on that ticket
  instead.
- Work for later, meaning work nobody plans to start soon. Send it to Marty
  instead.
- Work in the `chadxz/prompts` repository, including its PRs. It's Chad's
  personal repo, not work, so it never gets a Linear ticket, and its PRs don't
  need one linked. Don't send it to Marty either.

**Ticket first.** Open or find the ticket before you brief a cloud agent or open
a PR, never after. Put the ticket ID in the brief and tell the agent to
reference it in the PR title or body, so the PR links to the ticket.

Before you create a ticket, search the EE team for an open one that already
covers the work, so you don't make duplicates.

## Work for later goes to Marty

When you want a ticket for work nobody plans to start soon, don't create it
yourself. Send the details to Marty, the EE backlog bot (agent id
c55f687f-6f56-465a-b270-de34b0f2bd8b): title, description, context and links,
and which bot asked for it. Marty creates the ticket, attributes it to the
requesting bot with a "Filed by <bot>." line at the end of the description
(not the bot's label), leaves it unassigned, and creates it in the Triage
status. Tickets for work you're starting right away you still create yourself.

Work you'll start as soon as a blocker clears isn't later work, even if you
can't start it this turn. An investigation waiting only on Chad's Mac coming
back online is one example. Create that ticket yourself in Todo, assigned to
Chad with your bot label.

Any ticket created for work nobody is actioning soon goes in Triage, no matter
who creates it. Never create later work straight into Todo, Backlog, or In
Progress. The team pulls it out of Triage when it decides to take it on.

## How to fill it in

- Team: EE (Engineering Enablement).
- Assignee: Chad McElligott, set when a bot starts the ticket (moves it to In
  Progress) or queues it in Todo to start as soon as a blocker clears, including
  tickets created for that work. The work is his, even when a bot is doing it.
  Tickets filed for later stay unassigned.
- Labels: when you start or queue the ticket, add your own name from the `bot`
  label group (Cully, Doc Brown, Samwise, Soxy, Coach Lasso, Kaizen, Scotty,
  Marty, Mrs. Frizzle, or Scooby). Tickets filed for later get no bot label,
  since a label reads like an assignment. Add `waiting-on-chad` only under the
  rules in "The waiting-on-chad label" below.
- Title: a plain description of the outcome, not the task chatter.
- Description:
  - What the work is and why.
  - What done looks like.
  - A link back to where it started: the Slack thread, the chat, or the PR.
  - Which bot filed it, as one last line: "Filed by Kaizen during a repo
    garden run."

## Moving it along

Use the EE team's existing statuses only, and never Backlog. A ticket that
isn't decided or scheduled goes in Triage, and one that's ready to work goes in
Todo. If you find a bot's ticket in Backlog, move it to Triage or Todo with a
comment saying why.

- Triage: new tickets for work nobody plans to start soon, unlabeled and
  unassigned, waiting for the team to decide when to take them on.
- Todo: not started yet, unlabeled and unassigned. The exception is your own
  ticket queued to start as soon as a blocker clears, which carries your bot
  label and has Chad assigned. If you move a ticket back to Todo unfinished and
  you're no longer planning to pick it up, remove your bot label and unassign
  Chad.
- In Progress: you're actively working on it.
- In Review: there's a PR or draft waiting for someone to review it, and no
  other step on the ticket is still open.
- Ready to Close: you're finished. Never move a ticket to Done or close it
  yourself unless Chad explicitly asks. The team reviews and closes Ready to
  Close tickets together at Monday morning planning, so Chad doesn't close them
  himself. Don't list them as waiting on Chad or remind him to close them.
- Canceled: only when Chad drops the work.

**Every status change gets a comment.** Whenever you change a ticket's status,
post a comment on the ticket in the same step that says why it changed, so
anyone looking back later can see the reason. That covers every move: Triage or
Todo to In Progress, In Progress to In Review, any move to Ready to Close, back
to Todo, and Canceled. It also covers adding or removing `waiting-on-chad`. A
status change with no comment is incomplete. If you notice you skipped one, post
it right away.

The comment says what happened: the work you started, the PR that opened, the
merge plus the live check that passed, the blocker that cleared, the question
you're now blocked on, or why the work was dropped. Link the PR, deploy, run, or
thread when there is one. Write it as Chad (see "Writing as Chad" below).

"Chad told me to", "as Chad asked", "per Chad", or anything else that only
points to an instruction is never the reason. State what actually changed:

- Good: "Moving this to Ready to Close. The fix merged in <PR link>, deployed to
  prod, and the nightly sync has run clean twice since."
- Bad: "Moving this to Ready to Close per Chad."
- Good: "Canceling this. The new pipeline in <PR link> replaced the old sync
  job, so there's nothing left to fix."
- Bad: "Canceling this as Chad asked."

Move the ticket to In Review as soon as its PRs open, and to Ready to Close
after merge plus live verification, without waiting to be asked, unless a step
on it is still open (see below). These automatic moves need the comment too:
name the PRs that opened, or the merge and the live check that passed. If a PR
needs a team's review, hand it to Doc Brown rather than asking for review
yourself (see `routing-pr-review-requests`).

Start that live check in the same turn as the merge, or brief an agent to follow
the post-merge deploy or apply. PR watch subscriptions close on merge, so a PR
watcher is not a follow-up. If the check can't finish in that turn, leave a
ticket comment that names the exact remaining check and when the next run will
do it. For 'errors haven't come back' work, move the ticket to Ready to Close
once the deploy is live and the error hasn't recurred since, and don't leave it
In Review waiting for a longer quiet period unless the ticket says so. Each run,
owning bots' hourly or backlog routines re-check every In Review ticket of
theirs whose PRs have merged, and move it to Ready to Close when the check has
passed, with a comment that names the merge and the check.

**Open steps block status moves.** Don't move a ticket to In Review or Ready to
Close while any step on it is still open, including a manual post-merge step
like an apply, a migration, or deleting leftover state. Finish the step
yourself, especially a small one, rather than splitting it into a new ticket, so
closing tickets doesn't leave a trail of new ones behind. Split a step out only
when you truly can't do it, such as when it needs access you don't have, and
link the new ticket from the original.

When the plan changes without a status change, add a short comment with a link
too, rather than rewriting the description.

## Labeling pull requests

Every GitHub pull request a bot opens or takes over for Chad carries a label
naming that bot, so anyone can see which bot did the work. The PR shows Chad as
the author, the same way Linear does.

- Use `bot:` plus your name in lowercase with hyphens for spaces: `bot:cully`,
  `bot:doc-brown`, `bot:samwise`, `bot:soxy`, `bot:coach-lasso`, `bot:kaizen`,
  `bot:scotty`, `bot:marty`, `bot:mrs-frizzle`, or `bot:scooby`.
- Before you open a PR or launch the cloud agent that will (except in
  `chadxz/prompts`, which never gets a ticket), check the PR has a ticket (see
  "Ticket first" above). If it doesn't, create or find the ticket first.
- This covers PRs opened by a cloud agent you launch. Put the label requirement
  in the cloud agent's instructions, and check the live PR afterward.
- Add the label when the PR is created, or right after with
  `gh pr edit <url> --add-label bot:<name>`. If you pick up an existing PR, add
  your label next to any that are already on it.
- If the repository doesn't have the label yet, adding it to the PR through
  GitHub's add-labels API (a cloud agent's PR label tool does this) creates it
  on the fly, and that's fine. It doesn't need a description. Don't stop and ask
  about a missing label.
- ADR and architecture-decision PRs also get the `requires-review-by-chad`
  label. Put that requirement in the cloud agent's brief. Don't treat those PRs
  as ready to merge from your side until Chad posts LGTM. Editorial fixes that
  don't change an ADR's meaning or decision (typos, casing, formatting, broken
  links) skip the label and need only the usual Engineering Enablement approval.
- When a cloud agent opens a PR for you, always tell it in its brief to babysit
  its pull request after opening it: keep watching CI and review comments and
  fix what comes up until the PR is ready to merge. Also tell it that the PR
  title, body, and commits show up under Chad's GitHub account, so it writes
  them in Chad's first person and never names Chad in the third person; review
  comments it posts under its own Cursor bot identity are written as itself and
  refer to Chad by name. It never opens a post with a disclaimer like "this is
  not Chad" or "posted by a bot", and never cites the bots' rules or
  instructions ("Chad's simplicity rule", "per the global rule"); it states the
  reason itself.

## Writing as Chad

The Linear connector posts as Chad, so every comment, description, and title you
write shows up under his name. Write in Chad's first person ("I looked into
this"). Never sign it or introduce yourself as a bot ("Scotty here"), and never
refer to Chad in the third person. The bot label on the ticket already shows
which bot did the work. The one exception is the single "Filed by <bot>." line
in a ticket's description. Never cite the bots' own rules or instructions in
anything outside the bots' chats ("Chad's simplicity rule", "per the global
rule", "as Chad asked"); state the reason itself, such as "I kept this to the
smallest change that works."

## The waiting-on-chad label

The label means you can't make progress until Chad answers a question or makes a
decision. In Review already says the next step is a review, and Ready to Close
waits for the team's Monday review, so the label would only repeat the status
there.

- Add it only to Todo or In Progress tickets that are blocked on a question or
  decision from Chad.
- Never put it on In Review or Ready to Close tickets. Remove it whenever you
  move a ticket into either status.
- Remove it as soon as Chad answers.
- Adding or removing it gets a comment like any status change (see "Moving it
  along"): the question you're blocked on, or the answer that unblocked you.
  When you remove it as part of a status move, one comment covers both.

## Work-in-progress limit

Keep at most 3 of your own tickets in In Progress at once. If you're at the
limit, finish, hand off, or pause one before you start another. If something
truly urgent can't wait, say so in the new ticket.

## If you can't reach Linear

If you don't have a working Linear connector, send the ticket details to Cully,
Chad's executive assistant bot (id 05c7f039-309c-47a2-8156-1a26a46018b6), and
Cully will open the ticket for you. Tickets for later work still go to Marty.
