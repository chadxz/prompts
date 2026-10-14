#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Compact large, idle desktop chats before their prompt cache expires."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import select
import shlex
import shutil
import socket
import sqlite3
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

EVENTS = (
    "Stop",
    "UserPromptSubmit",
    "SessionStart",
    "PreCompact",
    "SessionEnd",
    "Interrupt",
)
SCRIPT = Path(__file__).resolve()
MAX_FRAME = 8 * 1024 * 1024
SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


@dataclass(frozen=True)
class Settings:
    """Keep the idle deadline inside the newer models' 30-minute cache window."""

    enabled: bool = True
    idle_seconds: int = 1200
    max_cache_age_seconds: int = 1500
    min_context_tokens: int = 200_000

    @classmethod
    def load(cls, codex_dir: Path) -> Settings:
        file_path = codex_dir / "idle-compaction.json"
        settings = (
            cls(**json.loads(file_path.read_text())) if file_path.exists() else cls()
        )
        if type(settings.enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        for name in ("idle_seconds", "max_cache_age_seconds", "min_context_tokens"):
            if type(getattr(settings, name)) is not int or getattr(settings, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not settings.idle_seconds < settings.max_cache_age_seconds <= 1500:
            raise ValueError("idle_seconds < max_cache_age_seconds <= 1500 is required")
        return settings


@dataclass
class Snapshot:
    """Read only activity and token metadata, without retaining chat contents."""

    context_tokens: int = 0
    response_id: str | None = None
    cache_started_at: float | None = None
    active: bool = True


def timestamp(value: str | None) -> float | None:
    """Convert a rollout timestamp into wall-clock seconds."""
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        if value
        else None
    )


def read_snapshot(file_path: Path) -> Snapshot:
    """Inspect a bounded transcript tail, including completion and compaction resets.

    A response's previous completion or tool result is a conservative lower
    bound on its cache access time. Its own completion could follow a long
    generation, so using that newer timestamp would overestimate cache life.
    """
    snapshot = Snapshot()
    candidate_start = None
    last_usage = None
    with file_path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        offset = max(0, stream.tell() - MAX_FRAME)
        stream.seek(offset)
        if offset:
            stream.readline()
        for line in stream:
            try:
                row = json.loads(line)
                payload = row.get("payload") or {}
                observed_at = timestamp(row.get("timestamp"))
                kind = row.get("type")
                event = payload.get("type")
                if kind == "event_msg" and event in (
                    "task_started",
                    "task_complete",
                    "turn_aborted",
                ):
                    snapshot.active = event == "task_started"
                    candidate_start = observed_at
                elif kind == "response_item" and event in (
                    "function_call_output",
                    "custom_tool_call_output",
                ):
                    candidate_start = observed_at
                elif kind == "token_usage_record":
                    usage = payload.get("usage") or {}
                    snapshot.context_tokens = int(usage.get("total_tokens", 0))
                    snapshot.cache_started_at = candidate_start
                    snapshot.response_id = payload.get("response_id")
                    last_usage = usage
                    candidate_start = observed_at
                elif (
                    kind == "event_msg"
                    and event == "token_count"
                    and payload.get("info")
                ):
                    usage = payload["info"]["last_token_usage"]
                    snapshot.context_tokens = int(usage.get("total_tokens", 0))
                    if usage.get("input_tokens") and usage != last_usage:
                        snapshot.cache_started_at = candidate_start
                        snapshot.response_id = json.dumps(usage, sort_keys=True)
                        last_usage = usage
                        candidate_start = observed_at
                elif kind == "compacted":
                    snapshot.context_tokens = 0
                    snapshot.response_id = payload.get("compaction_response_id")
                    snapshot.cache_started_at = None
                    candidate_start = observed_at
            except (ValueError, TypeError, KeyError):
                # A final line may be incomplete while the engine appends it.
                continue
    return snapshot


def read_thread(codex_dir: Path, session_id: str) -> dict | None:
    """Read archive/provider metadata from Codex's state database without writing it."""
    databases = list(codex_dir.glob("state_*.sqlite"))
    if not databases:
        return None
    database = max(databases, key=lambda p: int(p.stem.split("_")[-1]))
    with contextlib.closing(
        sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)
    ) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT archived, model_provider, rollout_path FROM threads WHERE id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None


