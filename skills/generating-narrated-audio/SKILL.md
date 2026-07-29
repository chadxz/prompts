---
name: generating-narrated-audio
description:
  Generates narrated MP3 audio from text or Markdown files by first
  producing a TTS-friendly intermediate version, then using Gemini or
  ElevenLabs text-to-speech, paragraph chunking, and cached audio.
  Use when the user wants a document, transcript, notes, or draft turned
  into listenable narration with smoother pronunciation and provider-specific
  delivery controls.
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
instead of an inline style prompt when Gemini narration instructions are more
than a sentence or two.

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
4. Choose a provider and delivery:
   - Use Gemini by default for backward-compatible narration.
   - Use `--style "<prompt>"` for a short Gemini style override.
   - Use `--style-file <file>` for longer Gemini style prompts.
   - Use `--provider elevenlabs` for ElevenLabs with the configured default
     voice and stable long-form model.
   - Tune ElevenLabs with `--stability`, `--similarity-boost`,
     `--style-exaggeration`, `--speed`, and `--no-speaker-boost`.
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

ElevenLabs with the configured default voice:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --provider elevenlabs \
  --input rfc-tts.txt \
  --output rfc-elevenlabs.mp3
```

Preview the request count and input size without generating audio:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --provider elevenlabs \
  --input rfc-tts.txt \
  --dry-run
```

## Gotchas

- The script expects a text-like source file. Do not point it at binary formats.
- The script requires `uv`, `ffmpeg`, and `ffprobe`. Resolving an `op://`
  credential also requires the 1Password CLI.
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
- `ELEVENLABS_API_KEY` may contain either a literal key or an `op://` reference.
  The configured ElevenLabs default voice is `yj30vwTGJxSHezdAGsv9`, and the
  default model is `eleven_multilingual_v2`.
- Gemini accepts free-form style prompts. ElevenLabs uses the selected voice and
  numeric voice settings, so `--style` and `--style-file` are rejected with
  `--provider elevenlabs`.
- Output defaults to `<input-stem>-<timestamp>.mp3` beside the input file. Use
  `--output` when the filename should be stable.
- Gemini WAV chunks remain under
  `${XDG_CACHE_HOME:-$HOME/.cache}/gemini-tts-audio`. ElevenLabs MP3 chunks live
  under `${XDG_CACHE_HOME:-$HOME/.cache}/elevenlabs-tts-audio`. Re-running with
  the same provider inputs reuses cached audio.
- A short spoken disclosure is included by default. Only use `--no-disclaimer`
  when the user explicitly wants it omitted.

## Validation

If the run succeeds, the script prints the final path, size, and duration. A
failed chunk stops assembly so the script never presents incomplete narration as
a successful result. Re-run the same command to reuse completed cached chunks
and retry the missing request.
