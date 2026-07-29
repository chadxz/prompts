from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_PROVIDER = "gemini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-pro-preview-tts"
DEFAULT_GEMINI_VOICE = "Aoede"
DEFAULT_GEMINI_API_KEY_OP_PATH = "op://Employee/Personal Gemini API Key/General/API Key"
DEFAULT_ELEVENLABS_MODEL = "eleven_multilingual_v2"
DEFAULT_ELEVENLABS_VOICE = "yj30vwTGJxSHezdAGsv9"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
MAX_CHUNK_CHARACTERS = 2000

DEFAULT_GEMINI_STYLE = """\
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
Prioritize clarity, accuracy, and momentum. Do not sound rushed."""

DEFAULT_GEMINI_DISCLAIMER = """\
[extremely fast] This audio was generated using Google Gemini 2.5 Pro Preview
TTS."""

DEFAULT_ELEVENLABS_DISCLAIMER = """\
This audio was generated using ElevenLabs text to speech."""


class NarrationError(RuntimeError):
    """Reports an expected narration failure without a Python traceback."""


@dataclass(frozen=True)
class ElevenLabsVoiceSettings:
    """Captures deterministic ElevenLabs voice settings used in every chunk."""

    stability: float
    similarity_boost: float
    style: float
    speed: float
    use_speaker_boost: bool

    def as_request(self) -> dict[str, float | bool]:
        """Return the ElevenLabs API representation of these settings."""

        return {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "style": self.style,
            "speed": self.speed,
            "use_speaker_boost": self.use_speaker_boost,
        }


class TtsProvider(Protocol):
    """Defines the provider operations used by the narration coordinator."""

    name: str
    model: str
    voice: str

    def cache_path(
        self,
        text: str,
        previous_text: str,
        next_text: str,
        narration_style: str,
    ) -> Path:
        """Return the cache path for one exact provider request."""

    def generate(
        self,
        text: str,
        previous_text: str,
        next_text: str,
        narration_style: str,
        label: str,
    ) -> Path:
        """Generate or reuse one audio chunk and return its local path."""


