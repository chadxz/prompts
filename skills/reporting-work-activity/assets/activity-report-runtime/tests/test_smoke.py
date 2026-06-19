from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_module(module_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / file_name)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


generate_report = load_module("generate_report", "generate_report.py")
populate_data = load_module("populate_data", "populate_data.py")
clear_runtime_cache = load_module("clear_runtime_cache", "clear_runtime_cache.py")
report_server = load_module("report_server", "report_server.py")


def test_slugify_normalizes_report_labels() -> None:
    assert generate_report.slugify("Engineering Enablement") == "engineering-enablement"
    assert generate_report.slugify("EE") == "ee"


def test_load_muted_channels_ignores_invalid_json(tmp_path, monkeypatch) -> None:
    muted_file = tmp_path / "muted.json"
    muted_file.write_text("{not json")
    monkeypatch.setattr(report_server, "MUTED_SLACK_CHANNELS_FILE", muted_file)

    assert report_server.load_muted_channels() == []


def test_save_muted_channels_deduplicates_and_sorts(tmp_path, monkeypatch) -> None:
    muted_file = tmp_path / "muted.json"
    monkeypatch.setattr(report_server, "MUTED_SLACK_CHANNELS_FILE", muted_file)

    report_server.save_muted_channels(["#beta", "#alpha", "#beta"])

    assert report_server.load_muted_channels() == ["#alpha", "#beta"]


def test_validate_data_dir_lists_missing_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(generate_report, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        generate_report,
        "REQUIRED_DATA_FILES",
        ["github_repos.json", "linear_issues_updated.json"],
    )

    try:
        generate_report.validate_data_dir()
    except SystemExit as exc:
        message = str(exc)
    else:
        raise AssertionError("validate_data_dir should exit when required files are missing")

    assert "Missing private report data in data/." in message
    assert "mise run fetch" in message
    assert "$reporting-work-activity" in message
    assert "- github_repos.json" in message
    assert "- linear_issues_updated.json" in message


def test_dedupe_linear_issues_keeps_latest_unique_issue() -> None:
    older = {"id": "1", "identifier": "EE-1", "updatedAt": "2026-05-10T10:00:00Z"}
    newer = {"id": "1", "identifier": "EE-1", "updatedAt": "2026-05-11T10:00:00Z"}
    other = {"id": "2", "identifier": "GAM-2", "updatedAt": "2026-05-11T09:00:00Z"}

    deduped = populate_data.dedupe_linear_issues([[older, other], [newer]])

    assert deduped == [newer, other]


def test_personal_filters_match_chad_only() -> None:
    assert generate_report.is_personal_github_pr(
        {"author": {"login": generate_report.PERSON_GITHUB_LOGIN}}
    )
    assert not generate_report.is_personal_github_pr({"author": {"login": "someone-else"}})
    assert generate_report.is_personal_linear_issue(
        {"assignee": {"name": generate_report.PERSON_LINEAR_ASSIGNEE}}
    )
    assert not generate_report.is_personal_linear_issue({"assignee": None})


def test_load_slack_highlights_requires_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(generate_report, "SLACK_SNAPSHOT_FILE", tmp_path / "slack.json")

    try:
        generate_report.load_slack_highlights()
    except SystemExit as exc:
        message = str(exc)
    else:
        raise AssertionError("load_slack_highlights should exit when the snapshot is missing")

    assert "slack.json" in message
    assert "$reporting-work-activity" in message