def skip_reason(
    settings: Settings,
    snapshot: Snapshot,
    thread: dict | None,
    model: str,
    now: float,
    expected_response: str | None = None,
) -> str | None:
    """Skip candidates whose size, activity, identity, or cache age changed."""
    if not settings.enabled:
        return "disabled"
    if thread is None:
        return "thread-missing"
    if thread["archived"]:
        return "archived"
    if thread["model_provider"] != "openai":
        return "unsupported-provider"
    match = re.match(r"^gpt-(\d+)(?:\.(\d+))?(?:-|$)", model)
    if not match or tuple(int(n or 0) for n in match.groups()) < (5, 6):
        return "unsupported-cache-lifetime"
    if snapshot.active:
        return "active-turn"
    if snapshot.context_tokens < settings.min_context_tokens:
        return "small-context"
    if expected_response is not None and snapshot.response_id != expected_response:
        return "new-response"
    if (
        snapshot.cache_started_at is None
        or not 0 <= now - snapshot.cache_started_at < settings.max_cache_age_seconds
    ):
        return "cache-window-missed"
    return None


class TimerStore:
    """Serialize scheduling and cancellation in a separate, content-free database."""

    def __init__(self, codex_dir: Path):
        self.directory = codex_dir / "idle-compaction"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.database = self.directory / "state.sqlite3"
        with self.connect() as connection:
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS pending (session_id TEXT PRIMARY KEY, "
                "generation TEXT NOT NULL, candidate TEXT NOT NULL);"
                "CREATE TABLE IF NOT EXISTS events (occurred_at REAL NOT NULL, "
                "session_id TEXT NOT NULL, action TEXT NOT NULL, reason TEXT);"
            )
        self.database.chmod(0o600)

    @contextlib.contextmanager
    def connect(self):
        with contextlib.closing(
            sqlite3.connect(self.database, timeout=1)
        ) as connection:
            with connection:
                yield connection

    @staticmethod
    def record(connection, session_id, action, reason=None):
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            (time.time(), session_id, action, reason),
        )
        connection.execute(
            "DELETE FROM events WHERE rowid <= (SELECT MAX(rowid) - 1000 FROM events)"
        )

    def cancel(self, session_id, reason):
        with self.connect() as connection:
            removed = connection.execute(
                "DELETE FROM pending WHERE session_id = ?", (session_id,)
            ).rowcount
            if removed:
                self.record(connection, session_id, "cancelled", reason)

    def get(self, session_id, generation):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT candidate FROM pending WHERE session_id = ? AND generation = ?",
                (session_id, generation),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def finish(self, session_id, generation, reason):
        with self.connect() as connection:
            removed = connection.execute(
                "DELETE FROM pending WHERE session_id = ? AND generation = ?",
                (session_id, generation),
            ).rowcount
            if removed:
                self.record(connection, session_id, "skipped", reason)