def parse_arguments(arguments: Sequence[str]) -> argparse.Namespace:
    """Parse the stable narration CLI and provider-specific controls."""

    parser = argparse.ArgumentParser(
        description="Generate a narrated MP3 from a text or Markdown file."
    )
    parser.add_argument("positional_input", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("-i", "--input", dest="input_file")
    parser.add_argument("-o", "--output")
    parser.add_argument(
        "--provider",
        choices=("gemini", "elevenlabs"),
        default=DEFAULT_PROVIDER,
        help="TTS provider (default: gemini)",
    )
    parser.add_argument("--style", help="Gemini narration style override")
    parser.add_argument(
        "--style-file",
        help="Read a Gemini narration style from a file",
    )
    parser.add_argument(
        "--voice",
        help="Provider voice name or ID",
    )
    parser.add_argument(
        "--model",
        help="Provider TTS model",
    )
    parser.add_argument(
        "--disclaimer",
        help="Spoken disclosure to prepend",
    )
    parser.add_argument(
        "--no-disclaimer",
        action="store_true",
        help="Skip the spoken disclosure",
    )
    parser.add_argument(
        "--cache-dir",
        help="Cache directory for generated chunks",
    )
    parser.add_argument(
        "--api-key-op-path",
        help="1Password reference used when the provider key is unset",
    )
    parser.add_argument(
        "--stability",
        type=float,
        default=0.5,
        help="ElevenLabs stability from 0 to 1 (default: 0.5)",
    )
    parser.add_argument(
        "--similarity-boost",
        type=float,
        default=0.75,
        help="ElevenLabs similarity from 0 to 1 (default: 0.75)",
    )
    parser.add_argument(
        "--style-exaggeration",
        type=float,
        default=0.0,
        help="ElevenLabs style exaggeration from 0 to 1 (default: 0)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="ElevenLabs speed from 0.7 to 1.2 (default: 1)",
    )
    parser.add_argument(
        "--speaker-boost",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable ElevenLabs speaker boost (default: enabled)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the planned requests without generating audio",
    )

    parsed = parser.parse_args(arguments)
    if parsed.input_file and parsed.positional_input:
        parser.error("provide the input either positionally or with --input")
    parsed.input_file = parsed.input_file or parsed.positional_input
    if not parsed.input_file:
        parser.error("input file is required")
    if parsed.style and parsed.style_file:
        parser.error("--style and --style-file cannot be used together")
    if parsed.provider == "elevenlabs" and (parsed.style or parsed.style_file):
        parser.error(
            "--style and --style-file are Gemini-only; use ElevenLabs voice "
            "settings instead"
        )

    validate_range(parser, "--stability", parsed.stability, 0.0, 1.0)
    validate_range(
        parser,
        "--similarity-boost",
        parsed.similarity_boost,
        0.0,
        1.0,
    )
    validate_range(
        parser,
        "--style-exaggeration",
        parsed.style_exaggeration,
        0.0,
        1.0,
    )
    validate_range(parser, "--speed", parsed.speed, 0.7, 1.2)
    return parsed


def validate_range(
    parser: argparse.ArgumentParser,
    option: str,
    value: float,
    minimum: float,
    maximum: float,
) -> None:
    """Reject a numeric CLI option outside its provider-supported range."""

    if not minimum <= value <= maximum:
        parser.error(f"{option} must be between {minimum} and {maximum}")


def require_command(command_name: str) -> None:
    """Fail with a concise message when a required executable is unavailable."""

    if not shutil.which(command_name):
        raise NarrationError(f"Required command not found: {command_name}")


def resolve_secret(
    environment_name: str,
    fallback_op_reference: str | None,
) -> str:
    """Resolve a literal API key or an op reference without logging either."""

    secret_reference = os.environ.get(environment_name) or fallback_op_reference
    if not secret_reference:
        raise NarrationError(
            f"{environment_name} is unset and no 1Password reference was provided"
        )
    if not secret_reference.startswith("op://"):
        return secret_reference

    require_command("op")
    result = subprocess.run(
        ["op", "read", secret_reference],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "1Password returned no details"
        raise NarrationError(
            f"Could not resolve {environment_name} from 1Password: {detail}"
        )
    secret = result.stdout.strip()
    if not secret:
        raise NarrationError(f"Resolved {environment_name} is empty")
    return secret


def default_cache_dir(provider_name: str) -> Path:
    """Return a provider-specific cache while preserving Gemini's old path."""

    cache_root = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    if provider_name == "gemini":
        return cache_root / "gemini-tts-audio"
    return cache_root / "elevenlabs-tts-audio"


def read_narration_style(parsed: argparse.Namespace) -> str:
    """Load the Gemini style override or return the built-in default."""

    if parsed.provider != "gemini":
        return ""
    if parsed.style_file:
        style_file = Path(parsed.style_file)
        if not style_file.is_file():
            raise NarrationError(f"Style file not found: {style_file}")
        narration_style = style_file.read_text(encoding="utf-8").strip()
    else:
        narration_style = parsed.style or DEFAULT_GEMINI_STYLE
    if not narration_style:
        raise NarrationError("Narration style must not be empty")
    return narration_style


def split_paragraph(
    paragraph: str,
    maximum_characters: int = MAX_CHUNK_CHARACTERS,
) -> list[str]:
    """Split one oversized paragraph at sentence and then word boundaries."""

    if len(paragraph) <= maximum_characters:
        return [paragraph]

    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    chunks: list[str] = []
    buffer = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > maximum_characters:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            word_buffer = ""
            for word in sentence.split():
                if len(word) > maximum_characters:
                    if word_buffer:
                        chunks.append(word_buffer)
                        word_buffer = ""
                    chunks.extend(
                        word[offset : offset + maximum_characters]
                        for offset in range(0, len(word), maximum_characters)
                    )
                    continue
                candidate = f"{word_buffer} {word}".strip()
                if len(candidate) <= maximum_characters:
                    word_buffer = candidate
                    continue
                if word_buffer:
                    chunks.append(word_buffer)
                word_buffer = word
            if word_buffer:
                chunks.append(word_buffer)
            continue

        candidate = f"{buffer} {sentence}".strip() if buffer else sentence
        if len(candidate) <= maximum_characters:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = sentence

    if buffer:
        chunks.append(buffer)
    return chunks


def build_chunks(
    text: str,
    maximum_characters: int = MAX_CHUNK_CHARACTERS,
) -> list[str]:
    """Build paragraph-aware chunks small enough for either provider."""

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n+", text)
        if paragraph.strip()
    ]
    chunks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        segments = split_paragraph(paragraph, maximum_characters)
        if len(segments) > 1:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(segments)
            continue

        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= maximum_characters:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph

    if buffer:
        chunks.append(buffer)
    return chunks


def write_atomically(destination: Path, audio_data: bytes) -> None:
    """Write a complete cache entry before making it visible to later runs."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
    )
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(audio_data)
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def request_bytes(
    request: urllib.request.Request,
    label: str,
    retries: int = 3,
) -> bytes:
    """Execute an HTTP request with bounded retries and safe error reporting."""

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            response_body = error.read().decode("utf-8", errors="replace")[:300]
            retriable = error.code == 429 or error.code >= 500
            if not retriable or attempt == retries - 1:
                raise NarrationError(
                    f"{label} failed with HTTP {error.code}: {response_body}"
                ) from error
            retry_after = error.headers.get("Retry-After")
            delay = (
                float(retry_after)
                if retry_after and retry_after.replace(".", "", 1).isdigit()
                else float((attempt + 1) * 15)
            )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if attempt == retries - 1:
                detail = getattr(error, "reason", str(error))
                raise NarrationError(f"{label} failed: {detail}") from error
            delay = float((attempt + 1) * 15)

        print(f"retry in {delay:g}s...", flush=True)
        time.sleep(delay)

    raise NarrationError(f"{label} failed without a response")


class GeminiProvider:
    """Implements the existing Gemini TTS behavior behind a provider boundary."""

    name = "gemini"

    def __init__(
        self,
        model: str,
        voice: str,
        cache_dir: Path,
        api_key_op_path: str | None,
        secret_loader: Callable[[str, str | None], str] = resolve_secret,
    ) -> None:
        self.model = model
        self.voice = voice
        self.cache_dir = cache_dir
        self.api_key_op_path = api_key_op_path or DEFAULT_GEMINI_API_KEY_OP_PATH
        self.secret_loader = secret_loader
        self._api_key: str | None = None

    def styled_text(self, text: str, narration_style: str) -> str:
        """Reproduce the exact prompt envelope used by the original script."""

        if not narration_style:
            return text
        return f"<style>{narration_style}</style>\n\n{text}"

    def cache_path(
        self,
        text: str,
        previous_text: str,
        next_text: str,
        narration_style: str,
    ) -> Path:
        """Return the legacy-compatible Gemini WAV cache path."""

        del previous_text, next_text
        styled_text = self.styled_text(text, narration_style)
        material = f"{self.model}\0{self.voice}\0{styled_text}".encode()
        cache_key = hashlib.sha256(material).hexdigest()[:24]
        return self.cache_dir / f"{cache_key}.wav"

    def api_key(self) -> str:
        """Resolve and memoize the Gemini API key only when a request is needed."""

        if self._api_key is None:
            self._api_key = self.secret_loader(
                "GEMINI_API_KEY",
                self.api_key_op_path,
            )
        return self._api_key

    def generate(
        self,
        text: str,
        previous_text: str,
        next_text: str,
        narration_style: str,
        label: str,
    ) -> Path:
        """Generate one Gemini PCM response and store it as a WAV cache entry."""

        cached_path = self.cache_path(
            text,
            previous_text,
            next_text,
            narration_style,
        )
        if cached_path.exists():
            print(f"{label}: cached")
            return cached_path

        payload = json.dumps(
            {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": self.styled_text(
                                    text,
                                    narration_style,
                                )
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": self.voice,
                            }
                        }
                    },
                },
            }
        ).encode("utf-8")
        encoded_model = urllib.parse.quote(self.model, safe="")
        encoded_key = urllib.parse.quote(self.api_key(), safe="")
        request = urllib.request.Request(
            (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{encoded_model}:generateContent?key={encoded_key}"
            ),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            response_data = json.loads(request_bytes(request, label).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NarrationError(
                f"{label} returned an invalid Gemini response"
            ) from error
        audio_data = extract_gemini_audio(response_data)
        write_pcm_wav(cached_path, audio_data)
        print(f"{label}: generated")
        return cached_path


def extract_gemini_audio(response_data: dict[str, object]) -> bytes:
    """Extract the first inline audio payload from a Gemini response."""

    for candidate in response_data.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content", {})
        if not isinstance(content, dict):
            continue
        for part in content.get("parts", []):
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData")
            if isinstance(inline_data, dict) and inline_data.get("data"):
                try:
                    return base64.b64decode(
                        str(inline_data["data"]),
                        validate=True,
                    )
                except (ValueError, binascii.Error) as error:
                    raise NarrationError(
                        "Gemini returned invalid inline audio"
                    ) from error
    raise NarrationError("Gemini returned no inline audio")


def write_pcm_wav(destination: Path, audio_data: bytes) -> None:
    """Wrap Gemini's mono 24 kHz 16-bit PCM response in a WAV container."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
    )
    os.close(file_descriptor)
    try:
        with wave.open(temporary_name, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(audio_data)
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


class ElevenLabsProvider:
    """Generates ElevenLabs MP3 chunks with continuity-aware cache keys."""

    name = "elevenlabs"

    def __init__(
        self,
        model: str,
        voice: str,
        cache_dir: Path,
        api_key_op_path: str | None,
        voice_settings: ElevenLabsVoiceSettings,
        secret_loader: Callable[[str, str | None], str] = resolve_secret,
    ) -> None:
        self.model = model
        self.voice = voice
        self.cache_dir = cache_dir
        self.api_key_op_path = api_key_op_path
        self.voice_settings = voice_settings
        self.secret_loader = secret_loader
        self._api_key: str | None = None

    def cache_path(
        self,
        text: str,
        previous_text: str,
        next_text: str,
        narration_style: str,
    ) -> Path:
        """Return a cache path covering every input that can affect the audio."""

        del narration_style
        material = json.dumps(
            {
                "provider": self.name,
                "model": self.model,
                "voice": self.voice,
                "output_format": DEFAULT_OUTPUT_FORMAT,
                "voice_settings": self.voice_settings.as_request(),
                "text": text,
                "previous_text": previous_text,
                "next_text": next_text,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        cache_key = hashlib.sha256(material).hexdigest()[:24]
        return self.cache_dir / f"{cache_key}.mp3"

    def api_key(self) -> str:
        """Resolve the ElevenLabs key or op reference only for a cache miss."""

        if self._api_key is None:
            self._api_key = self.secret_loader(
                "ELEVENLABS_API_KEY",
                self.api_key_op_path,
            )
        return self._api_key

    def generate(
        self,
        text: str,
        previous_text: str,
        next_text: str,
        narration_style: str,
        label: str,
    ) -> Path:
        """Generate one ElevenLabs chunk with neighboring text for continuity."""

        cached_path = self.cache_path(
            text,
            previous_text,
            next_text,
            narration_style,
        )
        if cached_path.exists():
            print(f"{label}: cached")
            return cached_path

        request_body: dict[str, object] = {
            "text": text,
            "model_id": self.model,
            "voice_settings": self.voice_settings.as_request(),
            "apply_text_normalization": "auto",
        }
        if previous_text:
            request_body["previous_text"] = previous_text
        if next_text:
            request_body["next_text"] = next_text

        encoded_voice = urllib.parse.quote(self.voice, safe="")
        request = urllib.request.Request(
            (
                "https://api.elevenlabs.io/v1/text-to-speech/"
                f"{encoded_voice}?output_format={DEFAULT_OUTPUT_FORMAT}"
            ),
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "xi-api-key": self.api_key(),
            },
        )
        audio_data = request_bytes(request, label)
        if not audio_data:
            raise NarrationError(f"{label} returned empty audio")
        write_atomically(cached_path, audio_data)
        print(f"{label}: generated")
        return cached_path


def create_provider(
    parsed: argparse.Namespace,
    cache_dir: Path,
) -> TtsProvider:
    """Create the selected provider using provider-specific defaults."""

    if parsed.provider == "gemini":
        return GeminiProvider(
            model=parsed.model or DEFAULT_GEMINI_MODEL,
            voice=parsed.voice or DEFAULT_GEMINI_VOICE,
            cache_dir=cache_dir,
            api_key_op_path=parsed.api_key_op_path,
        )

    voice_settings = ElevenLabsVoiceSettings(
        stability=parsed.stability,
        similarity_boost=parsed.similarity_boost,
        style=parsed.style_exaggeration,
        speed=parsed.speed,
        use_speaker_boost=parsed.speaker_boost,
    )
    return ElevenLabsProvider(
        model=parsed.model or DEFAULT_ELEVENLABS_MODEL,
        voice=parsed.voice or DEFAULT_ELEVENLABS_VOICE,
        cache_dir=cache_dir,
        api_key_op_path=parsed.api_key_op_path,
        voice_settings=voice_settings,
    )


def default_disclaimer(provider_name: str) -> str:
    """Return the provider-specific disclosure prepended by default."""

    if provider_name == "gemini":
        return DEFAULT_GEMINI_DISCLAIMER
    return DEFAULT_ELEVENLABS_DISCLAIMER


def chunk_context(chunks: Sequence[str], index: int) -> tuple[str, str]:
    """Return adjacent chunk text used to preserve ElevenLabs continuity."""

    previous_text = chunks[index - 1] if index > 0 else ""
    next_text = chunks[index + 1] if index + 1 < len(chunks) else ""
    return previous_text, next_text


def concatenate_audio(audio_paths: Sequence[Path], output_path: Path) -> None:
    """Concatenate cached provider chunks and encode the final MP3."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="narrated-audio.") as work_dir:
        concat_path = Path(work_dir) / "concat.txt"
        entries = []
        for audio_path in audio_paths:
            escaped_path = str(audio_path).replace("'", "'\\''")
            entries.append(f"file '{escaped_path}'")
        concat_path.write_text("\n".join(entries) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-b:a",
                "128k",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            output_path.unlink(missing_ok=True)
            raise NarrationError(
                f"ffmpeg could not assemble the narration: {result.stderr.strip()}"
            )


def probe_audio(output_path: Path) -> tuple[int, int]:
    """Return the verified duration in seconds and file size in KiB."""

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise NarrationError(
            f"ffprobe could not verify the narration: {result.stderr.strip()}"
        )
    try:
        duration = float(result.stdout.strip())
    except ValueError as error:
        raise NarrationError("ffprobe returned an invalid duration") from error
    if duration <= 0:
        raise NarrationError("generated narration has zero duration")
    duration_seconds = max(1, int(duration))
    return duration_seconds, output_path.stat().st_size // 1024


def choose_output_path(input_path: Path, requested_output: str | None) -> Path:
    """Resolve an explicit output or create the legacy timestamped filename."""

    if requested_output:
        return Path(requested_output).expanduser().resolve()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return input_path.parent / f"{input_path.stem}-{timestamp}.mp3"


def report_plan(
    input_path: Path,
    output_path: Path,
    provider: TtsProvider,
    cache_dir: Path,
    chunks: Sequence[str],
    narration_style: str,
    include_disclaimer: bool,
) -> None:
    """Print the exact provider plan without revealing credentials."""

    cached_count = 0
    for index, chunk in enumerate(chunks):
        previous_text, next_text = chunk_context(chunks, index)
        if provider.cache_path(
            chunk,
            previous_text,
            next_text,
            narration_style,
        ).exists():
            cached_count += 1

    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Provider: {provider.name}")
    print(f"Model: {provider.model}")
    print(f"Voice: {provider.voice}")
    print(f"Cache: {cache_dir}")
    if narration_style:
        single_line_style = " ".join(narration_style.split())
        print(f"Style: {single_line_style[:80]}...")
    print(f"Chunks: {len(chunks)} ({cached_count} cached)")
    print(f"Input characters: {sum(len(chunk) for chunk in chunks)}")
    print(f"Disclosure: {'included' if include_disclaimer else 'omitted'}")


def run(arguments: Sequence[str]) -> Path | None:
    """Coordinate validation, chunk generation, assembly, and verification."""

    parsed = parse_arguments(arguments)
    input_path = Path(parsed.input_file).expanduser().resolve()
    if not input_path.is_file():
        raise NarrationError(f"Input file not found: {input_path}")

    try:
        full_text = input_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise NarrationError(f"Could not read input file: {error}") from error
    if not full_text:
        raise NarrationError("Input file is empty")
    chunks = build_chunks(full_text)
    if not chunks:
        raise NarrationError("Input file contains no narratable text")

    narration_style = read_narration_style(parsed)
    cache_dir = (
        Path(parsed.cache_dir).expanduser().resolve()
        if parsed.cache_dir
        else default_cache_dir(parsed.provider)
    )
    output_path = choose_output_path(input_path, parsed.output)
    if output_path == input_path:
        raise NarrationError("Output path must not overwrite the input file")
    provider = create_provider(parsed, cache_dir)
    include_disclaimer = not parsed.no_disclaimer

    report_plan(
        input_path,
        output_path,
        provider,
        cache_dir,
        chunks,
        narration_style,
        include_disclaimer,
    )
    if parsed.dry_run:
        print("Dry run complete; no audio was generated.")
        return None

    require_command("ffmpeg")
    require_command("ffprobe")
    cache_dir.mkdir(parents=True, exist_ok=True)

    audio_paths: list[Path] = []
    if include_disclaimer:
        disclaimer = parsed.disclaimer or default_disclaimer(provider.name)
        print("Generating disclosure...")
        audio_paths.append(
            provider.generate(
                disclaimer,
                "",
                "",
                "",
                "disclosure",
            )
        )

    print("Generating main content...")
    for index, chunk in enumerate(chunks):
        previous_text, next_text = chunk_context(chunks, index)
        print(
            f"chunk {index + 1}/{len(chunks)} ({len(chunk)} characters): ",
            end="",
            flush=True,
        )
        audio_paths.append(
            provider.generate(
                chunk,
                previous_text,
                next_text,
                narration_style,
                f"chunk-{index:03d}",
            )
        )

    print(f"Concatenating {len(audio_paths)} parts and encoding to MP3...")
    concatenate_audio(audio_paths, output_path)
    duration_seconds, size_kib = probe_audio(output_path)
    minutes, seconds = divmod(duration_seconds, 60)
    print(f"Done! {output_path} ({size_kib}K, {minutes}m {seconds}s)")
    return output_path


def main() -> int:
    """Run the CLI and present expected failures without a traceback."""

    try:
        run(sys.argv[1:])
    except NarrationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
