---
name: product-announcement-videos
description: >-
  Use when building short product announcement videos for features shipped in a
  reporting window — required as the post-PDF step of the Thursday personal
  week-in-review — or when folding announcement videos into EE Notion
  announcements.
---
# Product announcement videos

Build short (~60–90s, 16:9) product announcement videos for features shipped in the current reporting window. Videos sit at the top of EE Notion Announcement pages and should match EE announcement voice (Windows containers / Teams MCP style): plain, direct, engaging without hype.

## When this runs

- **Required week-in-review step.** After the Thursday personal activity report PDF is delivered (same reporting window), run this skill before standing down. If nothing announceable shipped, say so in one line and skip.
- Anytime Chad asks for announcement videos for a set of shipped features outside that cadence.

## Standing creative decisions (reuse these)

Capture Chad’s standing preferences here so every batch — including week-in-review — starts from the same bar:

1. **First frame = banner.** Every video opens on its title/banner card (same look as the poster / opening title treatment). Frame 0 must not be a mid-scene still, code card, or UI screenshot.
2. **Music bed — upbeat commercial.** Add a light upbeat commercial-style bed under the VO (product-ad energy, not sleepy lo-fi). Keep VO clear and dominant; duck the bed under speech (~15 LU); allow a small lift between scenes; fade on end cards.
3. **Vary the music per release.** Each video in a batch gets its **own** royalty-free track. Do not reuse one bed across every video in the set. Prefer license-safe / CC tracks with required credit on the end card (and note the credit in ASSETS.md / Notion embed notes). If a prior cut already locked a track for one video and Chad says keep it, leave that one alone and vary the others.
4. **Vary the voice per release.** Each video in a batch uses a **different** TTS / Kokoro voice (or clearly distinct speaker character). Do not use one voice across the whole set. Keep EE announcement tone; still apply pronunciation pins below.
5. **Vary the visual theme per release.** Each video gets a visibly different design (palette, typography, accent, spatial silhouette) — same idea as rotating the weekly personal activity report’s look. Keep EE announcement readability and CTA; do not ship four identical skins. Track themes used (e.g. under `/workspace/announcement-videos/theme-history.json`) so later batches don’t repeat recent ones when alternatives exist.
6. **VO pronunciation.** Fix synthetic VO so product words land correctly. In particular: “live” as in live-action / go-live (rhymes with five, not give); “eng” in `#team-eng-enablement` as the start of “engineering” (/ˈɛndʒ/), not a hard eng. Audit other product names (1Password, GitHub, CI, SSO, etc.) the same way after each render.
7. **1Password examples.** When highlighting 1Password integration, show a real `op://` CLI-style reference in the code example (e.g. `op://<vault>/<item>/<field>` matching the live product shape). Never a vague “from 1Password” placeholder or obsolete `{item, field}` object once the product uses `op://`.
8. **Real assets only.** Use real screenshots, code samples, and recordings from owning bots / PRs. Do not invent UI. Blur secret values; `op://` references themselves are fine to show.
9. **Watch before Notion.** Deliver MP4s + posters to Chad first; embed at the top of the matching Announcement page only after he watches with sound and OKs.

## Steps

1. **Shortlist features.** From the week’s personal activity evidence (merged PRs, Done/Ready-to-Close Linear, shipped prod), pick announceable product features — not chore PRs. Cap at what can be finished well (usually 2–4).
2. **Open or reuse a Linear ticket** (`tracking-bot-work-in-linear`) for the video batch; label `bot:cully` (or the owning bot); keep WIP rules.
3. **Collaborate with owning bots.** Ask each feature’s owning bot for: pitch, ~60–90s script beats, asset pack (real screenshots, code samples, recordings, URLs), and a do-not-claim list. Do not invent UI.
4. **House style.** Keep one consistent look/voice across the batch. Prefer the guide at `/workspace/announcement-videos/brand/ee-announcement-video-guide.md` when present; otherwise mirror EE Notion announcements (hook → what’s new → why → how → CTA to `#team-eng-enablement`). Apply the standing creative decisions above.
5. **Gather assets.** Save under `/workspace/announcement-videos/<feature-slug>/`. Reuse PR-embedded demos when they exist. Blur secrets.
6. **Brief Opus 5.5 xhigh cloud agents** (`claude-opus-5-5`, `model_params.effort=xhigh`) — one agent per feature (or one Project only if Chad asks for a Project). Follow `cloud-agent-brief-checklist`. Prefer Remotion (or equivalent code-driven video) with real stills/clips; do **not** use Grok Imagine / GenerateVideo for UI demos. Ticket ID and `bot:` label in the brief. Explicitly require: first frame = banner; unique music bed per video; unique VO voice per video; unique visual theme per video; VO ducking rules; pronunciation pins; `op://` when relevant. Babysit the PR; never merge.
7. **Deliver.** Send Chad the MP4s (and poster frames) in chat; note track choices + loudness; note Notion embed path. Offer to place each video at the top of the matching Announcement page when that page exists or is drafted — only after his watch/OK.
8. **Stand down.** Comment progress on the Linear ticket; move to Ready to Close when videos are accepted.

## Gotchas

- Skip features the owning bot marks not-ready (e.g. early over-reach not yet framed).
- Cursor artifact URLs often need a signed-in browser; curl alone is not enough.
- Keep voice in Chad’s first person for PR bodies; video VO is EE “we/you”.
- When VO and a still disagree (e.g. out-of-scope example PR isn’t a release/dep bump), rewrite the VO to match the still — don’t leave a mismatch.
- Paid no-attribution music licenses are optional; default is royalty-free with end-card credit.