class DesktopIPC:
    """Use the desktop's internal owner-routing protocol, with no resume fallback."""

    def __init__(self, socket_path: Path):
        metadata = socket_path.stat()
        if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise ValueError("Desktop IPC socket is not owned by the current user")
        self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connection.settimeout(5)
        try:
            self.connection.connect(str(socket_path))
            self.client_id = "uninitialized"
            result = self.request("initialize", {"clientType": "cli"}, version=0)
            self.client_id = result["result"]["clientId"]
        except Exception:
            self.close()
            raise

    def close(self):
        self.connection.close()

    def receive(self):
        def exact(length):
            data = bytearray()
            while len(data) < length:
                chunk = self.connection.recv(length - len(data))
                if not chunk:
                    raise EOFError("Desktop IPC closed")
                data.extend(chunk)
            return data

        length = struct.unpack("<I", exact(4))[0]
        if not 0 < length <= MAX_FRAME:
            raise ValueError("Unexpected desktop IPC frame length")
        return json.loads(exact(length))

    def send(self, method, params, version=1, target=None):
        request_id = str(uuid.uuid4())
        message = {
            "type": "request",
            "requestId": request_id,
            "sourceClientId": self.client_id,
            "version": version,
            "method": method,
            "params": params,
            "timeoutMs": 4000,
        }
        if target:
            message["targetClientId"] = target
        payload = json.dumps(message).encode()
        self.connection.sendall(struct.pack("<I", len(payload)) + payload)
        return request_id

    def wait(self, request_id):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            message = self.receive()
            if (
                message.get("requestId") == request_id
                and message.get("type") == "response"
            ):
                if message.get("resultType") != "success":
                    raise RuntimeError(
                        message.get("error", "Desktop IPC request failed")
                    )
                return message
        raise TimeoutError("Desktop IPC response timed out")

    def request(self, method, params, version=1, target=None):
        return self.wait(self.send(method, params, version, target))

    def owner_settings(self, session_id):
        owner = self.request(
            "thread-owner-discovery", {"hostId": "local", "conversationId": session_id}
        )
        target = owner["handledByClientId"]
        settings = self.request(
            "thread-follower-read-model-settings",
            {"conversationId": session_id},
            target=target,
        )
        return target, settings["result"]["settings"]


def handle_hook(codex_dir: Path, payload: dict):
    """Arm one timer after Stop and invalidate it before any resumed work."""
    session_id = payload.get("session_id", "")
    if not SESSION_ID.fullmatch(session_id):
        return
    event = payload.get("hook_event_name")
    store = TimerStore(codex_dir)
    if event != "Stop":
        store.cancel(session_id, event)
        return
    settings = Settings.load(codex_dir)
    thread = read_thread(codex_dir, session_id)
    if thread is None or thread["archived"] or not payload.get("transcript_path"):
        store.cancel(session_id, "thread-unavailable")
        return
    transcript = Path(payload["transcript_path"]).resolve()
    if transcript != Path(thread["rollout_path"]).resolve():
        store.cancel(session_id, "transcript-mismatch")
        return
    snapshot = read_snapshot(transcript)
    # Stop runs before the engine appends task_complete; the worker checks it.
    snapshot.active = False
    model = payload.get("model", "")
    now = time.time()
    reason = skip_reason(settings, snapshot, thread, model, now + settings.idle_seconds)
    if reason:
        store.cancel(session_id, reason)
        return
    generation = str(uuid.uuid4())
    candidate = {
        "transcript": str(transcript),
        "model": model,
        "response_id": snapshot.response_id,
        "due_at": now + settings.idle_seconds,
    }
    with store.connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO pending VALUES (?, ?, ?)",
            (session_id, generation, json.dumps(candidate)),
        )
        store.record(connection, session_id, "scheduled")
    try:
        subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "--codex-dir",
                str(codex_dir),
                "worker",
                session_id,
                generation,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            cwd=SCRIPT.parent,
        )
    except OSError:
        store.finish(session_id, generation, "worker-start-failed")
        raise


