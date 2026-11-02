from __future__ import annotations

import json
import subprocess
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "dist"
HOST = "127.0.0.1"
PORT = 8765
GENERATOR = ROOT / "generate_report.py"
MUTED_SLACK_CHANNELS_FILE = ROOT / "muted_slack_channels.json"


def load_muted_channels() -> list[str]:
    if not MUTED_SLACK_CHANNELS_FILE.exists():
        return []
    try:
        data = json.loads(MUTED_SLACK_CHANNELS_FILE.read_text())
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return sorted({item for item in data if isinstance(item, str) and item})


def save_muted_channels(channels: list[str]) -> None:
    MUTED_SLACK_CHANNELS_FILE.write_text(json.dumps(sorted(set(channels)), indent=2) + "\n")


def regenerate_report() -> None:
    subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=ROOT,
        check=True,
    )


class ReportHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/status":
            self._send_json(
                {
                    "status": "ok",
                    "muted_channels": load_muted_channels(),
                }
            )
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/mute":
            self._send_json(
                {
                    "status": "error",
                    "message": f"Unknown endpoint: {self.path}",
                },
                status=HTTPStatus.NOT_FOUND,
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            payload = json.loads(raw_body.decode("utf-8"))
            channel = payload.get("channel")
            if not isinstance(channel, str) or not channel.strip():
                raise ValueError("channel is required")

            muted_channels = load_muted_channels()
            if channel not in muted_channels:
                muted_channels.append(channel)
                save_muted_channels(muted_channels)
                regenerate_report()

            self._send_json(
                {
                    "status": "ok",
                    "channel": channel,
                    "muted_channels": sorted(set(muted_channels)),
                    "muted_count": len(set(muted_channels)),
                }
            )
        except Exception as exc:
            self._send_json(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ReportHandler)
    print(f"Serving report controls on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
