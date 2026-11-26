---
name: working-in-notion
description: Conventions for searching, creating and editing pages and databases in Chad's work Notion (Convergint Tech). Use whenever a bot, or a cloud agent working on Chad's behalf through one, searches Notion, creates or edits a page or database row, comments, uploads a file, or decides where a doc should live.
---

# Working in Notion

## Workspace and access

1. Use the Convergint Tech workspace. Use the personal chadxz workspace only
   when Chad asks.
2. When doing work Chad asked for, use his Notion connector. When posting on
   your own, use the bot's key. For anyone else, use the bot's key or their
   connection. Never lend Chad's access.
3. Read, write, edit, comment and publish without asking Chad first.
4. Trash pages you created when it's reasonable. Ask before deleting a page you
   didn't create.
5. The connector can't change sharing. Tell Chad when a page needs sharing.

## Finding things

1. Search live. Don't build or keep a Notion index.
2. When search misses, browse the hub pages: Engineering Enablement, The
   Platform, Team Runbooks, Announcements. Query the Docs and Announcements
   databases directly.
3. Extend an existing page before creating a new one.
4. Check a Notion guide against the live code or config before relying on it.

## Where things go

1. Platform feature pages and runbooks for platform users: under The Platform.
   Add or update the feature's row in the Platform Capabilities table, with its
   maturity.
2. EE team runbooks: under Team Runbooks, titled "How to <task>".
3. RFCs and other team documents: the Docs database, from the matching template,
   with Document Type, Author and Status set. Load the `writing-rfcs` skill for
   RFCs.
4. Announcements: the Announcements database, titled "YYYY-MM-DD Announcement -
   <hook>: <capability>".
5. Ideas: the Ideas for the Future database. Load the `enriching-idea-cards`
   skill.
6. Vendor contacts: the Vendor Contacts page, one H1 per vendor with "Primary
   Contacts" and "How to Get Support" under it.
7. Project trackers: one top-level page per project, kept current, with a child
   runbook page per system. If the natural home belongs to another team, create
   the page beside it and link to theirs.
8. Drafts Chad wants to iterate on: a separate page until he says to merge.
9. Taco 'Bout It posts: under Chad's personal page.
10. Never put product announcement videos in Notion.

## Document type

1. When creating or substantially editing a doc, classify it as one Diataxis
   type: tutorial, how-to, reference or explanation. Shape it to that type. Load
   the `writing-diataxis-documentation` skill for the details.
2. When touching an existing page, nudge it toward its type. Don't rewrite it
   wholesale.

## Titles and opening

1. Give every page a meaningful title that says what it's about. No ticket IDs
   or ticket names; link the ticket in the body.
2. Match the title pattern of sibling pages.
3. Existing pages that break these rules are grandfathered. Don't rename or
   restyle them just to comply.
4. Open with one or two plain sentences that work as the Slack unfurl. Put an
   announcement's hero image right after them.
5. Put a divider under the opening.

## Structure

1. Make main sections H1. Lean toward the EE colors: H1 yellow, H2 blue, H3 bold
   green, and colored callouts.
2. Give every page a relevant icon emoji. Prefer an on-point one over a generic
   one. If none fits, add one to the workspace emoji library.
3. Use emoji sparingly elsewhere.
4. Mark a feature page's maturity (for example Alpha) in a gray callout.
5. Keep pages crisp: no history, PR lists, logs, YAML or command output. Put
   needed detail on a linked child page.
6. Make pages for platform users stand alone.
7. Size the page to the ask.
8. Link anything outside the page the first time it comes up, on the words that
   name it. Link Notion pages as mentions. Inline screenshots.
9. Re-verify a verified page for 90 days when you update it.

## Voice

1. Load the `writing-in-my-voice` skill for every page, post and comment. It
   governs prose, tables and bullets.
2. Follow the structure and tone of earlier announcements.
3. Make Taco 'Bout It posts upbeat: lead with what you're excited about, stuck
   items second. Post only when you add something.

## Editing

1. Fetch the page right before editing. Make targeted edits so you don't
   overwrite anyone's changes.
2. On a page someone else owns, comment instead of editing unless told
   otherwise.
3. Don't reshape a template or another team's page. Add beside it or at the
   bottom.
4. When pruning, sort each section into keep, move or cut, and verify what stays
   against the live system.
5. Fold decided questions into the content as fact. No change notes.
6. Write comments that stand alone.

## Databases

1. Fetch the schema before writing a row. Use the existing properties and
   templates; don't add properties.
2. Keep structured fields minimal. Taco 'Bout It uses only Headline and Bot.
3. Don't change Status or triage fields on rows you don't own.
4. Docs status runs Drafting, Reviewing, then Published or Archived. Never
   delete an RFC.

## Tools

1. Default to Notion MCP. Use `ntn` for file uploads, HTML embeds and repeatable
   scripts. Load the `choosing-notion-tools` skill for details.
2. Convergint Tech is on the Enterprise plan. Free-plan upload limits don't
   apply.
3. Check the live tool list before saying a tool can't do something.

## Read back

1. Fetch the page after every write. Check for truncated or unknown blocks, the
   opening, heading colors, the divider, and every link and mention.
2. Report the page link and what changed. Say if the page is still private.
3. When Chad's feedback changes how you work in Notion, update this skill.
