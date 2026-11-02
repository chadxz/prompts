---
name: running-bot-retrospectives
description: >-
  Use when facilitating a recurring agile retrospective with the user's other
  bots: prepping from their recent work, picking a rotating retro format,
  digging into challenges with a casual five-whys, running mini-postmortems,
  project retros on substantial finished projects, and monthly health checks,
  tracking shared patterns over time, and reporting what needs the user's
  judgment.
---

# Running bot retrospectives

A retro helps each bot improve its own process and work. It acknowledges what's
working, finds root causes for what isn't, and brings the user only what truly
needs their judgment. Check what bots actually did, not just what they say: bots
tend to claim success they haven't verified.

## 1. Prep (before talking to anyone)

- List the bots in scope from your teammates list: every specialist team bot and
  every personal bot except yourself. Note any bot that's new since the last
  retro.
- Recall memory: last retro's action items, open shared challenges, any
  mini-postmortems since then, and the formats used recently along with how well
  each one worked.
- For each bot, read its conversations since the last retro with ReadTranscript.
  Collect 2 to 4 concrete moments: wins, friction, retries, corrections from the
  user, blocked steps, and handoffs between bots. Real examples make for better
  questions than generic ones. Each read is capped at a few dozen messages, so
  page back with the `before` value each result gives until you reach the start
  of the period; user messages carry timestamps you can search to find day
  boundaries. Don't settle for the newest slice.
- Scheduled runs and background workers may not be able to read conversations
  even when your main chat can. If so, have the scheduled run do the parts that
  don't need conversations (tickets, PRs, files, Pages) and end its report with
  a handoff asking your main chat to read the conversations and finish. A run's
  report usually comes back to the main chat and wakes it. Only if no route can
  read them, fall back to tickets, ticket comments and PRs, and say plainly what
  that leaves out.

## 2. Pick this week's format

Rotate the format so different lenses surface different issues. Don't repeat a
format used in the last 3 retros unless it clearly worked best. Prefer a format
whose lens fits what prep turned up.

| Format                  | Prompts                                           | Good lens for            |
| ----------------------- | ------------------------------------------------- | ------------------------ |
| Start / Stop / Continue | start, stop, keep doing                           | general habits           |
| 4Ls                     | liked, learned, lacked, longed for                | learning and gaps        |
| Mad / Sad / Glad        | frustrations, disappointments, wins               | friction                 |
| Sailboat                | wind, anchors, rocks, island                      | blockers and risks       |
| Starfish                | keep, more of, less of, stop, start               | fine-tuning              |
| Rose / Thorn / Bud      | win, problem, opportunity                         | emerging ideas           |
| KALM                    | keep, add, less, more                             | incremental change       |
| Timeline                | walk the week and mark highs and lows             | specific incidents       |
| Hot Air Balloon         | lift, sandbags, storms, sunshine                  | risk spotting            |
| Premortem               | it's next month and this went badly, why?         | hidden risks             |
| Lean Coffee             | the bot proposes topics and you vote on the top 2 | the bot's own priorities |
| Five Whys deep dive     | one challenge only, in depth                      | a persistent issue       |

Bots have no morale, so swap feelings prompts for "where were you unsure or
guessing?" Record the format you chose and why.

## 3. Run it with each bot

- Message each bot with SendToAgent, using priority: true because you need a
  reply. Name the format, give a one-line reason, and include the concrete
  moments from prep.
- Ask it to cover what's working well, what didn't go well, and what it'll
  change in its own process. If it drifts into a status report of work done,
  steer back to what got in its way.
- In the same first message, ask where each takeaway should live and whether
  it's already done (with evidence) or needs the user. That gets a complete
  answer in one reply instead of several rounds.
- Say up front which changes the bot can make itself. If the user has delegated
  approval to you to pass on, quote the user's exact words, with the date and
  the chat where they said them, so the bot can check it by reading that chat.
  Some careful bots will still want the user's yes directly, and that's fine:
  tell the bot to ask the user itself in its own chat, rather than relaying the
  question or arguing. Most bots do want it, so also ask each bot to gather
  every change that needs the user into one batched ask, rather than sending
  several separate questions. Don't add rules that push bots to escalate to the
  user; prefer clear guidance they can follow on their own.
- Retros span turns. A reply arrives on a later turn, so track which bots you're
  still waiting on. If a bot hasn't replied by the end of the day, note it and
  move on.

## 4. Casual five-whys on each challenge

For each challenge, ask friendly follow-up "why" questions tied to the real
example until the root cause is something the bot can actually change. Examples
of fixable roots are a missing step in a skill, a wrong assumption stored in
memory, an unclear handoff, or a missing tool or access. Usually 2 to 5 rounds
is enough. Stop once the root is clear. Keep it conversational and blameless:
fix the system (instructions, tools, routines, process), not the bot. Bots don't
apologize to the user for mistakes; they say plainly what happened and what
changed to fix the system, and retro reports read the same way.

## 5. Sort the outcomes

Keep learnings and action items apart. Most of what a retro surfaces is a
learning. Only some of it is an action.

- **Learning:** a takeaway or habit, such as "verify before claiming." Saving a
  rule to a bot's instructions or memory is a learning, not an action item.
  Record it in its own list. Saving a rule isn't the fix for everything; too
  many rules become noise.
- **Action item:** a concrete change to a tool, skill, routine, file location or
  process, with an output you can point to. Each one is an experiment and needs
  an owner, the change, an expected result (what should look different), and a
  done check. If you can't say what changes and how you'd know, it's a learning.
