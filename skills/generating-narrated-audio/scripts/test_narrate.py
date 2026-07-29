from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Self
from unittest import mock

SCRIPT_PATH = Path(__file__).with_name("narrate.py")
MODULE_SPEC = importlib.util.spec_from_file_location("narrate", SCRIPT_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Could not load {SCRIPT_PATH}")
narrate = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules["narrate"] = narrate
MODULE_SPEC.loader.exec_module(narrate)


class FakeResponse:
    """Provides the context-manager behavior expected from urlopen."""

    def __init__(self, response_body: bytes) -> None:
        self.response_body = response_body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *unused: object) -> None:
        del unused

    def read(self) -> bytes:
        return self.response_body


class NarrateTests(unittest.TestCase):
    """Exercises provider-neutral chunking and ElevenLabs request behavior."""

    def test_build_chunks_preserves_paragraph_order(self) -> None:
        source = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

        chunks = narrate.build_chunks(source, maximum_characters=35)

        self.assertEqual(
            chunks,
            ["First paragraph.\n\nSecond paragraph.", "Third paragraph."],
        )

    def test_split_paragraph_keeps_chunks_within_limit(self) -> None:
        source = "One two three four five six seven eight nine ten."

        chunks = narrate.split_paragraph(source, maximum_characters=12)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 12 for chunk in chunks))
        self.assertEqual(" ".join(chunks), source)

    def test_split_paragraph_hard_splits_oversized_word(self) -> None:
        source = "abcdefghijklmnop"

        chunks = narrate.split_paragraph(source, maximum_characters=5)

        self.assertEqual(chunks, ["abcde", "fghij", "klmno", "p"])

    def test_gemini_cache_key_matches_legacy_script(self) -> None:
        with tempfile.TemporaryDirectory() as cache_directory:
            provider = narrate.GeminiProvider(
                model=narrate.DEFAULT_GEMINI_MODEL,
                voice=narrate.DEFAULT_GEMINI_VOICE,
                cache_dir=Path(cache_directory),
                api_key_op_path=None,
            )
            style = "Speak clearly."
            text = "Hello."
            styled_text = f"<style>{style}</style>\n\n{text}"
            material = (f"{provider.model}\0{provider.voice}\0{styled_text}").encode()
            expected_key = narrate.hashlib.sha256(material).hexdigest()[:24]

            cache_path = provider.cache_path(text, "", "", style)

            self.assertEqual(cache_path.name, f"{expected_key}.wav")

    def test_elevenlabs_cache_key_includes_neighboring_text(self) -> None:
        with tempfile.TemporaryDirectory() as cache_directory:
            provider = self.elevenlabs_provider(Path(cache_directory))

            first_path = provider.cache_path("Current", "Before", "After", "")
            second_path = provider.cache_path(
                "Current",
                "Different before",
                "After",
                "",
            )

            self.assertNotEqual(first_path, second_path)

    def test_elevenlabs_request_uses_voice_settings_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as cache_directory:
            provider = self.elevenlabs_provider(Path(cache_directory))
            captured_requests: list[urllib.request.Request] = []

            def fake_urlopen(
                request: urllib.request.Request,
                timeout: int,
            ) -> FakeResponse:
                self.assertEqual(timeout, 300)
                captured_requests.append(request)
                return FakeResponse(b"fake-mp3")

            with (
                mock.patch.object(
                    narrate.urllib.request,
                    "urlopen",
                    side_effect=fake_urlopen,
                ),
                redirect_stdout(io.StringIO()),
            ):
                result = provider.generate(
                    "Current", "Before", "After", "", "chunk-000"
                )

            self.assertEqual(result.read_bytes(), b"fake-mp3")
            self.assertEqual(len(captured_requests), 1)
            request = captured_requests[0]
            self.assertIn(
                narrate.DEFAULT_ELEVENLABS_VOICE,
                request.full_url,
            )
            self.assertEqual(request.get_header("Xi-api-key"), "secret")
            request_body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(request_body["text"], "Current")
            self.assertEqual(request_body["previous_text"], "Before")
            self.assertEqual(request_body["next_text"], "After")
            self.assertEqual(
                request_body["voice_settings"],
                {
                    "similarity_boost": 0.75,
                    "speed": 1.0,
                    "stability": 0.5,
                    "style": 0.0,
                    "use_speaker_boost": True,
                },
            )

    def test_op_reference_is_resolved_without_shell_interpolation(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["op"],
            returncode=0,
            stdout="resolved-secret\n",
            stderr="",
        )
        with (
            mock.patch.dict(
                narrate.os.environ,
                {"ELEVENLABS_API_KEY": "op://Vault/Item/Field"},
                clear=False,
            ),
            mock.patch.object(
                narrate,
                "require_command",
            ),
            mock.patch.object(
                narrate.subprocess,
                "run",
                return_value=completed,
            ) as run_mock,
        ):
            result = narrate.resolve_secret("ELEVENLABS_API_KEY", None)

        self.assertEqual(result, "resolved-secret")
        run_mock.assert_called_once_with(
            ["op", "read", "op://Vault/Item/Field"],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_elevenlabs_rejects_gemini_style_prompt(self) -> None:
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            narrate.parse_arguments(
                [
                    "--provider",
                    "elevenlabs",
                    "--style",
                    "Speak warmly.",
                    "input.txt",
                ]
            )

    def elevenlabs_provider(
        self,
        cache_directory: Path,
    ) -> narrate.ElevenLabsProvider:
        """Create a provider whose secret lookup cannot reach the network."""

        return narrate.ElevenLabsProvider(
            model=narrate.DEFAULT_ELEVENLABS_MODEL,
            voice=narrate.DEFAULT_ELEVENLABS_VOICE,
            cache_dir=cache_directory,
            api_key_op_path=None,
            voice_settings=narrate.ElevenLabsVoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                style=0.0,
                speed=1.0,
                use_speaker_boost=True,
            ),
            secret_loader=lambda environment_name, fallback: "secret",
        )


if __name__ == "__main__":
    unittest.main()
