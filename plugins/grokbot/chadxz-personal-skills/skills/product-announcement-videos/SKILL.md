---
name: product-announcement-videos
description: >-
  Use when building short product announcement videos for features shipped in a
  reporting window (including as part of the weekly personal activity report),
  or when folding announcement videos into EE Notion announcements.
---
# Product announcement videos

Build short (~60–90s, 16:9) product announcement videos for features shipped in the current reporting window. Videos sit at the top of EE Notion Announcement pages and should match EE announcement voice (Windows containers / Teams MCP style): plain, direct, engaging without hype.

## When this runs

- As a standing step of the Thursday personal week-in-review, after the report PDF is delivered (or in parallel once the feature shortlist is clear).
- Anytime Chad asks for announcement videos for a set of shipped features.

## Steps

1. **Shortlist features.** From the week’s personal activity evidence (merged PRs, Done/Ready-to-Close Linear, shipped prod), pick announceable product features — not chore PRs. Cap at what can be finished well (usually 2–4).
2. **Open or reuse a Linear ticket** (`tracking-bot-work-in-linear`) for the video batch; label `bot:cully` (or the owning bot); keep WIP rules.
3. **Collaborate with owning bots.** Ask each feature’s owning bot for: pitch, ~60–90s script beats, asset pack (real screenshots, code samples, recordings, URLs), and a do-not-claim list. Do not invent UI.
4. **House style.** Keep one consistent look/voice across the batch. Prefer the guide at `/workspace/announcement-videos/brand/ee-announcement-video-guide.md` when present; otherwise mirror EE Notion announcements (hook → what’s new → why → how → CTA to `#team-eng-enablement`).
5. **Gather assets.** Save under `/workspace/announcement-videos/<feature-slug>/`. Reuse PR-embedded demos when they exist. Blur secrets.
6. **Brief Opus 5.5 xhigh cloud agents** (`claude-opus-5-5`, `model_params.effort=xhigh`) — one agent per feature (or one Project only if Chad asks for a Project). Follow `cloud-agent-brief-checklist`. Prefer Remotion (or equivalent code-driven video) with real stills/clips; do **not** use Grok Imagine / GenerateVideo for UI demos. Ticket ID and `bot:` label in the brief. Babysit the PR; never merge.
7. **Deliver.** Send Chad the MP4s (and poster frames) in chat; note Notion embed path. Offer to place each video at the top of the matching Announcement page when that page exists or is drafted.
8. **Stand down.** Comment progress on the Linear ticket; move to Ready to Close when videos are accepted.

## Gotchas

- Skip features the owning bot marks not-ready (e.g. early over-reach not yet framed).
- Cursor artifact URLs often need a signed-in browser; curl alone is not enough.
- Keep voice in Chad’s first person for PR bodies; video VO is EE “we/you”.
