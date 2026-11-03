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
  away. Use one ticket for that run's follow-ups. Follow-ups you won't work on
  now go to Marty (see below). A run that produced nothing gets no ticket.

Don't open one for:

- Quick answers or lookups you finish in the same turn.
- Routine runs that end with nothing to do.
- Work that's already tracked on an existing ticket. Comment on that ticket
  instead.
- Work for later, meaning work you aren't starting right now. Send it to Marty
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

When you want a ticket for work you aren't planning to do right now, don't
create it yourself. Send the details to Marty, the EE backlog bot (agent id
c55f687f-6f56-465a-b270-de34b0f2bd8b): title, description, context and links,
and which bot asked for it. Marty creates the ticket, attributes it to the
requesting bot with that bot's label, ranks it against the rest of the EE Todo
work, and drags it into the right place in the list. Tickets for work you're
starting right away you still create yourself.

## How to fill it in

- Team: EE (Engineering Enablement).
- Assignee: Chad McElligott. The work is his, even when a bot is doing it.
- Labels: pick your own name from the `bot` label group (Cully, Doc Brown,
  Samwise, Soxy, Coach Lasso, Kaizen, Scotty, Marty, Mrs. Frizzle, or Scooby).
  Add `waiting-on-chad` only under the rules in "The waiting-on-chad label"
  below.
- Title: a plain description of the outcome, not the task chatter.
- Description:
  - What the work is and why.
  - What done looks like.
  - A link back to where it started: the Slack thread, the chat, or the PR.
  - Which bot owns it.

## Moving it along

Use the EE team's existing statuses only:

- Todo: you've picked it up, but haven't started yet. Tickets for later work
  come from Marty, who places them in the Todo list.
- In Progress: you're actively working on it.
- In Review: there's a PR or draft waiting for someone to review it.
- Ready to Close: you're finished. Never move a ticket to Done or close it
  yourself unless Chad explicitly asks. The team reviews and closes Ready to
  Close tickets together at Monday morning planning, so Chad doesn't close them
  himself. Don't list them as waiting on Chad or remind him to close them.
- Canceled: only when Chad drops the work.

When the status or the plan changes, add a short comment with a link, rather
than rewriting the description.

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
which bot did the work. Never cite the bots' own rules or instructions in
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

## Work-in-progress limit

Keep at most 3 of your own tickets in In Progress at once. If you're at the
limit, finish, hand off, or pause one before you start another. If something
truly urgent can't wait, say so in the new ticket.

## If you can't reach Linear

If you don't have a working Linear connector, send the ticket details to Cully,
Chad's executive assistant bot (id 05c7f039-309c-47a2-8156-1a26a46018b6), and
Cully will open the ticket for you. Tickets for later work still go to Marty.
