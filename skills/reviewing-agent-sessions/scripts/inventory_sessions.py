#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

"""Build a deduplicated inventory of local Codex session rollouts."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROLLOUT_PATTERN = re.compile(
    r"^rollout-(?P<date>\d{4}-\d{2}-\d{2})T.*"
    r"(?P<session_id>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.jsonl$"
)
SKILL_PATTERN = re.compile(r"/skills/([^/\"']+)/SKILL\.md")
SECRET_PATTERNS = (
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(Bearer\s+)[^\s\"']+"),
    re.compile(r"(?i)\b(token|password|secret)=([^\s&]+)"),
)
FAILURE_SIGNALS = {
    "command-not-found": re.compile(
        r"command not found|not recognized as an internal|No such file or directory",
        re.IGNORECASE,
    ),
    "git-worktree-layout": re.compile(
        r"must be run in a work tree|not a git repository|already checked out at|"
        r"is a bare repository",
        re.IGNORECASE,
    ),
    "git-branch-or-ref": re.compile(
        r"ambiguous argument|unknown revision|invalid reference|"
        r"couldn't find remote ref|not a valid object name",
        re.IGNORECASE,
    ),
    "git-dirty-or-conflict": re.compile(
        r"would be overwritten|merge conflict|unmerged paths|"
        r"Please commit your changes or stash them",
        re.IGNORECASE,
    ),
    "test-or-lint": re.compile(
        r"^(?:FAIL|--- FAIL:)|tests? failed|lint(?:ing)? failed|"
        r"coverage threshold|(?:gofumpt|golangci-lint|eslint|typecheck)"
        r".*(?:error|fail)|(?:error|fail).*(?:gofumpt|golangci-lint|eslint|"
        r"typecheck)",
        re.IGNORECASE,
    ),
    "build-or-compile": re.compile(
        r"build failed|compilation failed|cannot compile|undefined:|"
        r"syntax error|SyntaxError",
        re.IGNORECASE,
    ),
    "auth-or-permission": re.compile(
        r"authentication failed|unauthorized|forbidden|permission denied|"
        r"HTTP 401|HTTP 403|Bad credentials",
        re.IGNORECASE,
    ),
    "network-or-timeout": re.compile(
        r"(?:operation|request|connection|context|dial|i/o).*timed? out|"
        r"context deadline exceeded|connection refused|Could not resolve host|"
        r"network is unreachable|TLS handshake (?:timeout|failed)",
        re.IGNORECASE,
    ),
    "rate-limit": re.compile(
        r"rate.?limit|HTTP 429|too many requests",
        re.IGNORECASE,
    ),
    "missing-input-or-path": re.compile(
        r"does not exist|cannot stat|can't open|no matches found|file not found",
        re.IGNORECASE,
    ),
    "invalid-cli-usage": re.compile(
        r"unknown (?:option|flag|command)|invalid arguments?|"
        r"requires .* argument|^usage:",
        re.IGNORECASE,
    ),
    "terraform": re.compile(
        r"Error acquiring the state lock|Terraform.*(?:error|failed)|"
        r"Terragrunt.*(?:error|failed)|Unsupported argument|"
        r"Reference to undeclared",
        re.IGNORECASE,
    ),
    "docker": re.compile(
        r"Cannot connect to the Docker daemon|Docker daemon.*not running|"
        r"(?:docker|buildx).*(?:error|failed)|"
        r"(?:error|failed).*(?:docker|buildx)",
        re.IGNORECASE,
    ),
    "mise": re.compile(
        r"mise (?:ERROR|WARN)|mise.*(?:error|failed|not trusted)|"
        r"(?:error|failed).*mise|trust this config",
        re.IGNORECASE,
    ),
    "connector": re.compile(
        r"MCP server.*(?:error|failed|unavailable)|"
        r"(?:connector|integration).*(?:error|failed|not connected)|"
        r"(?:error|failed).*(?:connector|integration)",
        re.IGNORECASE,
    ),
}
INTENT_SIGNALS = {
    "github": re.compile(
        r"\b(?:github|pull request|\bpr\b|commit|merge|review comments?|"
        r"checks?|ci)\b",
        re.IGNORECASE,
    ),
    "slack": re.compile(
        r"\bslack\b|app\.slack\.com|convergint\.enterprise\.slack\.com",
        re.IGNORECASE,
    ),
    "notion": re.compile(r"\bnotion\b|notion\.so|notion\.com", re.IGNORECASE),
    "linear": re.compile(r"\blinear\b|\bee-\d+\b", re.IGNORECASE),
    "terraform": re.compile(
        r"\bterraform\b|\bterragrunt\b|\bapply\b.*\bplan\b",
        re.IGNORECASE,
    ),
    "kubernetes": re.compile(
        r"\bkubernetes\b|\bk8s\b|\bkubectl\b|\bhelm\b|\bcluster\b",
        re.IGNORECASE,
    ),
    "temporal": re.compile(
        r"\btemporal\b|\bworkflow\b|\bactivity\b",
        re.IGNORECASE,
    ),
    "implementation": re.compile(
        r"\b(?:build|implement|change|update|modify|fix|add|remove|create)\b",
        re.IGNORECASE,
    ),
    "diagnosis": re.compile(
        r"\b(?:why|diagnos|investigat|figure out|root cause|what happened|"
        r"failing|failure)\b",
        re.IGNORECASE,
    ),
    "review": re.compile(
        r"\b(?:review|critique|second[- ]guess|evaluate|audit)\b",
        re.IGNORECASE,
    ),
    "verification": re.compile(
        r"\b(?:double[- ]check|check your work|review your work|verify|"
        r"verification|re-?audit|second[- ]guess)\b",
        re.IGNORECASE,
    ),
    "communication": re.compile(
        r"\b(?:draft|write|reply|message|announce|postmortem|document|"
        r"summarize)\b",
        re.IGNORECASE,
    ),
    "research": re.compile(
        r"\b(?:research|compare|recommend|what is|how does|explain|tell me)\b",
        re.IGNORECASE,
    ),
}
CORRECTION_SIGNALS = {
    "continue": re.compile(
        r"^(?:please )?(?:keep going|continue|proceed|go ahead|resume)\b",
        re.IGNORECASE,
    ),
    "correction": re.compile(
        r"^(?:no\b|actually\b|that's not\b|that is not\b|"
        r"you (?:missed|forgot|haven't|didn't|should)|"
        r"i (?:said|meant|want))\b",
        re.IGNORECASE,
    ),
    "retry": re.compile(r"\b(?:try again|retry|re-run|rerun)\b", re.IGNORECASE),
    "dissatisfaction": re.compile(
        r"\b(?:wrong|incorrect|not what i asked|still broken|"
        r"doesn't work|didn't work)\b",
        re.IGNORECASE,
    ),
    "stop": re.compile(
        r"^(?:stop|cancel|never mind|nevermind)\b",
        re.IGNORECASE,
    ),
}


@dataclass
class FailureRecord:
    """Identify a failed tool call without retaining its potentially secret output."""

    tool: str
    categories: tuple[str, ...]


@dataclass
class Session:
    """Hold the compact facts extracted from one rollout file."""

    file: Path
    rollout_date: str
    filename_session_id: str
    byte_count: int
    session_id: str = ""
    cwd: str = ""
    source_kind: str = "direct"
    parent_thread_id: str = ""
    originator: str = ""
    started_at: str = ""
    ended_at: str = ""
    first_turn_id: str = ""
    started_turn_ids: set[str] = field(default_factory=set)
    completed_turn_ids: set[str] = field(default_factory=set)
    aborted_turn_ids: set[str] = field(default_factory=set)
    user_messages_by_turn: dict[str, str] = field(default_factory=dict)
    fallback_user_messages: list[str] = field(default_factory=list)
    models_by_turn: dict[str, str] = field(default_factory=dict)
    event_counts: Counter[str] = field(default_factory=Counter)
    response_item_types: Counter[str] = field(default_factory=Counter)
    call_names: dict[str, str] = field(default_factory=dict)
    call_skills: dict[str, set[str]] = field(default_factory=dict)
    failures: list[FailureRecord] = field(default_factory=list)
    parse_errors: int = 0

    @property
    def effective_session_id(self) -> str:
        """Return metadata's session ID, falling back to the rollout filename."""

        return self.session_id or self.filename_session_id

    @property
    def task_root(self) -> str:
        """Return the earliest inherited user turn used to group task forks."""

        if self.user_messages_by_turn:
            return next(iter(self.user_messages_by_turn))
        return self.first_turn_id or self.effective_session_id

    @property
    def user_messages(self) -> list[str]:
        """Return deduplicated user-authored messages in transcript order."""

        if self.user_messages_by_turn:
            return list(self.user_messages_by_turn.values())
        return list(dict.fromkeys(self.fallback_user_messages))

    @property
    def kind(self) -> str:
        """Classify the rollout as direct, subagent, or internal review."""

        if self.source_kind == "internal":
            return "internal"
        if self.source_kind == "subagent":
            return "subagent"
        if self.models_by_turn and all(
            model.startswith("codex-auto-review/")
            for model in self.models_by_turn.values()
        ):
            return "internal"
        return "direct"