def compact_candidate(
    codex_dir: Path,
    store: TimerStore,
    session_id: str,
    generation: str,
    candidate: dict,
    ipc_factory=DesktopIPC,
):
    """Recheck eligibility, then send one compaction to the live owner."""
    settings = Settings.load(codex_dir)
    thread = read_thread(codex_dir, session_id)
    snapshot = read_snapshot(Path(candidate["transcript"]))
    reason = skip_reason(
        settings,
        snapshot,
        thread,
        candidate["model"],
        time.time(),
        candidate["response_id"],
    )
    if reason:
        store.finish(session_id, generation, reason)
        return
    with contextlib.closing(ipc_factory(codex_dir / "ipc" / "ipc.sock")) as ipc:
        owner, model_settings = ipc.owner_settings(session_id)
        if not model_settings or model_settings.get("model") != candidate["model"]:
            store.finish(session_id, generation, "model-changed")
            return
        # Cancellation hooks share this transaction. Release it immediately after
        # sending, before waiting for a reply or running PreCompact hooks.
        with store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute(
                "SELECT generation FROM pending WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not pending or pending[0] != generation:
                return
            snapshot = read_snapshot(Path(candidate["transcript"]))
            thread = read_thread(codex_dir, session_id)
            reason = skip_reason(
                settings,
                snapshot,
                thread,
                candidate["model"],
                time.time(),
                candidate["response_id"],
            )
            connection.execute(
                "DELETE FROM pending WHERE session_id = ?", (session_id,)
            )
            if reason:
                store.record(connection, session_id, "skipped", reason)
                return
            request_id = ipc.send(
                "thread-follower-compact-thread",
                {"conversationId": session_id},
                target=owner,
            )
            store.record(connection, session_id, "requested")
        ipc.wait(request_id)
        with store.connect() as connection:
            store.record(connection, session_id, "accepted")


def run_worker(codex_dir: Path, session_id: str, generation: str):
    """Wait outside the hook process and drop expired timers after machine sleep."""
    store = TimerStore(codex_dir)
    try:
        while candidate := store.get(session_id, generation):
            remaining = candidate["due_at"] - time.time()
            if remaining > 0:
                time.sleep(min(15, remaining))
                continue
            compact_candidate(codex_dir, store, session_id, generation, candidate)
            return
    except Exception as error:
        store.finish(session_id, generation, "worker-error")
        with store.connect() as connection:
            store.record(connection, session_id, "error", str(error)[:300])


class ConfigServer:
    """Use public app-server configuration APIs to trust only our installed hooks."""

    def __init__(self, executable: str, codex_dir: Path):
        self.process = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "CODEX_HOME": str(codex_dir)},
            bufsize=0,
        )
        self.buffer = b""
        self.sequence = 0
        try:
            self.request(
                "initialize",
                {"clientInfo": {"name": "prompts-idle-compaction", "version": "1"}},
            )
            self.process.stdin.write(b'{"method":"initialized"}\n')
            self.process.stdin.flush()
        except Exception:
            self.close()
            raise

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()

    def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        message = {"id": request_id, "method": method, "params": params}
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                response = json.loads(line)
                if response.get("id") == request_id:
                    if "error" in response:
                        raise RuntimeError(response["error"])
                    return response["result"]
            ready, _, _ = select.select(
                [self.process.stdout], [], [], max(0, deadline - time.monotonic())
            )
            if ready:
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise EOFError("Codex config server exited")
                self.buffer += chunk
        raise TimeoutError(f"Codex {method} timed out")


def codex_executable() -> str:
    """Prefer the desktop's bundled engine so its hook hashes match the running app."""
    for app in ("ChatGPT", "Codex"):
        file_path = Path(
            f"/Applications/{app}.app/Contents/Resources/codex-cli/"
            "CodexCLI.app/Contents/MacOS/codex"
        )
        if file_path.is_file():
            return str(file_path)
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("codex is required to install and trust the hooks")
    return executable


def is_idle_handler(handler: dict) -> bool:
    """Recognize our installed command even when the checkout path changes."""
    try:
        arguments = shlex.split(handler.get("command", ""))
    except ValueError:
        return False
    return bool(
        arguments
        and arguments[-1] == "hook"
        and any(
            argument.endswith("/codex/idle_compaction.py") for argument in arguments
        )
    )


