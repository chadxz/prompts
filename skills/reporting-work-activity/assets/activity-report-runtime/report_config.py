from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "dist"
SLACK_SNAPSHOT_FILE = DATA_DIR / "slack_channels.json"
NOTION_SNAPSHOT_FILE = DATA_DIR / "notion_pages.json"
START = datetime(2026, 5, 4, tzinfo=UTC)
END = datetime(2026, 5, 12, tzinfo=UTC)
REPORT_TITLE = "Convergint Weekly Activity Report"
ORG = "convergint"
LINEAR_WORKSPACE = "convergint"
WINDOW_START = START.date().isoformat()
WINDOW_END = (END - timedelta(days=1)).date().isoformat()
REPORT_SERVER_PORT = 8765
REPORT_SERVER_ORIGIN = f"http://127.0.0.1:{REPORT_SERVER_PORT}"
MUTED_SLACK_CHANNELS_FILE = ROOT / "muted_slack_channels.json"
REQUIRED_DATA_FILES = [
    "github_issues_closed.json",
    "github_issues_created.json",
    "github_prs_created.json",
    "github_prs_merged.json",
    "github_repos.json",
    "linear_issues_updated.json",
    "linear_projects_month.json",
    "linear_teams.json",
    "slack_channels.json",
    "notion_pages.json",
]
