"""Protect report claims against stale or unsupported cross-agent evidence."""

from copy import deepcopy

import pytest

from agent_session_evidence import validate_agent_sessions


def evidence_snapshot() -> dict:
    """Build a resumed-work example with honest, incomplete archive coverage."""

    cutoff = "2026-10-02T14:00:00Z"
    return {
        "window": {
            "start": "2026-09-26",
            "end": "2026-10-02",
            "timezone": "America/Chicago",
        },
        "refreshed_at": cutoff,
        "coverage": {
            agent: {"status": coverage, "detail": "Archive checked.", "cutoff": cutoff}
            for agent, coverage in [
                ("codex", "reviewed"),
                ("claude", "no_sessions"),
                ("cursor", "partial"),
            ]
        },
        "sessions": [
            {
                "agent": "codex",
                "session_id": "began-before-window",
                "activity_at": "2026-09-26T05:00:00Z",
                "topic": "Resumed implementation",
                "summary": "The change merged this week.",
                "status": "completed",
                "corroboration": "Verified merge date in the current PR.",
                "evidence": [{"label": "Merged PR", "url": "https://example.com/pr/1"}],
            }
        ],
    }


def validate(snapshot: dict) -> list[str]:
    """Apply the report's local-date boundaries to an evidence fixture."""

    return validate_agent_sessions(snapshot, "2026-09-26", "2026-10-02", "America/Chicago")


def test_resumed_work_and_capture_gaps_are_allowed() -> None:
    assert validate(evidence_snapshot()) == []


@pytest.mark.parametrize(
    "activity",
    ["2026-09-26T04:59:59Z", "2026-10-03T05:00:00Z", "2026-10-02T14:00:01Z", None],
)
def test_out_of_window_and_after_cutoff_activity_is_rejected(activity) -> None:
    snapshot = evidence_snapshot()
    snapshot["sessions"][0]["activity_at"] = activity
    assert any("activity timestamp" in error for error in validate(snapshot))


def test_completion_requires_proof_but_a_draft_can_remain_unfinished() -> None:
    snapshot = evidence_snapshot()
    del snapshot["sessions"][0]["corroboration"]
    assert any("corroboration" in error for error in validate(snapshot))
    snapshot["sessions"][0]["status"] = "in_progress"
    assert validate(snapshot) == []


def test_every_agent_requires_a_coverage_receipt() -> None:
    snapshot = evidence_snapshot()
    del snapshot["coverage"]["cursor"]
    assert any("cursor coverage" in error for error in validate(snapshot))


def test_stale_window_and_ambiguous_cutoff_are_rejected() -> None:
    snapshot = evidence_snapshot()
    snapshot["window"]["end"] = "2026-09-25"
    snapshot["coverage"]["cursor"]["cutoff"] = "2026-10-02T14:00:00"
    errors = validate(snapshot)
    assert any("window" in error for error in errors)
    assert any("cursor cutoff" in error for error in errors)


def test_same_session_outcome_cannot_be_repeated() -> None:
    snapshot = evidence_snapshot()
    snapshot["sessions"].append(deepcopy(snapshot["sessions"][0]))
    assert any("Duplicate" in error for error in validate(snapshot))
