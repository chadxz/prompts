from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "dist"
SLACK_SNAPSHOT_FILE = DATA_DIR / "slack_channels.json"
NOTION_SNAPSHOT_FILE = DATA_DIR / "notion_pages.json"
DATADOG_SNAPSHOT_FILE = DATA_DIR / "datadog_activity.json"
REPORT_TIMEZONE = ZoneInfo(os.environ.get("REPORT_TIMEZONE", "America/Chicago"))
REPORT_DATE = date.fromisoformat(
    os.environ.get("REPORT_DATE", datetime.now(REPORT_TIMEZONE).date().isoformat())
)
START_DATE = REPORT_DATE - timedelta(days=6)
END_DATE = REPORT_DATE
START = datetime.combine(START_DATE, time.min, REPORT_TIMEZONE).astimezone(UTC)
END = datetime.combine(END_DATE + timedelta(days=1), time.min, REPORT_TIMEZONE).astimezone(UTC)
REPORT_TITLE = "Chad McElligott Weekly Activity Report"
ORG = "convergint"
LINEAR_WORKSPACE = "convergint"
WINDOW_START = START_DATE.isoformat()
WINDOW_END = END_DATE.isoformat()
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
    "datadog_activity.json",
]
