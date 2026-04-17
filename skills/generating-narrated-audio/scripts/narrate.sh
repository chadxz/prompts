#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DEFAULT_MODEL="gemini-2.5-pro-preview-tts"
DEFAULT_VOICE="Aoede"
DEFAULT_API_KEY_OP_PATH="op://Employee/Personal Gemini API Key/General/API Key"
DEFAULT_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/gemini-tts-audio"

DEFAULT_STYLE="$(
  cat <<'EOF'
You are narrating documentation written by a senior engineer for other
engineers at Convergint. Read it like a thoughtful walkthrough in a doc review
or a long Slack message, conversational but professional, direct, specific, and
a little brisk. Keep the delivery steady and easy to follow, but avoid
audiobook drama, marketing polish, announcer energy, or lecturer voice. Let
the prose sound like working engineers talking to each other, grounded,
plainspoken, and lightly understated. Keep contractions natural, treat headings
as quiet transitions, and move cleanly through the document without lingering
for effect. Pronounce acronyms and initialisms clearly, and assume the audience
already knows the stack, so do not sound like you are teaching basics.
Prioritize clarity, accuracy, and momentum. Do not sound rushed.
EOF
)"

DEFAULT_DISCLAIMER="$(
  cat <<'EOF'
[extremely fast] This audio was generated using Google Gemini 2.5 Pro Preview
TTS.
EOF
)"

