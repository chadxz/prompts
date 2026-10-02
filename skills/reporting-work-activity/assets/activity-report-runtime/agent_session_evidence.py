"""Validate the curated cross-agent evidence used by weekly reports."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

AGENTS = ("codex", "claude", "cursor")
COVERAGE_STATUSES = {"reviewed", "no_sessions", "partial", "unavailable"}


def parse_aware_timestamp(value: object) -> datetime:
    """Parse an evidence timestamp without accepting local-time ambiguity."""

    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("missing timezone")
    return timestamp


def validate_agent_sessions(snapshot: dict, start: str, end: str, timezone: str) -> list[str]:
    """Reject stale evidence and unsupported completion claims, allowing capture gaps."""

    errors = []
    expected = {"start": start, "end": end, "timezone": timezone}
    if snapshot.get("window") != expected:
        errors.append("Agent session evidence window does not match the report.")
    zone = ZoneInfo(timezone)
    start_at = datetime.combine(datetime.fromisoformat(start).date(), time.min, zone)
    end_at = datetime.combine(
        datetime.fromisoformat(end).date() + timedelta(days=1), time.min, zone
    )
    coverage = snapshot.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}
    for agent in AGENTS:
        entry = coverage.get(agent)
        if (
            not isinstance(entry, dict)
            or entry.get("status") not in COVERAGE_STATUSES
            or not isinstance(entry.get("detail"), str)
            or not entry["detail"].strip()
            or not entry.get("cutoff")
        ):
            errors.append(f"Agent session evidence requires explicit {agent} coverage.")
        elif entry:
            try:
                parse_aware_timestamp(entry.get("cutoff"))
            except ValueError:
                errors.append(f"Agent session evidence requires an aware {agent} cutoff.")
    cutoff = None
    try:
        cutoff = parse_aware_timestamp(snapshot.get("refreshed_at"))
    except ValueError:
        errors.append("Agent session evidence requires an aware refresh timestamp.")
    sessions = snapshot.get("sessions")
    if not isinstance(sessions, list):
        return errors + ["Agent session evidence requires a sessions list."]
    seen = set()
    for index, entry in enumerate(sessions):
        if not isinstance(entry, dict):
            errors.append(f"Agent evidence item {index} must be an object.")
            continue
        key = (entry.get("agent"), entry.get("session_id"), entry.get("topic"))
        if key in seen:
            errors.append(f"Duplicate agent evidence item {index}.")
        seen.add(key)
        if entry.get("agent") not in AGENTS:
            errors.append(f"Unknown agent in evidence item {index}.")
        for field in ("session_id", "topic", "summary"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"Agent evidence item {index} requires {field}.")
        try:
            activity = parse_aware_timestamp(entry.get("activity_at"))
            if not start_at <= activity < end_at:
                raise ValueError("outside window")
            if cutoff is not None and activity.astimezone(UTC) > cutoff.astimezone(UTC):
                raise ValueError("after cutoff")
        except ValueError:
            errors.append(f"Agent evidence item {index} has an invalid activity timestamp.")
        if entry.get("status") not in {"completed", "in_progress", "exploratory"}:
            errors.append(f"Agent evidence item {index} requires an explicit work status.")
        if entry.get("status") == "completed" and (
            not isinstance(entry.get("corroboration"), str) or not entry["corroboration"].strip()
        ):
            errors.append(f"Completed agent evidence item {index} requires corroboration.")
        if not isinstance(entry.get("evidence"), list):
            errors.append(f"Agent evidence item {index} requires an evidence list.")
    return errors
