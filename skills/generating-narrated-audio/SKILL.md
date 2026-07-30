---
name: generating-narrated-audio
description:
  Generates narrated MP3 audio from text or Markdown files by first producing
  a TTS-friendly intermediate version, then using Kokoro through oMLX in one
  synthesis invocation. Use when the user wants a document, transcript, notes,
  or draft turned into listenable narration without remote TTS APIs.
user-invocable: true
---

# Generating Narrated Audio

Use the bundled script to turn a text or Markdown file into a narrated MP3.
Before running the script, create a TTS-friendly version of the source text and
narrate that rewritten copy instead of the raw input. If the source is prose
written on Chad's behalf, that rewrite must strictly follow the
`writing-in-my-voice` skill before any TTS cleanup.

The script uses Kokoro's `af_heart` voice by default through the MLX audio
runtime bundled with oMLX. It sends the complete input through one synthesis
invocation and writes one MP3. Don't divide the input into paragraph, sentence,
or character-count chunks before calling the script.

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

Use `--output` when the filename must be deterministic. Use `--voice` only when
the user requests a Kokoro voice other than `af_heart`.

## Workflow

1. Confirm the source file already exists and is readable.
2. Prefer plain text or Markdown inputs. If the source is a PDF or rich
   document, extract or export text first.
3. Create a TTS-friendly version of the text:
   - If the source is prose written on Chad's behalf, apply the
     `writing-in-my-voice` skill first and treat it as a hard constraint. Don't
     let TTS cleanup flatten the voice into generic formal narrator prose.
   - Preserve the original meaning and section order.
   - Keep Chad's voice intact while making the text speakable. Maintain
     contractions, cadence, directness, and the original level of specificity
     unless changing them is required for pronunciation or listener
     comprehension.
   - Expand or rewrite terms TTS often mangles, such as acronyms, initialisms,
     shorthand, slash-separated phrases, and words like `PRs`, `SaaS`, `CI/CD`,
     or `k8s`.
   - Rewrite dense visual text, code samples, links, and reference definitions
     into spoken-friendly phrasing.
   - Turn headings into short spoken transitions so flattened line breaks don't
     run sections together.
   - Don't add filler transitions, summary language, or explanatory scaffolding
     that would violate the voice just because it sounds more narrated.
   - Keep the original source file unchanged unless the user explicitly asks to
     replace it.
   - If the user provides text inline instead of via a file, write the rewritten
     version to a temporary text file and narrate that.
4. Run the script once against the complete TTS-friendly file.
5. Verify that the MP3 exists and that the script printed a non-zero duration.

## Common Commands

Default naming beside the input file:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --input notes-tts.txt
```

Explicit output filename:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --input adr-tts.txt \
  --output adr.mp3
```

Alternate Kokoro voice or speaking speed:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --input transcript-tts.txt \
  --voice af_bella \
  --speed 1.1
```

## oMLX Setup

The script expects the oMLX macOS app and its bundled MLX audio runtime.
Download `mlx-community/Kokoro-82M-bf16` through oMLX before the first
narration. The script resolves the model from the directories in
`~/.omlx/settings.json`.

Use `--model` to select another model repository or an absolute local model
directory:

```bash
bash <skill-dir>/scripts/narrate.sh \
  --input notes-tts.txt \
  --model mlx-community/Kokoro-82M-bf16
```

## Gotchas

- Always narrate the TTS-friendly intermediate text, not the raw source, unless
  the user explicitly asks for a literal read.
- Run the script once with the complete document. Don't pre-split long input or
  loop over parts. Kokoro handles its fixed inference windows inside that
  invocation, and the script joins them before MP3 encoding.
- Kokoro doesn't accept a free-form narration style prompt. Adjust wording,
  punctuation, voice, and `--speed` in the TTS-friendly input instead.
- The default voice is `af_heart`.
- A short spoken disclosure is included in the same synthesis invocation by
  default. Only use `--no-disclaimer` when the user explicitly wants it omitted.
- Output defaults to `<input-stem>-<timestamp>.mp3` beside the input file. Use
  `--output` when the filename should be stable.

## Validation

If the run succeeds, the script prints the final path, size, and duration.
Confirm the file exists and use `ffprobe` to verify that its duration is greater
than zero.
