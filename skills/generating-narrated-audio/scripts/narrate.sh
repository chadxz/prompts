#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DEFAULT_MODEL="mlx-community/Kokoro-82M-bf16"
DEFAULT_VOICE="af_heart"
DEFAULT_SPEED="1.0"
DEFAULT_DISCLAIMER="This audio was generated locally using Kokoro text to speech."

usage() {
  cat <<EOF
Usage:
  $SCRIPT_NAME --input <file> [options]
  $SCRIPT_NAME <file> [options]

Generate one narrated MP3 from a text-like input file using Kokoro through
oMLX's bundled MLX audio runtime.

Options:
  -i, --input <file>       Input text or Markdown file
  -o, --output <file>      Output MP3 path
      --voice <name>       Kokoro voice (default: $DEFAULT_VOICE)
      --model <repo|dir>   oMLX model repo or local directory
                           (default: $DEFAULT_MODEL)
      --speed <number>     Speaking speed (default: $DEFAULT_SPEED)
      --disclaimer <text>  Spoken disclosure to prepend
      --no-disclaimer      Skip the spoken disclosure
  -h, --help               Show this help text

Behavior:
  - Reads the complete input in one synthesis invocation.
  - Resolves the model from oMLX's configured model directories.
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

resolve_model_location() {
  local requested_model="$1"
  local settings_file="${OMLX_BASE_DIR:-$HOME/.omlx}/settings.json"
  local model_root
  local candidate_model

  if [ -d "$requested_model" ]; then
    printf '%s' "$requested_model"
    return 0
  fi

  if [ -f "$settings_file" ]; then
    require_command jq
    while IFS= read -r model_root; do
      [ -n "$model_root" ] || continue
      candidate_model="$model_root/$requested_model"
      if [ -d "$candidate_model" ]; then
        printf '%s' "$candidate_model"
        return 0
      fi
    done < <(
      jq -r '
        .model.model_dirs[]?,
        .model.model_dir?
        | select(type == "string" and length > 0)
      ' "$settings_file"
    )
  fi

  for model_root in "$HOME/.omlx/models" "$HOME/.lmstudio/models"; do
    candidate_model="$model_root/$requested_model"
    if [ -d "$candidate_model" ]; then
      printf '%s' "$candidate_model"
      return 0
    fi
  done

  die "Model not found in oMLX: $requested_model"
}

INPUT_FILE=""
OUTPUT_FILE=""
VOICE="$DEFAULT_VOICE"
MODEL="$DEFAULT_MODEL"
SPEED="$DEFAULT_SPEED"
DISCLAIMER="$DEFAULT_DISCLAIMER"
INCLUDE_DISCLAIMER=1

while [ $# -gt 0 ]; do
  case "$1" in
    -i|--input)
      [ $# -ge 2 ] || die "$1 requires a value"
      INPUT_FILE="$2"
      shift 2
      ;;
    -o|--output)
      [ $# -ge 2 ] || die "$1 requires a value"
      OUTPUT_FILE="$2"
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
    --speed)
      [ $# -ge 2 ] || die "$1 requires a value"
      SPEED="$2"
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
      if [ -z "$INPUT_FILE" ]; then
        INPUT_FILE="$1"
        shift
      else
        die "Unexpected argument: $1"
      fi
      ;;
  esac
done

[ -n "$INPUT_FILE" ] || die "Input file is required"
[ -f "$INPUT_FILE" ] || die "Input file not found: $INPUT_FILE"
[ -s "$INPUT_FILE" ] || die "Input file is empty: $INPUT_FILE"

require_command omlx
require_command realpath
require_command ffmpeg
require_command ffprobe

OMLX_EXECUTABLE="$(realpath "$(command -v omlx)")"
OMLX_CONTENTS_DIR="$(cd "$(dirname "$OMLX_EXECUTABLE")/.." && pwd)"
OMLX_RESOURCES_DIR="$OMLX_CONTENTS_DIR/Resources"
OMLX_PYTHON_HOME="$OMLX_RESOURCES_DIR/Python/cpython-3.11"
OMLX_MLX_SITE="$OMLX_RESOURCES_DIR/Python/framework-mlx-base/lib/python3.11/site-packages"
OMLX_PYTHON="$OMLX_PYTHON_HOME/bin/python3"

[ -x "$OMLX_PYTHON" ] || die "Could not locate oMLX's Python runtime"
[ -d "$OMLX_MLX_SITE/mlx_audio" ] || die "oMLX does not include MLX audio"

MODEL_LOCATION="$(resolve_model_location "$MODEL")"
VOICE_LOCATION="$VOICE"
if [[ "$VOICE" != *.safetensors ]]; then
  LOCAL_VOICE_FILE="$MODEL_LOCATION/voices/$VOICE.safetensors"
  if [ -f "$LOCAL_VOICE_FILE" ]; then
    VOICE_LOCATION="$LOCAL_VOICE_FILE"
  fi
fi

INPUT_DIR="$(cd "$(dirname "$INPUT_FILE")" && pwd)"
INPUT_NAME="$(basename "$INPUT_FILE")"
INPUT_STEM="${INPUT_NAME%.*}"

if [ -z "$OUTPUT_FILE" ]; then
  TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
  OUTPUT_FILE="$INPUT_DIR/${INPUT_STEM}-${TIMESTAMP}.mp3"
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"

WORK_DIR="$(mktemp -d -t narrated-audio.XXXXXX)"
cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

WAV_FILE="$WORK_DIR/narration.wav"
OMLX_PYTHON_PATH="$OMLX_RESOURCES_DIR:$OMLX_MLX_SITE"
if [ -n "${PYTHONPATH:-}" ]; then
  OMLX_PYTHON_PATH="$OMLX_PYTHON_PATH:$PYTHONPATH"
fi

run_kokoro() {
  env \
    PYTHONHOME="$OMLX_PYTHON_HOME" \
    PYTHONPATH="$OMLX_PYTHON_PATH" \
    "$OMLX_PYTHON" -m mlx_audio.tts.generate \
      --model "$MODEL_LOCATION" \
      --voice "$VOICE_LOCATION" \
      --speed "$SPEED" \
      --lang_code a \
      --output_path "$WORK_DIR" \
      --file_prefix narration \
      --audio_format wav \
      --join_audio
}

echo "Input: $INPUT_FILE"
echo "Output: $OUTPUT_FILE"
echo "Model: $MODEL_LOCATION"
echo "Voice: $VOICE"
echo "Speed: ${SPEED}x"
echo "Mode: one synthesis invocation"
echo ""

if [ "$INCLUDE_DISCLAIMER" -eq 1 ]; then
  {
    printf '%s\n\n' "$DISCLAIMER"
    tr '\r\n' '  ' < "$INPUT_FILE"
  } | run_kokoro
else
  tr '\r\n' '  ' < "$INPUT_FILE" | run_kokoro
fi

[ -s "$WAV_FILE" ] || die "Kokoro did not produce audio"

ffmpeg \
  -hide_banner \
  -loglevel error \
  -y \
  -i "$WAV_FILE" \
  -b:a 128k \
  "$OUTPUT_FILE"

[ -s "$OUTPUT_FILE" ] || die "MP3 output is empty"

DURATION_SECONDS="$(
  ffprobe \
    -v quiet \
    -show_entries format=duration \
    -of csv=p=0 \
    "$OUTPUT_FILE"
)"
[ -n "$DURATION_SECONDS" ] || die "Could not determine MP3 duration"

DURATION_WHOLE_SECONDS="${DURATION_SECONDS%.*}"
MINUTES=$((DURATION_WHOLE_SECONDS / 60))
SECONDS=$((DURATION_WHOLE_SECONDS % 60))
SIZE_KIB="$(du -k "$OUTPUT_FILE" | cut -f1)"

echo ""
echo "Done! $OUTPUT_FILE (${SIZE_KIB}K, ${MINUTES}m ${SECONDS}s)"
