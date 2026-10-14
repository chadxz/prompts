"""Exercise compaction eligibility, cancellation races, IPC, and installation."""

import json
import socket
import sqlite3
import struct
import tempfile
import threading
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import idle_compaction as compact


class IdleCompactionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.codex_dir = Path(self.temporary.name)
        self.session_id = "session-123"
        self.now = time.time()
        self.transcript = self.codex_dir / "rollout.jsonl"
        self.write_rollout()
        with sqlite3.connect(self.codex_dir / "state_5.sqlite") as connection:
            connection.execute(
                "CREATE TABLE threads (id TEXT, archived INTEGER, "
                "model_provider TEXT, rollout_path TEXT)"
            )
            connection.execute(
                "INSERT INTO threads VALUES (?, 0, 'openai', ?)",
                (self.session_id, str(self.transcript)),
            )
        self.settings = compact.Settings()

    def write_rollout(
        self,
        active=False,
        response_id="response-1",
        compaction=False,
        request_age=40,
        response_age=5,
    ):
        def row(kind, payload, seconds):
            return {
                "timestamp": compact.datetime.fromtimestamp(
                    seconds, compact.datetime.now().astimezone().tzinfo
                ).isoformat(),
                "type": kind,
                "payload": payload,
            }

        usage = {
            "input_tokens": 300000,
            "cached_input_tokens": 299000,
            "output_tokens": 2000,
            "cache_write_input_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": 302000,
        }
        rows = [
            row("event_msg", {"type": "task_started"}, self.now - 50),
            row(
                "response_item",
                {"type": "custom_tool_call_output", "output": "private content"},
                self.now - request_age,
            ),
            row(
                "token_usage_record",
                {"response_id": response_id, "usage": usage},
                self.now - response_age,
            ),
            row(
                "event_msg",
                {"type": "token_count", "info": {"last_token_usage": usage}},
                self.now - response_age,
            ),
        ]
        if compaction:
            rows.extend(
                [
                    row(
                        "compacted",
                        {"compaction_response_id": "compact-1"},
                        self.now - 4,
                    ),
                    row(
                        "event_msg",
                        {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 0,
                                    "total_tokens": 30000,
                                }
                            },
                        },
                        self.now - 3,
                    ),
                ]
            )
        if not active:
            rows.append(row("event_msg", {"type": "task_complete"}, self.now))
        self.transcript.write_text("".join(json.dumps(item) + "\n" for item in rows))

    def candidate(self):
        return {
            "transcript": str(self.transcript),
            "model": "gpt-6.1-sol",
            "response_id": "response-1",
            "due_at": self.now - 1,
        }

    def scheduled(self):
        store = compact.TimerStore(self.codex_dir)
        candidate = self.candidate()
        with store.connect() as connection:
            connection.execute(
                "INSERT INTO pending VALUES (?, ?, ?)",
                (self.session_id, "generation-1", json.dumps(candidate)),
            )
        return store, candidate

    def reason(self, **changes):
        snapshot = compact.read_snapshot(self.transcript)
        for name, value in changes.items():
            setattr(snapshot, name, value)
        return compact.skip_reason(
            self.settings,
            snapshot,
            compact.read_thread(self.codex_dir, self.session_id),
            "gpt-6.1-sol",
            self.now,
            "response-1",
        )

    def test_cache_age_uses_request_lower_bound_instead_of_generation_completion(self):
        snapshot = compact.read_snapshot(self.transcript)
        self.assertAlmostEqual(snapshot.cache_started_at, self.now - 40, places=4)
        self.assertEqual(snapshot.response_id, "response-1")
        self.assertIsNone(self.reason())

    def test_long_generation_does_not_extend_cache_window(self):
        self.assertEqual(
            self.reason(cache_started_at=self.now - 1600), "cache-window-missed"
        )

    def test_unknown_cache_start_is_ineligible(self):
        self.assertEqual(self.reason(cache_started_at=None), "cache-window-missed")

    def test_future_cache_time_is_ineligible(self):
        self.assertEqual(
            self.reason(cache_started_at=self.now + 30), "cache-window-missed"
        )

    def test_new_response_invalidates_timer(self):
        self.assertEqual(self.reason(response_id="response-2"), "new-response")

    def test_active_turn_is_ineligible(self):
        self.write_rollout(active=True)
        self.assertEqual(self.reason(), "active-turn")

    def test_compaction_reset_prevents_repeat(self):
        self.write_rollout(compaction=True)
        self.assertEqual(self.reason(), "small-context")

    def test_archived_thread_does_not_connect_to_ipc(self):
        store, candidate = self.scheduled()
        with sqlite3.connect(self.codex_dir / "state_5.sqlite") as connection:
            connection.execute("UPDATE threads SET archived = 1")
        with patch.object(compact, "DesktopIPC") as factory:
            compact.compact_candidate(
                self.codex_dir,
                store,
                self.session_id,
                "generation-1",
                candidate,
                ipc_factory=factory,
            )
        factory.assert_not_called()
        self.assertIsNone(store.get(self.session_id, "generation-1"))

    def test_missing_thread_does_not_qualify(self):
        self.assertEqual(
            compact.skip_reason(
                self.settings,
                compact.read_snapshot(self.transcript),
                None,
                "gpt-6.1-sol",
                self.now,
            ),
            "thread-missing",
        )

    def test_older_models_do_not_use_new_cache_lifetime(self):
        thread = compact.read_thread(self.codex_dir, self.session_id)
        for model in ("gpt-5.5", "claude-opus-5-5", "unknown"):
            with self.subTest(model=model):
                self.assertEqual(
                    compact.skip_reason(
                        self.settings,
                        compact.read_snapshot(self.transcript),
                        thread,
                        model,
                        self.now,
                    ),
                    "unsupported-cache-lifetime",
                )

    def test_cold_worker_never_connects_to_desktop(self):
        store, candidate = self.scheduled()
        with (
            patch.object(compact.time, "time", return_value=self.now + 1800),
            patch.object(compact, "DesktopIPC") as factory,
        ):
            compact.compact_candidate(
                self.codex_dir,
                store,
                self.session_id,
                "generation-1",
                candidate,
                ipc_factory=factory,
            )
        factory.assert_not_called()

    def test_prompt_and_compaction_lifecycle_cancel_pending_work(self):
        for event in compact.EVENTS[1:]:
            with self.subTest(event=event):
                store, _ = self.scheduled()
                compact.handle_hook(
                    self.codex_dir,
                    {"session_id": self.session_id, "hook_event_name": event},
                )
                self.assertIsNone(store.get(self.session_id, "generation-1"))

    def test_stop_schedules_without_waiting_and_replaces_previous_generation(self):
        payload = {
            "session_id": self.session_id,
            "hook_event_name": "Stop",
            "transcript_path": str(self.transcript),
            "model": "gpt-6.1-sol",
        }
        with patch.object(compact.subprocess, "Popen") as spawn:
            compact.handle_hook(self.codex_dir, payload)
            compact.handle_hook(self.codex_dir, payload)
        self.assertEqual(spawn.call_count, 2)
        store = compact.TimerStore(self.codex_dir)
        with store.connect() as connection:
            rows = connection.execute("SELECT * FROM pending").fetchall()
        self.assertEqual(len(rows), 1)
        candidate = json.loads(rows[0][2])
        self.assertGreater(candidate["due_at"], self.now + 1199)
        self.assertNotIn("private content", rows[0][2])
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])

    def test_stop_skips_when_cache_will_expire_before_idle_deadline(self):
        payload = {
            "session_id": self.session_id,
            "hook_event_name": "Stop",
            "transcript_path": str(self.transcript),
            "model": "gpt-6.1-sol",
        }
        with (
            patch.object(compact.time, "time", return_value=self.now + 400),
            patch.object(compact.subprocess, "Popen") as spawn,
        ):
            compact.handle_hook(self.codex_dir, payload)
        spawn.assert_not_called()

    def fake_ipc(self, before_settings=None):
        test = self

        class FakeIPC:
            sent = []

            def __init__(self, socket_path):
                pass

            def owner_settings(self, session_id):
                if before_settings:
                    before_settings()
                return "owner-1", {"model": "gpt-6.1-sol"}

            def send(self, method, params, target):
                test.assertEqual(target, "owner-1")
                self.sent.append((method, params))
                return "request-1"

            def wait(self, request_id):
                return {"resultType": "success"}

            def close(self):
                pass

        return FakeIPC

    def test_archive_during_owner_discovery_is_rechecked(self):
        store, candidate = self.scheduled()

        def archive():
            with sqlite3.connect(self.codex_dir / "state_5.sqlite") as connection:
                connection.execute("UPDATE threads SET archived = 1")

        factory = self.fake_ipc(archive)
        compact.compact_candidate(
            self.codex_dir,
            store,
            self.session_id,
            "generation-1",
            candidate,
            ipc_factory=factory,
        )
        self.assertEqual(factory.sent, [])

    def test_prompt_during_owner_discovery_cancels_request(self):
        store, candidate = self.scheduled()
        factory = self.fake_ipc(
            lambda: store.cancel(self.session_id, "UserPromptSubmit")
        )
        compact.compact_candidate(
            self.codex_dir,
            store,
            self.session_id,
            "generation-1",
            candidate,
            ipc_factory=factory,
        )
        self.assertEqual(factory.sent, [])

    def test_success_is_sent_once_and_never_retried(self):
        store, candidate = self.scheduled()
        factory = self.fake_ipc()
        for _ in range(2):
            compact.compact_candidate(
                self.codex_dir,
                store,
                self.session_id,
                "generation-1",
                candidate,
                ipc_factory=factory,
            )
        self.assertEqual(
            factory.sent,
            [("thread-follower-compact-thread", {"conversationId": self.session_id})],
        )

    def test_config_rejects_idle_deadline_outside_warm_window(self):
        config = asdict(self.settings)
        config["idle_seconds"] = 1600
        (self.codex_dir / "idle-compaction.json").write_text(json.dumps(config))
        with self.assertRaises(ValueError):
            compact.Settings.load(self.codex_dir)

    def test_detached_worker_completes_compaction_protocol_after_timer(self):
        self.write_rollout(request_age=0.2, response_age=0.1)
        (self.codex_dir / "idle-compaction.json").write_text(
            json.dumps(
                {
                    "enabled": True,
                    "idle_seconds": 1,
                    "max_cache_age_seconds": 10,
                    "min_context_tokens": 200000,
                }
            )
        )
        (self.codex_dir / "ipc").mkdir()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.settimeout(5)
        listener.bind(str(self.codex_dir / "ipc" / "ipc.sock"))
        listener.listen(1)
        methods = []
        failures = []

        def serve():
            try:
                with listener.accept()[0] as connection:
                    connection.settimeout(5)
                    for _ in range(4):
                        header = connection.recv(4)
                        size = struct.unpack("<I", header)[0]
                        data = b""
                        while len(data) < size:
                            data += connection.recv(size - len(data))
                        message = json.loads(data)
                        method = message["method"]
                        methods.append(method)
                        result = {}
                        if method == "initialize":
                            result = {"clientId": "worker-client"}
                        elif method == "thread-follower-read-model-settings":
                            result = {"settings": {"model": "gpt-6.1-sol"}}
                        response = json.dumps(
                            {
                                "type": "response",
                                "requestId": message["requestId"],
                                "resultType": "success",
                                "handledByClientId": "desktop-owner",
                                "result": result,
                            }
                        ).encode()
                        connection.sendall(struct.pack("<I", len(response)) + response)
            except Exception as error:
                failures.append(error)

        server = threading.Thread(target=serve, daemon=True)
        server.start()
        real_spawn = compact.subprocess.Popen
        workers = []

        def spawn(*args, **kwargs):
            process = real_spawn(*args, **kwargs)
            workers.append(process)
            return process

        with patch.object(compact.subprocess, "Popen", side_effect=spawn):
            compact.handle_hook(
                self.codex_dir,
                {
                    "session_id": self.session_id,
                    "hook_event_name": "Stop",
                    "transcript_path": str(self.transcript),
                    "model": "gpt-6.1-sol",
                },
            )
        store = compact.TimerStore(self.codex_dir)
        accepted = False
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            with store.connect() as connection:
                accepted = connection.execute(
                    "SELECT 1 FROM events WHERE action='accepted'"
                ).fetchone()
            if accepted:
                break
            time.sleep(0.05)
        server.join(1)
        for worker in workers:
            worker.wait(timeout=3)
        self.assertEqual(failures, [])
        self.assertTrue(accepted)
        self.assertEqual(
            methods,
            [
                "initialize",
                "thread-owner-discovery",
                "thread-follower-read-model-settings",
                "thread-follower-compact-thread",
            ],
        )

    def test_installer_preserves_other_hooks_and_trusts_only_its_own(self):
        existing = {
            "description": "Personal hooks",
            "hooks": {
                "Stop": [
                    {
                        "matcher": "existing",
                        "hooks": [{"type": "command", "command": "existing-command"}],
                    }
                ],
                "PostToolUse": [
                    {"hooks": [{"type": "command", "command": "other-command"}]}
                ],
            },
        }
        (self.codex_dir / "hooks.json").write_text(json.dumps(existing))
        writes = []
        test = self

        class FakeServer:
            def __init__(self, executable, codex_dir):
                pass

            def request(self, method, params):
                if method == "hooks/list":
                    document = json.loads((test.codex_dir / "hooks.json").read_text())
                    metadata = []
                    for event, groups in document["hooks"].items():
                        for index, group in enumerate(groups):
                            for handler in group["hooks"]:
                                metadata.append(
                                    {
                                        "source": "user",
                                        "command": handler["command"],
                                        "key": f"user:hooks.json:{event}:{index}:0",
                                        "currentHash": "sha256:test",
                                    }
                                )
                    return {"data": [{"hooks": metadata}]}
                writes.extend(params["edits"])
                return {}

            def close(self):
                pass

        with (
            patch.object(compact, "ConfigServer", FakeServer),
            patch.object(compact, "codex_executable", return_value="codex"),
        ):
            compact.install_hooks(self.codex_dir)
            first = (self.codex_dir / "hooks.json").read_text()
            compact.install_hooks(self.codex_dir)
        self.assertEqual(first, (self.codex_dir / "hooks.json").read_text())
        document = json.loads(first)
        self.assertEqual(document["description"], "Personal hooks")
        self.assertEqual(
            document["hooks"]["PostToolUse"], existing["hooks"]["PostToolUse"]
        )
        self.assertEqual(document["hooks"]["Stop"][0], existing["hooks"]["Stop"][0])
        self.assertEqual(len(writes), len(compact.EVENTS) * 4)
        self.assertTrue(all("PostToolUse" not in edit["keyPath"] for edit in writes))
        self.assertTrue(all(":Stop:0:" not in edit["keyPath"] for edit in writes))