usage() {
  cat <<EOF
Usage:
  $SCRIPT_NAME --input <file> [options]
  $SCRIPT_NAME <file> [options]

Generate a narrated MP3 from a text-like input file using Gemini TTS.

Options:
  -i, --input <file>          Input text or Markdown file
  -o, --output <file>         Output MP3 path
      --style <text>          Inline narration style override
      --style-file <file>     Read narration style from a file
      --voice <name>          Gemini prebuilt voice (default: $DEFAULT_VOICE)
      --model <name>          Gemini TTS model (default: $DEFAULT_MODEL)
      --disclaimer <text>     Spoken disclosure to prepend
      --no-disclaimer         Skip the spoken disclosure
      --cache-dir <dir>       Cache directory for intermediate WAVs
      --api-key-op-path <op>  1Password item path for GEMINI_API_KEY fallback
  -h, --help                  Show this help text

Behavior:
  - Uses GEMINI_API_KEY if it is already set.
  - Otherwise falls back to 1Password via --api-key-op-path.
  - If --output is omitted, writes <input-stem>-<timestamp>.mp3 beside
    the input file.
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

resolve_api_key() {
  if [ -n "${GEMINI_API_KEY:-}" ]; then
    if [[ "$GEMINI_API_KEY" == op://* ]]; then
      require_command op
      op read "$GEMINI_API_KEY" | tr -d '\r\n'
      return 0
    fi

    printf '%s' "$GEMINI_API_KEY"
    return 0
  fi

  require_command op
  local api_key
  api_key="$(op read "$API_KEY_OP_PATH" | tr -d '\r\n')"
  [ -n "$api_key" ] || die "Resolved GEMINI_API_KEY is empty"
  printf '%s' "$api_key"
}

INPUT=""
OUTPUT=""
STYLE="$DEFAULT_STYLE"
STYLE_FILE=""
VOICE="$DEFAULT_VOICE"
MODEL="$DEFAULT_MODEL"
DISCLAIMER="$DEFAULT_DISCLAIMER"
INCLUDE_DISCLAIMER=1
CACHE_DIR="$DEFAULT_CACHE_DIR"
API_KEY_OP_PATH="$DEFAULT_API_KEY_OP_PATH"

while [ $# -gt 0 ]; do
  case "$1" in
    -i|--input)
      [ $# -ge 2 ] || die "$1 requires a value"
      INPUT="$2"
      shift 2
      ;;
    -o|--output)
      [ $# -ge 2 ] || die "$1 requires a value"
      OUTPUT="$2"
      shift 2
      ;;
    --style)
      [ $# -ge 2 ] || die "$1 requires a value"
      STYLE="$2"
      STYLE_FILE=""
      shift 2
      ;;
    --style-file)
      [ $# -ge 2 ] || die "$1 requires a value"
      STYLE_FILE="$2"
      shift 2
      ;;
    --voice)
      [ $# -ge 2 ] || die "$1 requires a value"
      VOICE="$2"
      shift 2
      ;;
    --model)
      [ $# -ge 2 ] || die "$1 requires a value"
      MODEL="$2"
      shift 2
      ;;
    --disclaimer)
      [ $# -ge 2 ] || die "$1 requires a value"
      DISCLAIMER="$2"
      INCLUDE_DISCLAIMER=1
      shift 2
      ;;
    --no-disclaimer)
      INCLUDE_DISCLAIMER=0
      shift
      ;;
    --cache-dir)
      [ $# -ge 2 ] || die "$1 requires a value"
      CACHE_DIR="$2"
      shift 2
      ;;
    --api-key-op-path)
      [ $# -ge 2 ] || die "$1 requires a value"
      API_KEY_OP_PATH="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      die "Unknown option: $1"
      ;;
    *)
      if [ -z "$INPUT" ]; then
        INPUT="$1"
        shift
      else
        die "Unexpected argument: $1"
      fi
      ;;
  esac
done

[ -n "$INPUT" ] || die "Input file is required"
[ -f "$INPUT" ] || die "Input file not found: $INPUT"

if [ -n "$STYLE_FILE" ]; then
  [ -f "$STYLE_FILE" ] || die "Style file not found: $STYLE_FILE"
  STYLE="$(cat "$STYLE_FILE")"
fi

[ -n "$STYLE" ] || die "Narration style must not be empty"

require_command python3
require_command ffmpeg
require_command ffprobe

INPUT_DIR="$(cd "$(dirname "$INPUT")" && pwd)"
INPUT_NAME="$(basename "$INPUT")"
INPUT_STEM="${INPUT_NAME%.*}"

if [ -z "$OUTPUT" ]; then
  TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
  OUTPUT="$INPUT_DIR/${INPUT_STEM}-${TIMESTAMP}.mp3"
fi

mkdir -p "$(dirname "$OUTPUT")" "$CACHE_DIR"

WORK_DIR="$(mktemp -d -t narrated-audio.XXXXXX)"
cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

export GEMINI_API_KEY
GEMINI_API_KEY="$(resolve_api_key)"

echo "Input: $INPUT"
echo "Output: $OUTPUT"
echo "Model: $MODEL"
echo "Voice: $VOICE"
echo "Cache: $CACHE_DIR"
echo "Style: ${STYLE:0:80}..."
echo ""

python3 - "$STYLE" "$INPUT" "$OUTPUT" "$CACHE_DIR" "$MODEL" "$VOICE" \
  "$DISCLAIMER" "$INCLUDE_DISCLAIMER" "$WORK_DIR" <<'PYEOF'
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from typing import List

style = sys.argv[1]
input_path = sys.argv[2]
output_path = sys.argv[3]
cache_dir = sys.argv[4]
model = sys.argv[5]
voice = sys.argv[6]
disclaimer = sys.argv[7]
include_disclaimer = sys.argv[8] == "1"
work_dir = sys.argv[9]
api_key = os.environ["GEMINI_API_KEY"]

url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{model}:generateContent?key={api_key}"
)
max_chunk_chars = 2000


def cache_key(text: str) -> str:
    material = f"{model}\0{voice}\0{text}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as wav_file:
        return wav_file.getnframes() / float(wav_file.getframerate())


def split_paragraph(paragraph: str) -> List[str]:
    if len(paragraph) <= max_chunk_chars:
        return [paragraph]

    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    chunks: List[str] = []
    buffer = ""

    for sentence in sentences:
        if not sentence:
            continue

        if len(sentence) > max_chunk_chars:
            if buffer:
                chunks.append(buffer)
                buffer = ""

            words = sentence.split()
            word_buffer = ""
            for word in words:
                candidate = f"{word_buffer} {word}".strip()
                if len(candidate) <= max_chunk_chars:
                    word_buffer = candidate
                    continue

                if word_buffer:
                    chunks.append(word_buffer)
                word_buffer = word

            if word_buffer:
                chunks.append(word_buffer)
            continue

        candidate = f"{buffer} {sentence}".strip() if buffer else sentence
        if len(candidate) <= max_chunk_chars:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = sentence

    if buffer:
        chunks.append(buffer)

    return chunks


def build_chunks(text: str) -> List[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks: List[str] = []
    buffer = ""

    for paragraph in paragraphs:
        segments = split_paragraph(paragraph)
        if len(segments) > 1:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(segments)
            continue

        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= max_chunk_chars:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph

    if buffer:
        chunks.append(buffer)

    return chunks


def generate_audio(text: str, label: str, retries: int = 3) -> str | None:
    key = cache_key(text)
    cached_path = os.path.join(cache_dir, f"{key}.wav")
    if os.path.exists(cached_path):
        duration = wav_duration(cached_path)
        print(f"  {label}: {duration:.1f}s (cached)")
        return cached_path

    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice,
                        }
                    }
                },
            },
        }
    ).encode("utf-8")

    data = None
    for attempt in range(retries):
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except (urllib.error.HTTPError, TimeoutError, OSError) as exc:
            message = str(exc)
            if hasattr(exc, "read"):
                message = exc.read().decode("utf-8")[:200]
            if attempt < retries - 1:
                wait_seconds = (attempt + 1) * 15
                print(
                    f"    retry in {wait_seconds}s ({message})...",
                    flush=True,
                )
                time.sleep(wait_seconds)
            else:
                print(f"    FAILED after {retries} attempts ({message})")
                return None

    if not data:
        return None

    for candidate in data.get("candidates", []):
        parts = candidate.get("content", {}).get("parts", [])
        for part in parts:
            inline = part.get("inlineData")
            if not inline:
                continue
            audio_data = base64.b64decode(inline["data"])
            with wave.open(cached_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(audio_data)
            duration = len(audio_data) / (24000 * 2)
            print(f"  {label}: {duration:.1f}s")
            return cached_path

    return None


with open(input_path, "r", encoding="utf-8") as handle:
    full_text = handle.read().strip()

if not full_text:
    print("Error: input file is empty")
    sys.exit(1)

chunks = build_chunks(full_text)
wav_files: List[str] = []

if include_disclaimer:
    print("Generating disclaimer...")
    disclaimer_wav = generate_audio(disclaimer, "disclaimer")
    if disclaimer_wav:
        wav_files.append(disclaimer_wav)

cached_count = sum(
    1
    for chunk in chunks
    if os.path.exists(
        os.path.join(
            cache_dir,
            f"{cache_key(f'<style>{style}</style>\\n\\n{chunk}')}.wav",
        )
    )
)
print(
    "Generating main content: "
    f"{len(chunks)} chunks ({cached_count} cached, "
    f"{len(chunks) - cached_count} to generate)\n"
)

failed_chunks: List[int] = []
for index, chunk in enumerate(chunks, start=1):
    styled_text = f"<style>{style}</style>\n\n{chunk}"
    print(
        f"  Chunk {index}/{len(chunks)} ({len(chunk)} chars)...",
        end=" ",
        flush=True,
    )
    wav_path = generate_audio(styled_text, f"chunk-{index - 1:03d}")
    if wav_path:
        wav_files.append(wav_path)
    else:
        failed_chunks.append(index)

if failed_chunks:
    print(
        "\nWarning: chunks "
        f"{failed_chunks} failed. Re-run the same command to retry them."
    )

main_chunk_count = len(wav_files) - (1 if include_disclaimer and wav_files else 0)
if main_chunk_count <= 0:
    print("Error: no main audio was generated")
    sys.exit(1)

concat_path = os.path.join(work_dir, "concat.txt")
with open(concat_path, "w", encoding="utf-8") as handle:
    for wav_path in wav_files:
        escaped_path = wav_path.replace("'", "'\\''")
        handle.write(f"file '{escaped_path}'\n")

print(f"\nConcatenating {len(wav_files)} parts and encoding to MP3...")
ffmpeg_result = subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_path,
        "-b:a",
        "128k",
        output_path,
    ],
    capture_output=True,
    text=True,
)
if ffmpeg_result.returncode != 0:
    print(ffmpeg_result.stderr.strip())
    sys.exit(ffmpeg_result.returncode)

probe_result = subprocess.run(
    [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        output_path,
    ],
    capture_output=True,
    text=True,
)
if probe_result.returncode != 0:
    print(probe_result.stderr.strip())
    sys.exit(probe_result.returncode)

duration_seconds = int(float(probe_result.stdout.strip()))
minutes = duration_seconds // 60
seconds = duration_seconds % 60
size_kib = os.path.getsize(output_path) // 1024

print(
    f"\nDone! {output_path} ({size_kib}K, {minutes}m {seconds}s)"
)
if failed_chunks:
    print(f"Note: {len(failed_chunks)} chunk(s) are still missing.")
PYEOF
