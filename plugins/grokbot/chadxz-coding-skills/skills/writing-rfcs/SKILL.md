---
name: writing-rfcs
description: >-
  Use whenever you (one of Chad's bots, or a cloud agent working on Chad's
  behalf through one) draft, port, revise, or share a Convergint RFC (Request
  for Comments) in Notion, including turning an ADR or research into an RFC.
---
# Writing RFCs

**Read the full RFC guide first, every time:** [RFC Documentation](https://app.notion.com/p/3735f445bd318062a095d62acb48013c), in Tech Wiki / How we work. Fetch the whole page with the Notion connector and read it end to end, then open the [RFC Template](https://app.notion.com/p/2735f445bd31809090eff40c9109edb0) and some [published RFCs](https://app.notion.com/p/1135f445bd3180baab6cee1b6ced0764?v=e3c88fe44eda4d9aa6659bf27380ab4c) as examples. The guide is the source of truth. This skill sums it up and adds Chad's corrections. If the two disagree, follow the guide and update this skill.

An RFC asks for feedback. It isn't an approval gate, a project plan, or a research dump. It should be just long enough for reviewers to judge the proposal and spot risks.

## 1. Decide whether it's an RFC

- Write an RFC when the change reaches beyond one team, or when you want input from people outside it (another team's area, unknown unknowns).
- Don't write one when the author can't act on the decision, or when the change doesn't clearly beat the status quo.
- A decision that stays inside one repo goes in an ADR instead (see the `writing-adrs` skill).

## 2. Set up the page

- Create it in the **Docs** database from the "Request for Comments" template. Set Document Type to RFC, and set the Title, Author, Status and Review By date.
- Keep the page at Notion's default width, never full width. The template is set to full width, so new pages copy it. Right after you create the page, turn it off with `notion-update-page`, command `update_properties`, `full_width: false`, and check that a fetch shows `"full_width":false`.
- Title it `RFC - <what we'll do>` as an action, for example "RFC - Issue Cloudflare Total TLS certificates from Google Trust Services".
- Set Status to **Drafting** while you write. Set Review By 1–2 weeks out.
- Make the first block one selling sentence that says what changes and why, so the Notion link preview shows it.
- Under it, add a short "Your feedback is requested" list of 2–4 specific questions you want reviewers to answer.

## 3. Write the body in NABC order

Use the template's headings: Need, Approach, Benefits, Competition / Alternatives, Feedback, References.

- **Need:** the real problem today, who it hurts and what it costs, grounded in what actually happened (an incident, a ticket, numbers). If it reads like a pitch for the Approach, rewrite it.
- **Approach:** the solution in rough terms, plus the key decisions and trade-offs. Add scope, where the change lives, and rollout and rollback only as far as reviewers need them to judge risk. No task lists.
- **Benefits:** measurable gains that are meaningfully better, not just different. Say how you'd know it worked.
- **Competition / Alternatives:** see section 4. Always include doing nothing.
- **Feedback:** "None yet." until reviewers comment, then a summary of each comment and your response.
- **References:** tickets, related RFCs and ADRs (as Notion mentions), and vendor docs.

## 4. Alternatives: every one says why it was rejected, with a real reason

For each alternative, write:

1. **The strongest honest version of it.** Describe it the way its biggest fan would. If a better variant exists, write up that one; for example, "use subzones" rather than "rename every hostname".
2. **An explicit rejection line**, starting with **Rejected because**, followed by one or two sentences.

The rejection reason has to be legit:

- **It's a fact you verified this session,** from a live query, the code, vendor docs or a ticket, and it's not a guess or something you remember. Before you write that an option "would require", "costs", "breaks" or "can't", prove it. Get counts and examples from live data; for example, resolve the hostnames you name.
- **It's specific to this option and to us.** Vague lines like "messier", "more complex", "no advantage" or "not a fit" aren't reasons. Say what extra work, cost, risk or failure the option brings and who carries it.
- **It's decisive.** A side effect that wouldn't change the decision doesn't count. If the only honest reason is weak, say so, or reconsider whether the alternative is actually better.
- **If you can't verify a reason, cut it.** If none of the reasons hold up, the alternative may be the better choice, so tell the owner and don't write it off.

## 5. Rules that come from Chad's corrections

- **Keep it short.** Make length match complexity, and make every paragraph earn its place. Leave out evidence tables, test IDs, YAML, command output, rehearsal logs and in-flight PR lists. Link to the ticket or ADR for the details.
- **Batch open questions.** Before the first draft, gather every open question into one list for Chad, rather than asking them one at a time.
- **Check every claim against a source,** not only the rejections. Before you give a number, get it from a live query and don't estimate.
- **No attribution.** Leave out lines like "per Chad", "decided by" or "approved by". The Author field covers it.
- **Plain words.** Write in Chad's voice (load `writing-in-my-voice`): complete sentences, define acronyms on first use, no coined labels.
- **Scope to where the work really lands.** If config is moving to another repo or team, as Cloudflare config is moving to `it-monorepo`, say the change lands there and name who reviews it.

## 6. Review it before you share

Re-read the page as a reviewer and check these:

1. After the Need section, does a reader understand *why* this change is needed?
2. Does every alternative have a **Rejected because** line that passes the section 4 tests, and would its biggest fan accept the description as fair?
3. Does every number, name and "would require" claim trace to a source you checked this session?
4. Could any paragraph be cut without losing the reviewer's ability to judge the proposal? If so, cut it.
5. Does the draft still match the full RFC guide, which you re-read just now?
6. Does a fetch of the page show `"full_width":false`?

## 7. Share it and close it

- Sharing is an outside send, so get the owner's go-ahead first unless they've asked you to share it. Post a link with a short description in #engineering (or the group's usual channel), tag the reviewers, and set Status to **Reviewing**.
- Respond to every comment by the Review By date, and log each one under Feedback.
- On the Review By date, the author marks it **Published** (going ahead) or archives it, and never deletes it.
- Link the RFC from the Linear ticket that tracks the work.