def write_configuration(file_path: Path, document: dict):
    """Replace a JSON configuration atomically from a file in the same directory."""
    if file_path.is_symlink():
        raise ValueError(f"Refusing to replace a symlinked configuration: {file_path}")
    with tempfile.NamedTemporaryFile(
        mode="w", dir=file_path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(document, stream, indent=2)
        stream.write("\n")
    try:
        subprocess.run(["mv", str(temporary), str(file_path)], check=True)
    finally:
        temporary.unlink(missing_ok=True)


def install_hooks(codex_dir: Path):
    """Merge our handlers and trust the exact hashes Codex reports for them."""
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to run the idle compaction hook")
    executable = codex_executable()
    codex_dir.mkdir(parents=True, exist_ok=True)
    Settings.load(codex_dir)
    file_path = codex_dir / "hooks.json"
    document = json.loads(file_path.read_text()) if file_path.exists() else {}
    groups_by_event = document.setdefault("hooks", {})
    command = shlex.join(
        [
            uv,
            "run",
            "--no-project",
            "--script",
            str(SCRIPT),
            "--codex-dir",
            str(codex_dir),
            "hook",
        ]
    )
    for event in EVENTS:
        groups = groups_by_event.setdefault(event, [])
        # Remove our old handler only; preserve all unrelated hooks and metadata.
        retained = []
        for group in groups:
            handlers = group.get("hooks", [])
            remaining = [
                handler for handler in handlers if not is_idle_handler(handler)
            ]
            if len(remaining) == len(handlers):
                retained.append(group)
            elif remaining:
                retained.append({**group, "hooks": remaining})
        groups[:] = retained
        groups.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 3 if event in ("SessionEnd", "Interrupt") else 10,
                    }
                ]
            }
        )
    if file_path.is_symlink():
        raise ValueError("Refusing to overwrite a symlinked user hooks.json")
    # Keep a recovery copy when changing an existing user-owned configuration.
    if file_path.exists() and json.loads(file_path.read_text()) != document:
        shutil.copy2(file_path, codex_dir / "idle-compaction-hooks.backup.json")
    write_configuration(file_path, document)
    settings_path = codex_dir / "idle-compaction.json"
    if not settings_path.exists():
        write_configuration(settings_path, asdict(Settings()))
    with contextlib.closing(ConfigServer(executable, codex_dir)) as server:
        result = server.request("hooks/list", {"cwds": [str(SCRIPT.parent.parent)]})
        hooks = [
            hook
            for entry in result["data"]
            for hook in entry["hooks"]
            if hook.get("source") == "user" and hook.get("command") == command
        ]
        if len(hooks) != len(EVENTS):
            raise RuntimeError(f"Expected {len(EVENTS)} user hooks, found {len(hooks)}")
        edits = []
        for hook in hooks:
            key = "hooks.state." + json.dumps(hook["key"])
            edits.extend(
                [
                    {
                        "keyPath": key + ".enabled",
                        "value": True,
                        "mergeStrategy": "upsert",
                    },
                    {
                        "keyPath": key + ".trusted_hash",
                        "value": hook["currentHash"],
                        "mergeStrategy": "upsert",
                    },
                ]
            )
        server.request(
            "config/batchWrite",
            {"edits": edits, "filePath": str(codex_dir / "config.toml")},
        )
    print(f"Installed and trusted {len(EVENTS)} idle compaction hooks in {file_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-dir",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hook")
    commands.add_parser("install")
    commands.add_parser("status")
    worker = commands.add_parser("worker")
    worker.add_argument("session_id")
    worker.add_argument("generation")
    args = parser.parse_args()
    codex_dir = args.codex_dir.expanduser().resolve()
    if args.command == "hook":
        try:
            handle_hook(codex_dir, json.load(sys.stdin))
        except Exception as error:
            print(f"Idle compaction hook skipped: {error}", file=sys.stderr)
        print("{}")
    elif args.command == "install":
        install_hooks(codex_dir)
    elif args.command == "worker":
        run_worker(codex_dir, args.session_id, args.generation)
    elif args.command == "status":
        store = TimerStore(codex_dir)
        with store.connect() as connection:
            connection.row_factory = sqlite3.Row
            pending = [dict(row) for row in connection.execute("SELECT * FROM pending")]
            recent = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM events ORDER BY rowid DESC LIMIT 20"
                )
            ]
        print(
            json.dumps(
                {
                    "settings": asdict(Settings.load(codex_dir)),
                    "pending": pending,
                    "recent": recent,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