def parse_date(value: str) -> date:
    """Parse an ISO calendar date for CLI validation."""

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a valid YYYY-MM-DD date"
        ) from error


def previous_calendar_month(today: date) -> tuple[date, date]:
    """Return the inclusive bounds of the calendar month before today."""

    first_this_month = today.replace(day=1)
    end = first_this_month - timedelta(days=1)
    return end.replace(day=1), end


def default_codex_roots() -> list[Path]:
    """Return the active and archived rollout directories."""

    codex_directory = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return [
        codex_directory / "sessions",
        codex_directory / "archived_sessions",
    ]


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line interface."""

    parser = argparse.ArgumentParser(
        description=(
            "Inventory local Codex rollouts with fork-aware, deduplicated metrics."
        )
    )
    parser.add_argument("--start", type=parse_date)
    parser.add_argument("--end", type=parse_date)
    parser.add_argument(
        "--today",
        type=parse_date,
        help="Override today's date when testing the default month.",
    )
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        dest="roots",
        help="Rollout root to scan. Repeat to supply multiple roots.",
    )
    parser.add_argument(
        "--exclude-session-id",
        action="append",
        default=[],
        help="Session ID to omit. Repeat for multiple sessions.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum rows in each evidence and outlier collection.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path instead of standard output.",
    )
    return parser


def resolve_window(arguments: argparse.Namespace) -> tuple[date, date]:
    """Resolve explicit bounds or the previous local calendar month."""

    if bool(arguments.start) != bool(arguments.end):
        raise SystemExit("--start and --end must be provided together")
    if arguments.start and arguments.end:
        start, end = arguments.start, arguments.end
    else:
        local_today = arguments.today or datetime.now().astimezone().date()
        start, end = previous_calendar_month(local_today)
    if start > end:
        raise SystemExit("--start must be on or before --end")
    return start, end


def select_rollouts(
    roots: Iterable[Path],
    start: date,
    end: date,
    excluded_session_ids: set[str],
) -> list[tuple[Path, re.Match[str]]]:
    """Select rollout files by their embedded local calendar date."""

    selected: list[tuple[Path, re.Match[str]]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for file_path in root.rglob("rollout-*.jsonl"):
            match = ROLLOUT_PATTERN.match(file_path.name)
            if not match:
                continue
            rollout_date = date.fromisoformat(match.group("date"))
            if not start <= rollout_date <= end:
                continue
            if match.group("session_id") in excluded_session_ids:
                continue
            selected.append((file_path, match))
    return sorted(selected, key=lambda item: str(item[0]))


def response_text(content: Any) -> str:
    """Extract text from a response-item content array."""

    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def output_text(output: Any) -> str:
    """Flatten tool output enough to classify failures."""

    if isinstance(output, str):
        return output
    if isinstance(output, list):
        parts = []
        for item in output:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(json.dumps(item, default=str))
        return "\n".join(parts)
    return json.dumps(output, default=str)


def is_user_authored(text: str) -> bool:
    """Exclude injected instruction messages from user-turn metrics."""

    stripped = text.strip()
    return bool(stripped) and not stripped.startswith(
        ("# AGENTS.md instructions", "<environment_context>")
    )


def looks_like_failure(output: str) -> bool:
    """Detect command and connector failures while avoiding ordinary prose."""

    stripped = output.strip()
    prefix = stripped[:1000]
    process_exit = re.search(r"Process exited with code (\d+)", prefix)
    if process_exit:
        return int(process_exit.group(1)) != 0
    structured_exit = re.search(r'"exit_code"\s*:\s*(\d+)', prefix)
    if structured_exit:
        return int(structured_exit.group(1)) != 0
    if prefix.startswith("Script completed"):
        return False
    return bool(
        re.search(r'"isError"\s*:\s*true', prefix)
        or re.search(r'"type"\s*:\s*"tool_error"', prefix)
        or re.match(
            r"^(?:Error|ERROR|fatal|Traceback \(most recent call last\)|"
            r"Script failed|Call failed):",
            prefix,
        )
        or prefix.startswith("received invalid arguments")
    )


def failure_evidence(output: str) -> str:
    """Keep explicit error lines instead of incidental command-output prose."""

    signal = re.compile(
        r"^(?:error|fatal|fail(?:ed|ure)?|traceback|panic|usage:)|"
        r"\b(?:command not found|no such file or directory|does not exist|"
        r"cannot|can't|could not|invalid|unknown|unauthorized|forbidden|"
        r"permission denied|timed? out|deadline exceeded|connection refused|"
        r"network is unreachable|bad credentials|would be overwritten|"
        r"merge conflict|unmerged paths|not connected)\b",
        re.IGNORECASE,
    )
    lines = [
        line.strip()
        for line in output[:12000].splitlines()
        if signal.search(line.strip())
    ]
    return "\n".join(lines[:40])


def classify_failure(output: str) -> tuple[str, ...]:
    """Map failed tool output to operational categories."""

    evidence = failure_evidence(output)
    if not evidence:
        return ("nonzero-status",)
    categories = tuple(
        name for name, pattern in FAILURE_SIGNALS.items() if pattern.search(evidence)
    )
    return categories or ("other",)


def record_call(session: Session, payload: dict[str, Any]) -> None:
    """Record a function, custom, or tool-search call and any loaded skills."""

    call_id = payload.get("call_id") or payload.get("id")
    call_name = payload.get("name") or "tool_search"
    if not isinstance(call_id, str):
        return
    session.call_names[call_id] = str(call_name)
    raw_input = payload.get("arguments", payload.get("input", ""))
    if not isinstance(raw_input, str):
        raw_input = json.dumps(raw_input, default=str)
    matches = set(SKILL_PATTERN.findall(raw_input))
    if matches:
        session.call_skills.setdefault(call_id, set()).update(matches)


def parse_session(file_path: Path, match: re.Match[str]) -> Session:
    """Stream one JSONL rollout into a compact session record."""

    session = Session(
        file=file_path,
        rollout_date=match.group("date"),
        filename_session_id=match.group("session_id"),
        byte_count=file_path.stat().st_size,
    )
    with file_path.open(encoding="utf-8", errors="replace") as input_file:
        for line in input_file:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                session.parse_errors += 1
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            timestamp = item.get("timestamp") or payload.get("timestamp")
            if isinstance(timestamp, str) and timestamp:
                session.started_at = session.started_at or timestamp
                session.ended_at = timestamp

            item_type = item.get("type")
            if item_type == "session_meta":
                if session.session_id:
                    continue
                session.session_id = str(
                    payload.get("id") or payload.get("session_id") or ""
                )
                session.cwd = str(payload.get("cwd") or "")
                session.originator = str(payload.get("originator") or "")
                source = payload.get("source")
                if isinstance(source, dict) and "subagent" in source:
                    subagent = source.get("subagent")
                    if isinstance(subagent, dict):
                        session.source_kind = (
                            "internal" if subagent.get("other") else "subagent"
                        )
                        spawn = subagent.get("thread_spawn")
                        if isinstance(spawn, dict):
                            session.parent_thread_id = str(
                                spawn.get("parent_thread_id") or ""
                            )
                else:
                    session.source_kind = str(source or "direct")
                continue

            if item_type == "turn_context":
                turn_id = payload.get("turn_id")
                if isinstance(turn_id, str):
                    model = str(payload.get("model") or "unknown")
                    effort = str(payload.get("effort") or "unknown")
                    session.models_by_turn[turn_id] = f"{model}/{effort}"
                continue

            if item_type == "event_msg":
                event_type = str(payload.get("type") or "unknown")
                session.event_counts[event_type] += 1
                turn_id = payload.get("turn_id")
                if event_type == "task_started" and isinstance(turn_id, str):
                    session.first_turn_id = session.first_turn_id or turn_id
                    session.started_turn_ids.add(turn_id)
                elif event_type == "task_complete" and isinstance(turn_id, str):
                    session.completed_turn_ids.add(turn_id)
                elif event_type == "turn_aborted" and isinstance(turn_id, str):
                    session.aborted_turn_ids.add(turn_id)
                elif event_type == "user_message":
                    message = payload.get("message")
                    if isinstance(message, str) and is_user_authored(message):
                        session.fallback_user_messages.append(message.strip())
                continue

            if item_type != "response_item":
                continue
            response_type = str(payload.get("type") or "unknown")
            session.response_item_types[response_type] += 1

            if response_type == "message" and payload.get("role") == "user":
                text = response_text(payload.get("content"))
                metadata = payload.get("internal_chat_message_metadata_passthrough")
                turn_id = (
                    metadata.get("turn_id") if isinstance(metadata, dict) else None
                )
                if isinstance(turn_id, str) and is_user_authored(text):
                    session.user_messages_by_turn[turn_id] = text.strip()
                continue

            if response_type in {
                "function_call",
                "custom_tool_call",
                "tool_search_call",
            }:
                record_call(session, payload)
                continue

            if response_type in {
                "function_call_output",
                "custom_tool_call_output",
                "tool_search_output",
            }:
                output = output_text(payload.get("output"))
                if looks_like_failure(output):
                    call_id = payload.get("call_id")
                    call_name = session.call_names.get(str(call_id), "unknown")
                    session.failures.append(
                        FailureRecord(
                            tool=call_name,
                            categories=classify_failure(output),
                        )
                    )
    return session


def newest_session(left: Session, right: Session) -> Session:
    """Choose the most complete copy when a session exists in both roots."""

    left_key = (left.ended_at, left.byte_count)
    right_key = (right.ended_at, right.byte_count)
    return right if right_key > left_key else left


def deduplicate_sessions(sessions: Iterable[Session]) -> tuple[list[Session], int]:
    """Deduplicate active and archived copies by session ID."""

    unique: dict[str, Session] = {}
    duplicates = 0
    for session in sessions:
        session_id = session.effective_session_id
        if session_id in unique:
            duplicates += 1
            unique[session_id] = newest_session(unique[session_id], session)
        else:
            unique[session_id] = session
    return sorted(unique.values(), key=lambda item: str(item.file)), duplicates


def redact_text(text: str, limit: int = 240) -> str:
    """Redact common credential forms and compact an evidence excerpt."""

    redacted = text.replace("\n", " ").strip()
    for pattern in SECRET_PATTERNS:
        if pattern.groups == 1:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        elif pattern.groups == 2:
            redacted = pattern.sub(r"\1=[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[:limit]


def top(counter: Counter[str], limit: int) -> list[list[Any]]:
    """Return descending counter rows suitable for JSON output."""

    return [[name, count] for name, count in counter.most_common(limit)]


def cwd_group(cwd: str) -> str:
    """Collapse common source and projectless paths into useful groups."""

    patterns = (
        (r"^/Users/[^/]+/src/convergint/([^/]+).*$", r"convergint/\1"),
        (r"^/Users/[^/]+/src/personal/([^/]+).*$", r"personal/\1"),
        (r"^/Users/[^/]+/Documents/Codex/.*$", "projectless"),
        (r"^/Users/[^/]+$", "home"),
    )
    for pattern, replacement in patterns:
        if re.match(pattern, cwd):
            return re.sub(pattern, replacement, cwd)
    return cwd or "unknown"


def message_labels(
    message: str,
    signals: dict[str, re.Pattern[str]],
) -> list[str]:
    """Return every broad label whose signal matches a user message."""

    return [name for name, pattern in signals.items() if pattern.search(message)]


def summarize_direct_sessions(
    sessions: list[Session],
    limit: int,
) -> dict[str, Any]:
    """Aggregate fork-aware metrics for direct user-facing sessions."""

    unique_turns: dict[str, str] = {}
    started_turns: set[str] = set()
    completed_turns: set[str] = set()
    aborted_turns: set[str] = set()
    call_names: dict[str, str] = {}
    call_skills: dict[str, set[str]] = {}
    models_by_turn: dict[str, str] = {}
    events: Counter[str] = Counter()
    response_types: Counter[str] = Counter()
    failure_categories: Counter[str] = Counter()
    failure_tools: Counter[str] = Counter()
    failure_evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
    dates: Counter[str] = Counter()
    cwd_groups: Counter[str] = Counter()

    for session in sessions:
        unique_turns.update(session.user_messages_by_turn)
        started_turns.update(session.started_turn_ids)
        completed_turns.update(session.completed_turn_ids)
        aborted_turns.update(session.aborted_turn_ids)
        call_names.update(session.call_names)
        for call_id, skills in session.call_skills.items():
            call_skills.setdefault(call_id, set()).update(skills)
        models_by_turn.update(session.models_by_turn)
        events.update(session.event_counts)
        response_types.update(session.response_item_types)
        dates[session.rollout_date] += 1
        cwd_groups[cwd_group(session.cwd)] += 1
        for failure in session.failures:
            failure_tools[failure.tool] += 1
            for category in failure.categories:
                failure_categories[category] += 1
                rows = failure_evidence[category]
                evidence_key = (
                    session.effective_session_id,
                    failure.tool,
                )
                if len(rows) < limit and evidence_key not in {
                    (row["sessionId"], row["tool"]) for row in rows
                }:
                    rows.append(
                        {
                            "sessionId": session.effective_session_id,
                            "file": str(session.file),
                            "tool": failure.tool,
                        }
                    )

    intent_counts: Counter[str] = Counter()
    correction_counts: Counter[str] = Counter()
    correction_evidence: list[dict[str, str]] = []
    for turn_id, message in unique_turns.items():
        intent_counts.update(message_labels(message, INTENT_SIGNALS))
        corrections = message_labels(message.strip(), CORRECTION_SIGNALS)
        correction_counts.update(corrections)
        if corrections and len(correction_evidence) < limit:
            correction_evidence.append(
                {
                    "turnId": turn_id,
                    "signals": ",".join(corrections),
                    "message": redact_text(message),
                }
            )

    skill_counts: Counter[str] = Counter()
    for skills in call_skills.values():
        skill_counts.update(skills)
    model_counts = Counter(models_by_turn.values())
    tool_counts = Counter(call_names.values())

    return {
        "logicalTaskRoots": len({session.task_root for session in sessions}),
        "uniqueTurns": {
            "userAuthored": len(unique_turns),
            "started": len(started_turns),
            "completed": len(completed_turns),
            "aborted": len(aborted_turns),
        },
        "sessionsWithCompaction": sum(
            session.event_counts.get("context_compacted", 0) > 0 for session in sessions
        ),
        "compactionEvents": sum(
            session.event_counts.get("context_compacted", 0) for session in sessions
        ),
        "uniqueToolCalls": len(call_names),
        "tools": top(tool_counts, limit),
        "skillReads": top(skill_counts, limit),
        "models": top(model_counts, limit),
        "events": top(events, limit),
        "responseItemTypes": top(response_types, limit),
        "failureCategories": top(failure_categories, limit),
        "failureTools": top(failure_tools, limit),
        "failureEvidence": dict(failure_evidence),
        "intents": top(intent_counts, limit),
        "correctionSignals": top(correction_counts, limit),
        "correctionEvidence": correction_evidence,
        "dates": top(dates, limit),
        "cwdGroups": top(cwd_groups, limit),
    }


def session_outlier(session: Session) -> dict[str, Any]:
    """Create a compact evidence row for one direct session."""

    messages = session.user_messages
    return {
        "sessionId": session.effective_session_id,
        "taskRoot": session.task_root,
        "date": session.rollout_date,
        "file": str(session.file),
        "cwd": session.cwd,
        "userTurns": len(session.user_messages_by_turn) or len(messages),
        "toolCalls": len(session.call_names),
        "failures": len(session.failures),
        "compactions": session.event_counts.get("context_compacted", 0),
        "subagentEvents": session.event_counts.get("sub_agent_activity", 0),
        "firstPrompt": redact_text(messages[0] if messages else ""),
        "latestPrompt": redact_text(messages[-1] if messages else ""),
    }


def build_outliers(
    sessions: list[Session],
    limit: int,
) -> dict[str, list[dict[str, Any]]]:
    """Rank direct sessions by conversation, tools, failures, and compaction."""

    rows = [session_outlier(session) for session in sessions]
    rankings = {
        "longConversations": ("userTurns", "toolCalls"),
        "toolHeavy": ("toolCalls", "userTurns"),
        "failureHeavy": ("failures", "toolCalls"),
        "compactionHeavy": ("compactions", "userTurns"),
        "delegationHeavy": ("subagentEvents", "toolCalls"),
    }
    output: dict[str, list[dict[str, Any]]] = {}
    for name, keys in rankings.items():
        output[name] = sorted(
            rows,
            key=lambda row: tuple(int(row[key]) for key in keys),
            reverse=True,
        )[:limit]
    return output


def build_task_families(
    sessions: list[Session],
    limit: int,
) -> list[dict[str, Any]]:
    """Group inherited rollouts so forks and their subagents stay together."""

    groups: dict[str, list[Session]] = defaultdict(list)
    for session in sessions:
        groups[session.task_root].append(session)

    families = []
    for task_root, members in groups.items():
        direct = [session for session in members if session.kind == "direct"]
        subagents = [session for session in members if session.kind == "subagent"]
        user_turns: dict[str, str] = {}
        calls: dict[str, str] = {}
        failure_count = 0
        for session in direct:
            user_turns.update(session.user_messages_by_turn)
            calls.update(session.call_names)
            failure_count += len(session.failures)
        messages = list(user_turns.values())
        if not messages:
            for session in direct:
                messages.extend(session.user_messages)
        families.append(
            {
                "taskRoot": task_root,
                "directSessions": len(direct),
                "subagentSessions": len(subagents),
                "userTurns": len(user_turns) or len(dict.fromkeys(messages)),
                "toolCalls": len(calls),
                "failures": failure_count,
                "compactions": max(
                    (
                        session.event_counts.get("context_compacted", 0)
                        for session in direct
                    ),
                    default=0,
                ),
                "firstPrompt": redact_text(messages[0] if messages else ""),
                "latestPrompts": [
                    redact_text(session.user_messages[-1])
                    for session in sorted(
                        direct,
                        key=lambda item: (item.ended_at, item.rollout_date),
                    )
                    if session.user_messages
                ][-5:],
                "sessionIds": [
                    session.effective_session_id
                    for session in sorted(direct, key=lambda item: item.started_at)
                ],
                "files": [
                    str(session.file)
                    for session in sorted(direct, key=lambda item: item.started_at)
                ],
            }
        )
    return sorted(
        families,
        key=lambda row: (
            int(row["userTurns"]),
            int(row["toolCalls"]),
            int(row["directSessions"]),
        ),
        reverse=True,
    )[:limit]


def build_report(
    sessions: list[Session],
    selected_file_count: int,
    duplicate_count: int,
    start: date,
    end: date,
    roots: list[Path],
    limit: int,
) -> dict[str, Any]:
    """Assemble the final JSON report."""

    direct = [session for session in sessions if session.kind == "direct"]
    subagents = [session for session in sessions if session.kind == "subagent"]
    internal = [session for session in sessions if session.kind == "internal"]
    parse_errors = sum(session.parse_errors for session in sessions)
    total_bytes = sum(session.byte_count for session in sessions)
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now().astimezone().isoformat(),
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "selection": "inclusive date embedded in rollout filename",
        },
        "roots": [str(root) for root in roots],
        "corpus": {
            "selectedFiles": selected_file_count,
            "duplicateSessionCopies": duplicate_count,
            "uniqueSessions": len(sessions),
            "directSessions": len(direct),
            "subagentSessions": len(subagents),
            "internalSessions": len(internal),
            "totalMiB": round(total_bytes / 1024 / 1024, 1),
            "parseErrors": parse_errors,
        },
        "direct": summarize_direct_sessions(direct, limit),
        "taskFamilies": build_task_families(sessions, limit),
        "outliers": build_outliers(direct, limit),
    }


def write_report(report: dict[str, Any], output_path: Path | None) -> None:
    """Write JSON to stdout or a requested scratch artifact."""

    serialized = json.dumps(report, indent=2, sort_keys=False) + "\n"
    if output_path is None:
        print(serialized, end="")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized, encoding="utf-8")
    print(output_path)


def main() -> None:
    """Run the inventory command."""

    parser = build_parser()
    arguments = parser.parse_args()
    start, end = resolve_window(arguments)
    roots = arguments.roots or default_codex_roots()
    selected = select_rollouts(
        roots,
        start,
        end,
        set(arguments.exclude_session_id),
    )
    parsed = [parse_session(file_path, match) for file_path, match in selected]
    sessions, duplicate_count = deduplicate_sessions(parsed)
    report = build_report(
        sessions,
        len(selected),
        duplicate_count,
        start,
        end,
        roots,
        arguments.limit,
    )
    write_report(report, arguments.output)


if __name__ == "__main__":
    main()
