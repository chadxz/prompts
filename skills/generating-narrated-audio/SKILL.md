---
name: generating-narrated-audio
description:
  Generates narrated MP3 audio from text or Markdown files by first
  producing a TTS-friendly intermediate version, then using Gemini
  text-to-speech, paragraph chunking, and cached intermediate WAVs.
  Use when the user wants a document, transcript, notes, or draft
  turned into listenable narration with smoother pronunciation and an
  optional custom speaking style.
user-invocable: true
---

# Generating Narrated Audio

Use the bundled script to turn a text or Markdown file into a narrated MP3.
Before running the script, create a TTS-friendly version of the source text and
narrate that rewritten copy instead of the raw input. If the source is prose
written on Chad's behalf, that rewrite must strictly follow the
`writing-in-my-voice` skill before any TTS cleanup.

## Quick Start

Create a TTS-friendly intermediate text file, then run the bundled script with
that file:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --input <tts-friendly.txt>
```

In pi, resolve `scripts/narrate.sh` relative to this skill directory and use the
resolved absolute path. In Claude-style skill runners, `<skill-dir>` can be
`${CLAUDE_SKILL_DIR}`.

Use `--output` when the filename must be deterministic. Use `--style-file`
instead of an inline style prompt when the narration instructions are more than
a sentence or two.

## Workflow

1. Confirm the source file already exists and is readable.
2. Prefer plain text or Markdown inputs. If the source is a PDF or rich
   document, extract or export text first.
3. Create a TTS-friendly version of the text:
   - If the source is prose written on Chad's behalf, apply the
     `writing-in-my-voice` skill first and treat it as a hard constraint. Do not
     let TTS cleanup flatten the voice into generic formal narrator prose.
   - Preserve the original meaning and section order.
   - Keep Chad's voice intact while making the text speakable. Maintain
     contractions, cadence, directness, and the original level of specificity
     unless changing them is required for pronunciation or listener
     comprehension.
   - Expand or rewrite terms TTS often mangles, such as acronyms, initialisms,
     shorthand, slash-separated phrases, and words like `PRs`, `SaaS`, `CI/CD`,
     or `k8s`.
   - Rewrite dense visual text into spoken-friendly phrasing when that improves
     pronunciation or flow.
   - Do not add filler transitions, summary language, or explanatory scaffolding
     that would violate the voice just because it sounds more "narrated."
   - Keep the original source file unchanged unless the user explicitly asks to
     replace it.
   - If the user provides text inline instead of via a file, write the rewritten
     version to a temporary text file and narrate that.
4. Choose a narration style:
   - Use the built-in default for internal docs and RFC-style content.
   - Use `--style "<prompt>"` for a short override.
   - Use `--style-file <file>` for longer or reusable prompts.
5. Run the script against the TTS-friendly file.
6. Verify that the MP3 exists and that the script printed a non-zero duration.

## Common Commands

Default naming beside the input file:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --input notes-tts.txt
```

Explicit output filename:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --input rfc-tts.txt \
  --output rfc.mp3
```

Custom narration style from a file:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --input transcript-tts.txt \
  --style-file narration-style.txt
```

## Gotchas

- The script expects a text-like source file. Do not point it at binary formats.
- Always narrate the TTS-friendly intermediate text, not the raw source, unless
  the user explicitly asks for a literal read.
- When the source is Chad-authored prose, voice fidelity beats generic narration
  polish. Smooth pronunciation and flow, but do not sand off contractions or
  rewrite the text into a different voice.
- Pronunciation smoothing should favor what the listener needs to hear, not what
  looks closest to the original typography.
- If `GEMINI_API_KEY` is unset, the script falls back to Chad's 1Password item
  at `op://Employee/Personal Gemini API Key/General/API Key`. If `op` is
  unavailable, set `GEMINI_API_KEY` before running it.
- Output defaults to `<input-stem>-<timestamp>.mp3` beside the input file. Use
  `--output` when the filename should be stable.
- Cached WAV chunks live under
  `${XDG_CACHE_HOME:-$HOME/.cache}/gemini-tts-audio`. Re-running with the same
  model, voice, style, and text reuses cached audio.
- A short spoken disclosure is included by default. Only use `--no-disclaimer`
  when the user explicitly wants it omitted.

## Validation

If the run succeeds, the script prints the final path, size, and duration. If it
warns about failed chunks, re-run the same command: cached chunks are reused and
only missing chunks are retried.