def test_load_notion_highlights_prefers_snapshot(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "notion.json"
    snapshot_path.write_text(
        json.dumps(
            [
                {
                    "title": "Fresh Notion Page",
                    "date": "May 11",
                    "kind": "program hub",
                    "url": "https://www.notion.so/example",
                    "summary": "Fresh connector-backed summary.",
                }
            ]
        )
    )
    monkeypatch.setattr(generate_report, "NOTION_SNAPSHOT_FILE", snapshot_path)

    highlights = generate_report.load_notion_highlights()

    assert highlights == [
        {
            "title": "Fresh Notion Page",
            "date": "May 11",
            "kind": "program hub",
            "url": "https://www.notion.so/example",
            "summary": "Fresh connector-backed summary.",
        }
    ]


def test_load_datadog_activity_requires_object_snapshot(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "datadog.json"
    snapshot_path.write_text("[]")
    monkeypatch.setattr(generate_report, "DATADOG_SNAPSHOT_FILE", snapshot_path)

    try:
        generate_report.load_datadog_activity()
    except SystemExit as exc:
        message = str(exc)
    else:
        raise AssertionError("load_datadog_activity should exit when the snapshot is invalid")

    assert "datadog.json" in message
    assert "Expected a JSON object" in message


def test_report_sources_reads_private_config(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "tracked_sources.json"
    config_path.write_text(
        json.dumps(
            {
                "slack_channels": [
                    {
                        "channel": "#example-channel",
                        "url": "https://app.slack.com/client/T123/C456",
                        "focus": "Watch delivery workflow traffic.",
                    }
                ],
                "notion_pages": [
                    {
                        "title": "Example page",
                        "url": "https://www.notion.so/example",
                        "focus": "Watch rollout and status updates.",
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("REPORT_TRACKED_SOURCES_FILE", str(config_path))

    report_sources = load_module("report_sources_test", "report_sources.py")

    assert report_sources.load_tracked_sources()["slack_channels"] == [
        {
            "channel": "#example-channel",
            "url": "https://app.slack.com/client/T123/C456",
            "focus": "Watch delivery workflow traffic.",
        }
    ]
    assert report_sources.load_tracked_sources()["notion_pages"] == [
        {
            "title": "Example page",
            "url": "https://www.notion.so/example",
            "focus": "Watch rollout and status updates.",
        }
    ]


def test_report_sources_bootstrap_from_summary(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "tracked_sources.json"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "slack_highlights": [
                    {
                        "channel": "#example-channel",
                        "theme": "Watch delivery workflow traffic.",
                    }
                ],
                "notion_highlights": [
                    {
                        "title": "Example page",
                        "url": "https://www.notion.so/example",
                        "summary": "Watch rollout and status updates.",
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("REPORT_TRACKED_SOURCES_FILE", str(config_path))

    report_sources = load_module("report_sources_bootstrap_test", "report_sources.py")
    monkeypatch.setattr(report_sources, "SUMMARY_SNAPSHOT_FILE", summary_path)
    monkeypatch.setattr(report_sources, "SLACK_SNAPSHOT_FILE", tmp_path / "missing-slack.json")
    monkeypatch.setattr(report_sources, "NOTION_SNAPSHOT_FILE", tmp_path / "missing-notion.json")
    report_sources.load_tracked_sources.cache_clear()

    tracked = report_sources.load_tracked_sources()

    assert config_path.exists()
    assert tracked == {
        "slack_channels": [
            {
                "channel": "#example-channel",
                "focus": "Watch delivery workflow traffic.",
            }
        ],
        "notion_pages": [
            {
                "title": "Example page",
                "url": "https://www.notion.so/example",
                "focus": "Watch rollout and status updates.",
            }
        ],
    }


def test_clear_runtime_cache_removes_generated_artifacts(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "dist"
    team_dump_dir = data_dir / "linear_team_dumps"
    data_dir.mkdir()
    output_dir.mkdir()
    team_dump_dir.mkdir(parents=True)

    tracked_sources = tmp_path / "tracked_sources.json"
    muted = tmp_path / "muted_slack_channels.json"
    tracked_sources.write_text("{}")
    muted.write_text("[]")
    (data_dir / "github_repos.json").write_text("[]")
    (data_dir / "slack_channels.json").write_text("[]")
    (team_dump_dir / "team.json").write_text("[]")
    (output_dir / "index.html").write_text("<html></html>")

    monkeypatch.setattr(clear_runtime_cache, "DATA_DIR", data_dir)
    monkeypatch.setattr(clear_runtime_cache, "OUTPUT_DIR", output_dir)

    removed = clear_runtime_cache.clear_runtime_cache()

    assert "data/github_repos.json" in removed
    assert "data/slack_channels.json" in removed
    assert "data/linear_team_dumps/team.json" in removed
    assert "dist/index.html" in removed
    assert tracked_sources.exists()
    assert muted.exists()
    assert not (data_dir / "github_repos.json").exists()
    assert not (data_dir / "slack_channels.json").exists()
    assert not (team_dump_dir / "team.json").exists()
    assert output_dir.exists()