class DesktopIPCTest(unittest.TestCase):
    def test_fragmented_frames_and_unrelated_broadcasts(self):
        with tempfile.TemporaryDirectory() as directory:
            socket_path = Path(directory) / "ipc.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(listener.close)
            listener.bind(str(socket_path))
            listener.listen(1)
            failures = []

            def serve():
                try:
                    with listener.accept()[0] as connection:
                        header = connection.recv(4)
                        size = struct.unpack("<I", header)[0]
                        request = json.loads(connection.recv(size))
                        broadcast = json.dumps(
                            {"type": "broadcast", "method": "client-status-changed"}
                        ).encode()
                        response = json.dumps(
                            {
                                "type": "response",
                                "requestId": request["requestId"],
                                "resultType": "success",
                                "result": {"clientId": "test-client"},
                            }
                        ).encode()
                        frames = (
                            struct.pack("<I", len(broadcast))
                            + broadcast
                            + struct.pack("<I", len(response))
                            + response
                        )
                        for byte in frames:
                            connection.sendall(bytes([byte]))
                except Exception as error:
                    failures.append(error)

            thread = threading.Thread(target=serve)
            thread.start()
            ipc = compact.DesktopIPC(socket_path)
            self.assertEqual(ipc.client_id, "test-client")
            ipc.close()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