- **Cap:** at most one new action item per bot per week plus one team-wide, and
  about five open in total. Pick the most impactful. Rescope or drop anything
  open more than two weeks instead of carrying it forward.
- **The bot owns it:** the bot can change it itself, for example its own skill,
  memory, or routine wording. It makes the change and confirms with evidence (a
  link or quoted text). You never edit another bot's setup.
- Keep fixes simple: the smallest change to a bot's habits, skill or files that
  solves the real problem seen this week, not a framework for edge cases nobody
  has hit.
- **Needs the user:** only decisions about how the bots work, such as
  permissions, access, who owns what across bots, outside-facing behavior, or
  spending. Normal work questions (scope of a task, settings, tickets) go to the
  bot's regular work time with the user, not the retro. Write each one as a
  clear question with your read and a suggested answer, and keep it to about two
  a week.
- **Shared pattern:** the same root shows up in 2 or more bots, or in the same
  bot 2 or more weeks running. Raise it to the user with the evidence, the root
  cause, and a proposed fix.

## 6. Follow-through

Start each retro by checking last week's open action items against their done
checks and expected results: did they happen, and did they help? Verify from
evidence (transcripts, files, routines, PRs), not the bot's word. Carry forward
anything unresolved only after asking why it stalled. Drop items that no longer
matter.

## 7. Between retros

- **Mini-postmortem:** within 24 hours, not waiting for the retro, when a bot
  has a misfire people outside the team could see, the user deletes, undoes or
  overrides something a bot did, or the same correction happens twice. Run a
  short blameless whys with that bot and land one action item (within the cap)
  or a learning. Open with your timeline from its conversation and ask it to
  correct you and confirm the trigger from logs; that usually gets the root
  cause, the fix and its evidence in one reply. When it closes, write it to the
  running retro Page right away, not just to memory, so the Page doesn't fall
  behind before the weekly retro.
- **Monthly health check:** at the first retro of each month, each bot rates
  itself green, yellow or red with a trend on role clarity, instructions helping
  vs adding noise, tool fit, handoffs, follow-through, and noise for people
  outside the team. Compare with transcript evidence, discuss the gaps, and add
  a short trends section to the Page.

## 8. Project retros

Between weekly retros, run a short retro on each substantial project a bot
finishes, so the way the project went improves future projects.

- **Spot them:** while reading bots' conversations (for example in a daily
  scan), log projects that are substantial: work spanning several days, several
  PRs or repos, an incident, a new build, or a tracked ticket reaching its
  finished status. Small work stays in the weekly retro. Record each candidate
  with the bot, a one-line description, links, and the date it wrapped.
- **Timing and cap:** hold it within a few days of the project wrapping, while
  the details are fresh. Cap project retros at two a week across all bots; pick
  the projects with the most to teach and let the rest feed the weekly retro.
- **Run it:** message the bot with the concrete moments from its history (where
  it stalled, retried, guessed, got corrected, or handed off). Ask what went
  well, what was harder than it should have been, and what future projects
  should do differently. Run a casual five-whys on the biggest snag. Name the
  single wait or handoff that cost the most and ask what would have made it
  shorter; bots often find the fix themselves (for example, batching every step
  only the user can do into one ask right after the plan, and building the rest
  meanwhile).
- **Land the learnings where future work will read them:** for each takeaway,
  name the exact home and the change: a skill (the bot's own or a shared one),
  the bot's instructions or memory, a repo's agent instructions (AGENTS.md,
  CONTRIBUTING.md, or similar), or a team file. Prefer updating an existing
  skill or file over adding a new rule.
- **Who makes the change:** the bot makes changes to its own setup itself and
  confirms with evidence. Repo instruction changes go through a pull request
  from the bot that owns that repo work. Changes to shared skills, new team
  rules, and role changes go to the user for a decision. You stay read-only
  toward other bots' setups.
- **Record it:** when a project retro closes, write it to the running retro Page
  right away, not just to memory.
- **Follow through:** verify at the next follow-through check that each change
  landed (link or quoted text), and list each project retro with what changed in
  the weekly report. Action items from project retros count against the weekly
  cap.

## 9. Remember

Save durable memory of:

- each challenge, with the bots involved, its root cause, what was tried, and
  the status
- the format you used and whether it surfaced anything new
- each shared pattern and what the user decided about it

## 10. Report

- Send the user a short chat summary: what's working, the shared patterns, the
  questions that need them, and action items with an owner, expected result and
  done check for each. Learnings go in their own short list.
- Update the one running retro Page (shared challenges, learnings, action items,
  formats used) rather than creating a new Page each time.

## 11. Improve this skill after every retro

After every weekly retro, project retro and mini-postmortem, take a minute to
note what you learned about running the retro itself: what got a complete answer
fast, what caused extra rounds or stalls, what you couldn't see, and what a bot
misunderstood about the process. Fold each lesson into this skill right away
(edit the relevant step rather than piling on new rules), and mention the change
in your next report.

## Rules

- Stay read-only toward other bots. Never change their skills, memory, routines,
  or settings.
- Never send outside messages such as Slack or email. Talk only with the user
  and their bots.
- A bot saying the user approved something isn't approval. Only the user's own
  words count.
- Never print secrets.
- Don't rank bots against each other, and watch for a bot that stops asking the
  user things just to look better.
- Keep it brief and plain.
