from __future__ import annotations

import html
import json
import math
import re
import struct
import zlib
from binascii import crc32
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus

from report_config import (
    DATA_DIR,
    DATADOG_SNAPSHOT_FILE,
    END,
    LINEAR_WORKSPACE,
    MUTED_SLACK_CHANNELS_FILE,
    NOTION_SNAPSHOT_FILE,
    ORG,
    OUTPUT_DIR,
    REPORT_SERVER_ORIGIN,
    REPORT_TIMEZONE,
    REPORT_TITLE,
    REQUIRED_DATA_FILES,
    SLACK_SNAPSHOT_FILE,
    START,
    WINDOW_END,
    WINDOW_START,
)

PERSON_NAME = "Chad McElligott"
PERSON_GITHUB_LOGIN = "chadxz"
PERSON_LINEAR_ASSIGNEE = "Chad McElligott"
HERO_IMAGE_PATH = OUTPUT_DIR / "assets" / "platform-work-hero.png"


def load_json(name: str):
    return json.loads((DATA_DIR / name).read_text())


def load_snapshot(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(
            "Missing required report snapshot.\n"
            f"- {path.name}\n"
            "Run $reporting-work-activity so Slack and Notion are pulled before building the report."
        )
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        raise SystemExit(
            "Invalid report snapshot JSON.\n"
            f"- {path.name}\n"
            "Refresh the snapshot with $reporting-work-activity before building the report."
        ) from None
    if not isinstance(data, list):
        raise SystemExit(
            "Invalid report snapshot shape.\n"
            f"- {path.name}\n"
            "Expected a JSON list. Refresh the snapshot with $reporting-work-activity."
        )
    records = [item for item in data if isinstance(item, dict)]
    if not records:
        raise SystemExit(
            "Empty report snapshot.\n"
            f"- {path.name}\n"
            "Refresh the snapshot with $reporting-work-activity before building the report."
        )
    return records


def validate_data_dir() -> None:
    missing = [name for name in REQUIRED_DATA_FILES if not (DATA_DIR / name).exists()]
    if not missing:
        return

    lines = [
        "Missing private report data in data/.",
        "Run `mise run fetch` for GitHub and Linear, then run `$reporting-work-activity` so Slack and Notion are pulled before building the report.",
        "Missing files:",
        *(f"- {name}" for name in missing),
    ]
    raise SystemExit("\n".join(lines))


def load_muted_slack_channels() -> set[str]:
    if not MUTED_SLACK_CHANNELS_FILE.exists():
        return set()
    try:
        data = json.loads(MUTED_SLACK_CHANNELS_FILE.read_text())
    except json.JSONDecodeError:
        return set()
    if not isinstance(data, list):
        return set()
    return {item for item in data if isinstance(item, str) and item}


def load_slack_highlights() -> list[dict]:
    raw_items = load_snapshot(SLACK_SNAPSHOT_FILE)
    highlights = []
    for item in raw_items:
        channel = item.get("channel")
        theme = item.get("theme")
        if not isinstance(channel, str) or not isinstance(theme, str):
            continue
        details = item.get("details", [])
        if not isinstance(details, list):
            details = []
        highlight = {
            "channel": channel,
            "theme": theme,
            "details": [detail for detail in details if isinstance(detail, str)],
        }
        if isinstance(item.get("url"), str):
            highlight["url"] = item["url"]
        highlights.append(highlight)
    if not highlights:
        raise SystemExit(
            "Slack snapshot did not contain any valid channel cards.\n"
            f"- {SLACK_SNAPSHOT_FILE.name}\n"
            "Refresh it with $reporting-work-activity before building the report."
        )
    return highlights


def load_notion_highlights() -> list[dict]:
    raw_items = load_snapshot(NOTION_SNAPSHOT_FILE)
    highlights = []
    for item in raw_items:
        title = item.get("title")
        date = item.get("date")
        kind = item.get("kind")
        url = item.get("url")
        summary = item.get("summary")
        if not all(isinstance(value, str) and value for value in [title, date, kind, url, summary]):
            continue
        highlights.append(
            {
                "title": title,
                "date": date,
                "kind": kind,
                "url": url,
                "summary": summary,
            }
        )
    if not highlights:
        raise SystemExit(
            "Notion snapshot did not contain any valid page cards.\n"
            f"- {NOTION_SNAPSHOT_FILE.name}\n"
            "Refresh it with $reporting-work-activity before building the report."
        )
    return highlights


def load_datadog_activity() -> dict:
    if not DATADOG_SNAPSHOT_FILE.exists():
        raise SystemExit(
            "Missing required Datadog activity snapshot.\n"
            f"- {DATADOG_SNAPSHOT_FILE.name}\n"
            "Refresh Datadog evidence before building the report."
        )
    try:
        data = json.loads(DATADOG_SNAPSHOT_FILE.read_text())
    except json.JSONDecodeError:
        raise SystemExit(
            "Invalid Datadog activity snapshot JSON.\n"
            f"- {DATADOG_SNAPSHOT_FILE.name}\n"
            "Refresh Datadog evidence before building the report."
        ) from None
    if not isinstance(data, dict):
        raise SystemExit(
            "Invalid Datadog activity snapshot shape.\n"
            f"- {DATADOG_SNAPSHOT_FILE.name}\n"
            "Expected a JSON object with counts, highlights, and lowlights."
        )
    return data


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def in_window(dt: datetime | None) -> bool:
    return bool(dt and START <= dt < END)


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def link_text(label: str, href: str, class_name: str = "") -> str:
    class_attr = f' class="{esc(class_name)}"' if class_name else ""
    return f'<a{class_attr} href="{esc(href)}">{esc(label)}</a>'


def link_html(inner_html: str, href: str, class_name: str = "") -> str:
    class_attr = f' class="{esc(class_name)}"' if class_name else ""
    return f'<a{class_attr} href="{esc(href)}">{inner_html}</a>'


def fmt_date(value: str | None) -> str:
    dt = parse_dt(value)
    return dt.astimezone(UTC).strftime("%b %d") if dt else "-"


def fmt_datetime(value: str | None) -> str:
    dt = parse_dt(value)
    return dt.astimezone(UTC).strftime("%b %d %H:%M UTC") if dt else "-"


def fmt_report_date(value: str) -> str:
    dt = datetime.strptime(value, "%Y-%m-%d")
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def report_window_label() -> str:
    start = datetime.strptime(WINDOW_START, "%Y-%m-%d")
    end = datetime.strptime(WINDOW_END, "%Y-%m-%d")
    if start.year == end.year and start.month == end.month:
        return (
            f"{start.strftime('%B')} {start.day} through {end.strftime('%B')} {end.day}, {end.year}"
        )
    if start.year == end.year:
        return (
            f"{start.strftime('%B')} {start.day} through {end.strftime('%B')} {end.day}, {end.year}"
        )
    return f"{fmt_report_date(WINDOW_START)} through {fmt_report_date(WINDOW_END)}"


def generated_label() -> str:
    return datetime.now(UTC).strftime("%b %d, %Y %H:%M UTC")


def fmt_pct(value: float) -> str:
    return f"{round(value * 100)}%"


def gh_search_url(query: str, search_type: str) -> str:
    return f"https://github.com/search?q={quote_plus(query)}&type={search_type}"


def gh_repo_url(full_name: str) -> str:
    return f"https://github.com/{full_name}"


def gh_org_repos_url() -> str:
    return f"https://github.com/orgs/{ORG}/repositories"


def gh_pr_search_url(
    repo: str | None = None, author: str | None = None, merged: bool = False
) -> str:
    terms = ["is:pr", "archived:false"]
    if repo:
        terms.append(f"repo:{repo}")
    else:
        terms.append(f"org:{ORG}")
    if author:
        terms.append(f"author:{author}")
    if merged:
        terms.extend(["is:merged", f"merged:{WINDOW_START}..{WINDOW_END}"])
        return gh_search_url(" ".join(terms), "pullrequests")
    terms.append(f"created:{WINDOW_START}..{WINDOW_END}")
    return gh_search_url(" ".join(terms), "pullrequests")


def gh_issue_search_url(repo: str | None = None, closed: bool = False) -> str:
    terms = ["is:issue", "archived:false"]
    if repo:
        terms.append(f"repo:{repo}")
    else:
        terms.append(f"org:{ORG}")
    if closed:
        terms.extend(["is:closed", f"closed:{WINDOW_START}..{WINDOW_END}"])
    else:
        terms.append(f"created:{WINDOW_START}..{WINDOW_END}")
    return gh_search_url(" ".join(terms), "issues")


def gh_author_search_url(login: str, merged: bool = False) -> str:
    return gh_pr_search_url(author=login, merged=merged)


def linear_team_url(team_key: str) -> str:
    return f"https://linear.app/{LINEAR_WORKSPACE}/team/{team_key}/all"


def report_page(name: str) -> str:
    return name


def linear_team_page(team_key: str) -> str:
    return report_page(f"linear-team-{slugify(team_key)}-updated.html")


def linear_state_page(state_name: str) -> str:
    return report_page(f"linear-state-{slugify(state_name)}-updated.html")


def output_path(name: str) -> Path:
    return OUTPUT_DIR / name


def bar(value: int, maximum: int, href: str | None = None) -> str:
    width = 0 if maximum == 0 else max(8, math.ceil(value / maximum * 100))
    inner = (
        '<div class="bar-cell">'
        f'<span class="bar-fill" style="width:{width}%"></span>'
        f'<span class="bar-value">{value}</span>'
        "</div>"
    )
    if href:
        return link_html(inner, href, "bar-link")
    return inner


def top_counter_rows(counter: Counter, limit: int = 10):
    return counter.most_common(limit)


def repo_name(item: dict) -> str:
    repo = item.get("repository") or {}
    return repo.get("nameWithOwner") or item.get("nameWithOwner") or ""


def team_name(team: dict | None) -> str:
    if not team:
        return "-"
    return team.get("name") or team.get("key") or "-"


def is_bot(author: dict | None) -> bool:
    if not author:
        return False
    login = author.get("login", "")
    return author.get("type") == "Bot" or login.endswith("[bot]")


def is_personal_github_pr(item: dict) -> bool:
    author = item.get("author")
    return bool(author and author.get("login") == PERSON_GITHUB_LOGIN)


def is_personal_linear_issue(issue: dict) -> bool:
    assignee = issue.get("assignee")
    return bool(assignee and assignee.get("name") == PERSON_LINEAR_ASSIGNEE)


NOISE_TITLE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^mock\d*$",
        r"^sit$",
        r"^files$",
        r"^techdev$",
        r"^test_demo$",
        r"^feature reviewnow$",
        r"^r\d+sf\w+$",
    ]
]


def is_noise_title(title: str) -> bool:
    normalized = title.strip()
    return any(pattern.match(normalized) for pattern in NOISE_TITLE_PATTERNS)


def github_summary() -> dict:
    repos = load_json("github_repos.json")
    prs_created = load_json("github_prs_created.json")
    prs_merged = load_json("github_prs_merged.json")
    issues_created = load_json("github_issues_created.json")
    issues_closed = load_json("github_issues_closed.json")

    active_repos = [repo for repo in repos if in_window(parse_dt(repo.get("pushedAt")))]
    created_repo_counts = Counter(repo_name(pr) for pr in prs_created)
    merged_repo_counts = Counter(repo_name(pr) for pr in prs_merged)
    issue_created_repo_counts = Counter(repo_name(issue) for issue in issues_created)
    issue_closed_repo_counts = Counter(repo_name(issue) for issue in issues_closed)
    created_author_counts = Counter(
        pr["author"]["login"] for pr in prs_created if pr.get("author") and not is_bot(pr["author"])
    )
    merged_author_counts = Counter(
        pr["author"]["login"] for pr in prs_merged if pr.get("author") and not is_bot(pr["author"])
    )

    interesting_merged = [
        pr
        for pr in prs_merged
        if pr.get("author") and not is_bot(pr["author"]) and not is_noise_title(pr.get("title", ""))
    ]
    interesting_merged.sort(
        key=lambda pr: (
            pr.get("commentsCount", 0),
            parse_dt(pr.get("closedAt")) or START,
        ),
        reverse=True,
    )

    recent_pushes = sorted(
        active_repos,
        key=lambda repo: parse_dt(repo.get("pushedAt")) or START,
        reverse=True,
    )
    personal_created = sorted(
        [pr for pr in prs_created if is_personal_github_pr(pr)],
        key=lambda pr: parse_dt(pr.get("createdAt")) or START,
        reverse=True,
    )
    personal_merged = sorted(
        [pr for pr in prs_merged if is_personal_github_pr(pr)],
        key=lambda pr: parse_dt(pr.get("closedAt")) or START,
        reverse=True,
    )
    personal_created_repo_counts = Counter(repo_name(pr) for pr in personal_created)
    personal_merged_repo_counts = Counter(repo_name(pr) for pr in personal_merged)
    personal_open_prs = [pr for pr in personal_created if pr.get("state") == "open"]

    created_states = Counter(pr.get("state", "unknown") for pr in prs_created)

    return {
        "repos_total": len(repos),
        "repos_active_week": len(active_repos),
        "prs_created": len(prs_created),
        "prs_created_human": sum(1 for pr in prs_created if not is_bot(pr.get("author"))),
        "prs_created_bot": sum(1 for pr in prs_created if is_bot(pr.get("author"))),
        "prs_created_open": created_states.get("open", 0),
        "prs_created_closed": created_states.get("closed", 0),
        "prs_created_merged": created_states.get("merged", 0),
        "prs_merged": len(prs_merged),
        "prs_merged_human": sum(1 for pr in prs_merged if not is_bot(pr.get("author"))),
        "prs_merged_bot": sum(1 for pr in prs_merged if is_bot(pr.get("author"))),
        "issues_created": len(issues_created),
        "issues_closed": len(issues_closed),
        "top_pr_repos": top_counter_rows(created_repo_counts),
        "top_merged_repos": top_counter_rows(merged_repo_counts),
        "top_issue_created_repos": top_counter_rows(issue_created_repo_counts),
        "top_issue_closed_repos": top_counter_rows(issue_closed_repo_counts),
        "top_created_authors": top_counter_rows(created_author_counts, 8),
        "top_merged_authors": top_counter_rows(merged_author_counts, 8),
        "interesting_merged": interesting_merged[:12],
        "recent_pushes": recent_pushes[:12],
        "personal_login": PERSON_GITHUB_LOGIN,
        "personal_prs_created": len(personal_created),
        "personal_prs_merged": len(personal_merged),
        "personal_prs_open": len(personal_open_prs),
        "personal_top_pr_repos": top_counter_rows(personal_created_repo_counts),
        "personal_top_merged_repos": top_counter_rows(personal_merged_repo_counts),
        "personal_created_items": personal_created,
        "personal_merged_items": personal_merged,
        "personal_open_items": personal_open_prs,
    }


def linear_summary() -> dict:
    issues = load_json("linear_issues_updated.json")
    projects = load_json("linear_projects_month.json")

    updated = [issue for issue in issues if in_window(parse_dt(issue.get("updatedAt")))]
    created = [issue for issue in issues if in_window(parse_dt(issue.get("createdAt")))]
    done_like = [issue for issue in updated if issue.get("state", {}).get("type") == "completed"]
    blocked = [
        issue for issue in updated if issue.get("state", {}).get("name", "").lower() == "blocked"
    ]
    team_names = {
        issue["team"]["key"]: team_name(issue.get("team"))
        for issue in issues
        if issue.get("team") and issue["team"].get("key")
    }

    team_updated = Counter(
        issue["team"]["key"] for issue in updated if issue.get("team") and issue["team"].get("key")
    )
    team_created = Counter(
        issue["team"]["key"] for issue in created if issue.get("team") and issue["team"].get("key")
    )
    state_updated = Counter(issue.get("state", {}).get("name", "Unknown") for issue in updated)

    projects_created = [
        project for project in projects if in_window(parse_dt(project.get("createdAt")))
    ]
    projects_updated = [
        project for project in projects if in_window(parse_dt(project.get("updatedAt")))
    ]

    updated.sort(key=lambda issue: parse_dt(issue.get("updatedAt")) or START, reverse=True)
    created.sort(key=lambda issue: parse_dt(issue.get("createdAt")) or START, reverse=True)
    done_like.sort(key=lambda issue: parse_dt(issue.get("updatedAt")) or START, reverse=True)
    projects_created.sort(
        key=lambda project: parse_dt(project.get("createdAt")) or START, reverse=True
    )
    projects_updated.sort(
        key=lambda project: parse_dt(project.get("updatedAt")) or START, reverse=True
    )
    interesting_lookup = {
        issue["identifier"]: issue for issue in updated if issue.get("identifier")
    }
    interesting = []
    for identifier, why in LINEAR_INTERESTING_NOTES:
        issue = interesting_lookup.get(identifier)
        if not issue:
            continue
        interesting.append(
            {
                "identifier": identifier,
                "title": issue.get("title"),
                "url": issue.get("url"),
                "team_name": team_name(issue.get("team")),
                "team_key": issue.get("team", {}).get("key"),
                "state_name": issue.get("state", {}).get("name", "-"),
                "updatedAt": issue.get("updatedAt"),
                "why": why,
            }
        )
    personal_updated = sorted(
        [issue for issue in updated if is_personal_linear_issue(issue)],
        key=lambda issue: parse_dt(issue.get("updatedAt")) or START,
        reverse=True,
    )
    personal_created = sorted(
        [issue for issue in created if is_personal_linear_issue(issue)],
        key=lambda issue: parse_dt(issue.get("createdAt")) or START,
        reverse=True,
    )
    personal_done_like = [
        issue for issue in personal_updated if issue.get("state", {}).get("type") == "completed"
    ]
    personal_in_review = [
        issue
        for issue in personal_updated
        if issue.get("state", {}).get("name", "").lower() == "in review"
    ]
    personal_state_counts = Counter(
        issue.get("state", {}).get("name", "Unknown") for issue in personal_updated
    )
    personal_team_counts = Counter(
        issue["team"]["key"]
        for issue in personal_updated
        if issue.get("team") and issue["team"].get("key")
    )
    personal_interesting = [
        item
        for item in interesting
        if any(item["identifier"] == issue.get("identifier") for issue in personal_updated)
    ]

    return {
        "issues_sampled": len(issues),
        "issues_updated": len(updated),
        "issues_created": len(created),
        "issues_done_like": len(done_like),
        "issues_blocked": len(blocked),
        "team_names": team_names,
        "teams_updated": top_counter_rows(team_updated, 10),
        "teams_created": top_counter_rows(team_created, 10),
        "states_updated": top_counter_rows(state_updated, 10),
        "interesting": interesting,
        "recent_updated": updated[:12],
        "recent_created": created[:12],
        "recent_done_like": done_like[:12],
        "projects_created": projects_created[:12],
        "projects_updated": projects_updated[:12],
        "personal_assignee": PERSON_LINEAR_ASSIGNEE,
        "personal_issues_updated": len(personal_updated),
        "personal_issues_created": len(personal_created),
        "personal_issues_done_like": len(personal_done_like),
        "personal_issues_in_review": len(personal_in_review),
        "personal_states_updated": top_counter_rows(personal_state_counts, 10),
        "personal_teams_updated": top_counter_rows(personal_team_counts, 10),
        "personal_updated": personal_updated,
        "personal_created": personal_created,
        "personal_done_like": personal_done_like,
        "personal_in_review": personal_in_review,
        "personal_interesting": personal_interesting,
    }


def normalize_datadog_cards(items: object) -> list[dict]:
    if not isinstance(items, list):
        return []

    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        summary = item.get("summary")
        url = item.get("url")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(summary, str) or not summary.strip():
            continue
        card = {
            "title": title.strip(),
            "date": str(item.get("date") or "-"),
            "kind": str(item.get("kind") or "Datadog evidence"),
            "url": url if isinstance(url, str) and url.strip() else "#datadog",
            "summary": summary.strip(),
        }
        cards.append(card)
    return cards


def normalize_datadog_counts(items: object) -> list[tuple[str, int, str | None]]:
    if not isinstance(items, list):
        return []

    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        count = item.get("count")
        if not isinstance(label, str) or not isinstance(count, int):
            continue
        url = item.get("url")
        rows.append((label, count, url if isinstance(url, str) else None))
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows


def datadog_summary() -> dict:
    activity = load_datadog_activity()
    counts = activity.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}

    highlights = normalize_datadog_cards(activity.get("highlights"))
    lowlights = normalize_datadog_cards(activity.get("lowlights"))
    event_groups = normalize_datadog_counts(activity.get("event_groups"))
    methodology = activity.get("methodology")
    source_url = activity.get("source_url")

    return {
        "counts": counts,
        "event_count": int(counts.get("events", 0)),
        "incident_count": int(counts.get("incidents", 0)),
        "monitor_alert_count": int(counts.get("monitor_alerts", 0)),
        "dashboard_count": int(counts.get("dashboards", 0)),
        "touchpoint_count": len(highlights) + len(lowlights),
        "highlights": highlights,
        "lowlights": lowlights,
        "event_groups": event_groups,
        "methodology": (
            methodology
            if isinstance(methodology, str) and methodology.strip()
            else "We pulled Datadog from MCP event, incident, monitor, and dashboard reads."
        ),
        "source_url": source_url if isinstance(source_url, str) else "#datadog",
    }


LINEAR_INTERESTING_NOTES = [
    (
        "EE-981",
        "Adds Windows Server 2025 node-pool support for iQuote, which is platform plumbing that quietly reduces future hosting friction.",
    ),
    (
        "EE-966",
        "Ties directly to the Datadog certification dashboard work: award-row data needed to be trustworthy before the dashboard could be useful.",
    ),
    (
        "EE-986",
        "Moves DBM from surface-level database monitoring toward query and wait-event visibility for MySQL workloads.",
    ),
    (
        "EE-985",
        "Turns three local CTC financial dashboards into one platform-hosted app with a clearer auth and deployment path.",
    ),
    (
        "EE-929",
        "The main Insights staging migration thread, backed by GitHub, Notion planning, and Datadog DBM work.",
    ),
    (
        "EE-969",
        "Keeps the production side of the Insights database move explicit instead of hiding it inside app deployment work.",
    ),
    (
        "DAT-2592",
        "Matches the SQLMesh RFC lowlight: audit and run failures need first-class alerts before the Tobiko migration is safe.",
    ),
    (
        "DAT-2595",
        "Connects SQLMesh run logs to Datadog so data-platform failures have a durable operating surface.",
    ),
    (
        "DAT-2594",
        "Adds freshness monitoring to the SQLMesh migration story, which is the difference between jobs running and users trusting outputs.",
    ),
    (
        "DAT-2593",
        "Keeps the GitHub Actions path honest by alerting when the workflow layer fails before SQLMesh can report anything.",
    ),
    (
        "CUS-1338",
        "Customer Portal DataSync work ties the Insights webhook integration to customer-facing operations.",
    ),
    (
        "CUS-1195",
        "A concrete support blocker around Alta Video lab testing; useful because enablement work is not only platform primitives.",
    ),
    (
        "CP-497",
        "The Customer Portal Datadog-triggered error shows monitoring creating work instead of waiting for a human to notice.",
    ),
    (
        "GAM-1245",
        "Gamma pre-deployment prep paired with Datadog and E2E activity shows the release path getting more observable.",
    ),
    (
        "QAE-146",
        "E2E support for site-priority updates helped keep the iCare and Gamma release work testable.",
    ),
]


def filtered_slack_highlights(slack_highlights: list[dict]) -> list[dict]:
    muted = load_muted_slack_channels()
    return [item for item in slack_highlights if item["channel"] not in muted]


def make_theme_cards(github_data: dict, linear_data: dict, datadog_data: dict) -> list[dict]:
    top_repo_text = ", ".join(repo for repo, _ in github_data["top_pr_repos"][:3])
    top_linear_teams = ", ".join(
        linear_data["team_names"].get(team_key, team_key)
        for team_key, _ in linear_data["teams_updated"][:3]
    )
    datadog_signal = (
        f"{datadog_data['event_count']:,} Datadog events"
        if datadog_data["event_count"]
        else "Datadog incident, monitor, and dashboard reads"
    )
    return [
        {
            "title": "AI and platform tooling are getting governed",
            "body": (
                f"We saw that in {top_repo_text}, in Slack spend-control and agent-tooling discussions, "
                "and in the choice to remove brittle automation when it stopped helping. "
                "This is moving from casual tool use into repo-owned workflows, review loops, and operating policy."
            ),
        },
        {
            "title": "GitHub and Linear are moving together",
            "body": (
                f"Linear showed {linear_data['issues_updated']} sampled issue updates across the week, with the most visible traffic in {top_linear_teams}. "
                "The Engineering Enablement Linear feed made that movement easy to follow in Slack, and the matching GitHub repos show code landing behind it."
            ),
        },
        {
            "title": "Reliability work kept surfacing",
            "body": (
                "We kept running into the same thread across tools: dashboards, SLO work, deploy-duration metrics, "
                f"bot protection, Temporal monitors, support-driven debugging, and {datadog_signal}. "
                "That story showed up in GitHub, Linear, Slack, Notion, and Datadog."
            ),
        },
        {
            "title": "Notion carried real operating context",
            "body": (
                "The useful Notion pages this week carried live work: delivery status, QA coverage, data quality review, architecture direction, "
                "and AI spend guidance. They belonged in the weekly readout right alongside the code and ticket streams."
            ),
        },
    ]


def stat_card(label: str, value_html: str, subtext_html: str) -> str:
    return (
        '<div class="stat-card">'
        f'<div class="stat-label">{esc(label)}</div>'
        f'<div class="stat-value">{value_html}</div>'
        f'<div class="stat-subtext">{subtext_html}</div>'
        "</div>"
    )


def render_counter_table(
    title: str,
    rows: list[tuple[str, int]],
    max_rows: int = 10,
    link_builder=None,
    label_builder=None,
    table_id: str | None = None,
) -> str:
    if not rows:
        return ""
    maximum = max(value for _, value in rows[:max_rows])
    body_rows = []
    for name, value in rows[:max_rows]:
        href = link_builder(name, value) if link_builder else None
        display_name = label_builder(name, value) if label_builder else name
        name_html = link_text(display_name, href) if href else esc(display_name)
        body_rows.append(f"<tr><td>{name_html}</td><td>{bar(value, maximum, href)}</td></tr>")
    wrapper_id = f' id="{esc(table_id)}"' if table_id else ""
    return (
        f'<div class="table-wrap"{wrapper_id}>'
        f"<h4>{esc(title)}</h4>"
        '<table class="metric-table"><thead><tr><th>Name</th><th>Count</th></tr></thead>'
        f"<tbody>{''.join(body_rows)}</tbody></table></div>"
    )


def render_github_pr_table(items: list[dict]) -> str:
    rows = []
    for pr in items:
        repo = repo_name(pr)
        author_login = pr.get("author", {}).get("login", "-")
        rows.append(
            "<tr>"
            f"<td>{esc(fmt_date(pr.get('closedAt')))}</td>"
            f"<td>{link_text(repo, gh_repo_url(repo))}</td>"
            f'<td><a href="{esc(pr.get("url"))}">{esc(pr.get("title"))}</a></td>'
            f"<td>{link_text(author_login, gh_author_search_url(author_login, merged=True))}</td>"
            f"<td>{esc(pr.get('commentsCount', 0))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        "<h4>Selected merged PRs worth opening</h4>"
        '<table class="metric-table"><thead><tr><th>Merged</th><th>Repo</th><th>PR</th><th>Author</th><th>Comments</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_linear_issue_table(title: str, items: list[dict]) -> str:
    rows = []
    for issue in items:
        team_key = issue.get("team", {}).get("key", "-")
        team_display = team_name(issue.get("team"))
        rows.append(
            "<tr>"
            f'<td><a href="{esc(issue.get("url"))}">{esc(issue.get("identifier"))}</a></td>'
            f"<td>{link_text(team_display, linear_team_url(team_key)) if team_key != '-' else esc(team_display)}</td>"
            f"<td>{esc(issue.get('state', {}).get('name', '-'))}</td>"
            f'<td><a href="{esc(issue.get("url"))}">{esc(issue.get("title"))}</a></td>'
            f"<td>{esc(fmt_datetime(issue.get('updatedAt')))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        f"<h4>{esc(title)}</h4>"
        '<table class="metric-table"><thead><tr><th>Issue</th><th>Team</th><th>State</th><th>Title</th><th>Updated</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_projects_table(items: list[dict]) -> str:
    rows = []
    for project in items:
        team_links = ", ".join(
            link_text(team_name(team), linear_team_url(team["key"]))
            for team in project.get("teams", {}).get("nodes", [])
        )
        rows.append(
            "<tr>"
            f"<td>{esc(fmt_date(project.get('createdAt')))}</td>"
            f"<td>{team_links or '-'}</td>"
            f"<td>{esc(project.get('state', '-'))}</td>"
            f"<td>{esc(fmt_pct(project.get('progress', 0)) if project.get('progress') is not None else '-')}</td>"
            f'<td><a href="{esc(project.get("url"))}">{esc(project.get("name"))}</a></td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        "<h4>Recent Linear projects</h4>"
        '<table class="metric-table"><thead><tr><th>Created</th><th>Team</th><th>State</th><th>Progress</th><th>Project</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_highlight_cards(
    items: list[dict],
    link_key: str | None = None,
    enable_mute: bool = False,
) -> str:
    cards = []
    for item in items:
        title = item["title"] if "title" in item else item["channel"]
        meta = item["kind"] if "kind" in item else item["theme"]
        link_open = ""
        link_close = ""
        if link_key and item.get(link_key):
            link_open = f'<a href="{esc(item[link_key])}">'
            link_close = "</a>"
        summary = item.get("summary", "")
        details = item.get("details", [])
        detail_html = ""
        mute_html = ""
        meta_html = ""
        if details:
            detail_html = (
                "<ul>" + "".join(f"<li>{esc(detail)}</li>" for detail in details) + "</ul>"
            )
        if enable_mute and item.get("channel"):
            mute_html = (
                '<button class="mute-button" type="button" '
                f'data-channel="{esc(item["channel"])}" '
                f'aria-label="Mute {esc(item["channel"])}">'
                "Mute channel"
                "</button>"
            )
        if not enable_mute:
            meta_html = f'<div class="highlight-meta">{esc(item.get("date", meta))}</div>'
        cards.append(
            f'<article class="highlight-card" data-channel="{esc(item.get("channel", ""))}">'
            f"{meta_html}"
            '<div class="highlight-head">'
            f"<h4>{link_open}{esc(title)}{link_close}</h4>"
            f"{mute_html}"
            "</div>"
            f'<p class="highlight-summary">{esc(meta if summary == "" else summary)}</p>'
            f"{detail_html}"
            "</article>"
        )
    return '<div class="highlight-grid">' + "".join(cards) + "</div>"


def render_datadog_event_table(items: list[tuple[str, int, str | None]]) -> str:
    if not items:
        return ""
    maximum = max(count for _, count, _ in items)
    rows = []
    for label, count, url in items:
        label_html = link_text(label, url) if url else esc(label)
        rows.append(f"<tr><td>{label_html}</td><td>{bar(count, maximum, url)}</td></tr>")
    return (
        '<div class="table-wrap">'
        "<h4>Top Datadog event groupings</h4>"
        '<table class="metric-table"><thead><tr><th>Signal</th><th>Count</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_datadog_item_table(title: str, items: list[dict]) -> str:
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{esc(item.get('date', '-'))}</td>"
            f"<td>{esc(item.get('kind', '-'))}</td>"
            f'<td><a href="{esc(item.get("url", "#"))}">{esc(item.get("title", "-"))}</a></td>'
            f"<td>{esc(item.get('summary', '-'))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        f"<h4>{esc(title)}</h4>"
        '<table class="metric-table"><thead><tr><th>Date</th><th>Kind</th><th>Evidence</th><th>Why it matters</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_github_item_list(
    title: str,
    items: list[dict],
    date_field: str,
    date_label: str,
) -> str:
    rows = []
    for item in items:
        repo = repo_name(item)
        author_login = item.get("author", {}).get("login", "-")
        rows.append(
            "<tr>"
            f"<td>{esc(fmt_datetime(item.get(date_field)))}</td>"
            f"<td>{link_text(repo, gh_repo_url(repo))}</td>"
            f'<td><a href="{esc(item.get("url"))}">{esc(item.get("title"))}</a></td>'
            f"<td>{link_text(author_login, gh_author_search_url(author_login, merged=(date_field == 'closedAt')))}</td>"
            f"<td>{esc(item.get('state', '-'))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        f"<h4>{esc(title)}</h4>"
        f'<table class="metric-table"><thead><tr><th>{esc(date_label)}</th><th>Repo</th><th>Title</th><th>Author</th><th>State</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_active_repo_list(title: str, items: list[dict]) -> str:
    rows = []
    for repo in items:
        full_name = repo.get("nameWithOwner", "-")
        rows.append(
            "<tr>"
            f"<td>{esc(fmt_datetime(repo.get('pushedAt')))}</td>"
            f"<td>{link_text(full_name, gh_repo_url(full_name))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        f"<h4>{esc(title)}</h4>"
        '<table class="metric-table"><thead><tr><th>Last push</th><th>Repo</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_linear_issue_list(
    title: str,
    items: list[dict],
    date_field: str,
    date_label: str,
) -> str:
    rows = []
    for issue in items:
        team_key = issue.get("team", {}).get("key", "-")
        team_display = team_name(issue.get("team"))
        rows.append(
            "<tr>"
            f"<td>{esc(fmt_datetime(issue.get(date_field)))}</td>"
            f'<td><a href="{esc(issue.get("url"))}">{esc(issue.get("identifier"))}</a></td>'
            f"<td>{link_text(team_display, linear_team_url(team_key)) if team_key != '-' else esc(team_display)}</td>"
            f"<td>{esc(issue.get('state', {}).get('name', '-'))}</td>"
            f'<td><a href="{esc(issue.get("url"))}">{esc(issue.get("title"))}</a></td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        f"<h4>{esc(title)}</h4>"
        f'<table class="metric-table"><thead><tr><th>{esc(date_label)}</th><th>Issue</th><th>Team</th><th>State</th><th>Title</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_linear_interest_cards(items: list[dict]) -> str:
    cards = []
    for item in items:
        issue_link = (
            f'<a href="{esc(item["url"])}">{esc(item["identifier"])} · {esc(item["title"])}</a>'
        )
        team_link = (
            link_text(item["team_name"], linear_team_url(item["team_key"]))
            if item.get("team_key")
            else esc(item["team_name"])
        )
        cards.append(
            '<article class="highlight-card">'
            f'<div class="highlight-meta">{esc(item["state_name"])} · {esc(fmt_datetime(item["updatedAt"]))}</div>'
            f"<h4>{issue_link}</h4>"
            f'<p class="highlight-summary">{team_link}</p>'
            f"<p>{esc(item['why'])}</p>"
            "</article>"
        )
    return '<div class="highlight-grid">' + "".join(cards) + "</div>"


def build_html(summary: dict) -> str:
    github_data = summary["github"]
    linear_data = summary["linear"]
    datadog_data = summary["datadog"]
    slack_highlights = summary["slack_highlights"]
    muted_slack_channels = summary.get("muted_slack_channels", [])
    notion_highlights = summary["notion_highlights"]
    themes = summary["themes"]

    github_top_repo = github_data["top_pr_repos"][0][0] if github_data["top_pr_repos"] else "n/a"
    github_top_repo_count = github_data["top_pr_repos"][0][1] if github_data["top_pr_repos"] else 0
    top_linear_team_key = (
        linear_data["teams_updated"][0][0] if linear_data["teams_updated"] else "n/a"
    )
    top_linear_team = linear_data["team_names"].get(top_linear_team_key, top_linear_team_key)
    top_linear_team_count = (
        linear_data["teams_updated"][0][1] if linear_data["teams_updated"] else 0
    )

    window_label = report_window_label()
    slack_stance = "Tracked channels refreshed from connector snapshots"
    notion_stance = "Tracked pages refreshed from connector snapshots"
    datadog_stance = "Datadog evidence refreshed from MCP reads"
    slack_summary_label = "Tracked channels + connector reads"
    slack_intro = "We built the Slack pass from tracked channels refreshed through connector reads. That gives us current coverage for the channels we care about most, but it's still deliberate sampling rather than a full workspace export."
    notion_intro = "The useful Notion pages this week carried live work. This slice was refreshed from tracked pages through connector fetches, so it reflects current doc state without pretending to be a workspace-wide crawl."
    datadog_intro = "The Datadog pass pulled operational evidence into the same story instead of leaving reliability work as background noise. It is a targeted read of events, incidents, monitors, and dashboards for the reporting window."

    executive_cards = "".join(
        [
            stat_card(
                "GitHub",
                f"{link_text(str(github_data['prs_created']) + ' PRs opened', report_page('github-prs-created.html'))} / {link_text(str(github_data['prs_merged']) + ' merged', report_page('github-prs-merged.html'))}",
                f"{link_text(str(github_data['repos_active_week']) + ' active repos', report_page('github-active-repos.html'))} out of {link_text(str(github_data['repos_total']) + ' total', gh_org_repos_url())}",
            ),
            stat_card(
                "Linear",
                link_text(
                    f"{linear_data['issues_updated']} sampled issue updates",
                    report_page("linear-issues-updated.html"),
                ),
                f"{link_text(str(linear_data['issues_created']) + ' newly created issues', report_page('linear-issues-created.html'))} and {link_text('recent projects', report_page('linear-projects.html'))}",
            ),
            stat_card(
                "Datadog",
                link_text(
                    f"{datadog_data['event_count']:,} events reviewed",
                    report_page("datadog-evidence.html"),
                ),
                (
                    f"{datadog_data['incident_count']} incidents, "
                    f"{datadog_data['monitor_alert_count']} monitor alerts, "
                    f"{datadog_data['dashboard_count']} dashboards"
                ),
            ),
            stat_card(
                "Slack",
                link_text(slack_summary_label, "#slack"),
                (
                    f"{slack_stance}. Signals centered on AI tooling, delivery feeds, data alerts, onboarding, and support work"
                    if not muted_slack_channels
                    else f"{slack_stance}. Signals centered on AI tooling, delivery feeds, data alerts, onboarding, and support work. {len(muted_slack_channels)} muted."
                ),
            ),
            stat_card(
                "Notion",
                link_text(f"{len(notion_highlights)} notable docs/pages", "#notion"),
                f"{notion_stance}. Docs behaved like active operating surfaces, not passive archives",
            ),
        ]
    )
    github_opened_table = render_counter_table(
        "Top repos by PRs opened",
        github_data["top_pr_repos"],
        link_builder=lambda repo, _: gh_pr_search_url(repo=repo),
        table_id="github-pr-opened",
    )
    github_merged_table = render_counter_table(
        "Top repos by PRs merged",
        github_data["top_merged_repos"],
        link_builder=lambda repo, _: gh_pr_search_url(repo=repo, merged=True),
        table_id="github-pr-merged",
    )
    github_authors_table = render_counter_table(
        "Top human authors by PR creation",
        github_data["top_created_authors"],
        8,
        link_builder=lambda login, _: gh_author_search_url(login),
    )
    github_issue_repos_table = render_counter_table(
        "Top issue creation repos",
        github_data["top_issue_created_repos"],
        8,
        link_builder=lambda repo, _: gh_issue_search_url(repo=repo),
    )
    github_pushes_table = render_counter_table(
        "Repos with pushes in the week",
        [(repo["nameWithOwner"], 1) for repo in github_data["recent_pushes"]],
        12,
        link_builder=lambda repo, _: gh_repo_url(repo),
    )
    linear_teams_table = render_counter_table(
        "Top teams by updated issues",
        linear_data["teams_updated"],
        link_builder=lambda team_key, _: linear_team_page(team_key),
        label_builder=lambda team_key, _: linear_data["team_names"].get(team_key, team_key),
        table_id="linear-teams",
    )
    linear_states_table = render_counter_table(
        "Most common states in updated issues",
        linear_data["states_updated"],
        link_builder=lambda state_name, _: linear_state_page(state_name),
        table_id="linear-states",
    )
    linear_interest_html = render_linear_interest_cards(linear_data["interesting"])
    datadog_highlights_html = (
        render_highlight_cards(datadog_data["highlights"], "url")
        if datadog_data["highlights"]
        else '<p class="mute-note">No Datadog highlights were prominent enough to call out.</p>'
    )
    datadog_lowlights_html = (
        render_highlight_cards(datadog_data["lowlights"], "url")
        if datadog_data["lowlights"]
        else '<p class="mute-note">No Datadog lowlights were prominent enough to call out.</p>'
    )
    datadog_event_table = render_datadog_event_table(datadog_data["event_groups"])
    slack_highlights_html = (
        render_highlight_cards(slack_highlights, "url", enable_mute=True)
        if slack_highlights
        else '<p class="mute-note">All tracked Slack channels are muted right now.</p>'
    )

    theme_html = "".join(
        '<article class="theme-card">'
        f"<h3>{esc(theme['title'])}</h3>"
        f"<p>{esc(theme['body'])}</p>"
        "</article>"
        for theme in themes
    )

    slack_methodology = "We pulled the Slack slice from tracked channels refreshed through connector reads. This is deliberate coverage, not a full workspace export."
    notion_methodology = (
        "We pulled the Notion slice from tracked pages refreshed through connector fetches."
    )
    datadog_methodology = datadog_data["methodology"]

    methodology = f"""
<ul class="method-list">
  <li>We pulled GitHub coverage from the Convergint org for {esc(window_label)}, using repo lists plus PR and issue searches.</li>
  <li>We built the Linear slice from the 100 most recently updated issues per team, deduped into one sample of {linear_data["issues_sampled"]} issues, plus recent project records.</li>
  <li>{esc(datadog_methodology)}</li>
  <li>{esc(slack_methodology)}</li>
  <li>{esc(notion_methodology)}</li>
</ul>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(REPORT_TITLE)}</title>
  <style>
    :root {{
      --bg: #f5f7f4;
      --surface: rgba(255, 255, 252, 0.94);
      --surface-strong: #ffffff;
      --ink: #17211f;
      --muted: #5e6a66;
      --accent: #0f766e;
      --accent-2: #b45336;
      --accent-3: #4f6f31;
      --line: #d7ddd6;
      --shadow: 0 24px 60px rgba(23, 33, 31, 0.08);
      --radius: 8px;
      --radius-sm: 8px;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      background:
        linear-gradient(180deg, rgba(237, 245, 241, 0.96) 0%, rgba(249, 250, 248, 1) 42%),
        linear-gradient(90deg, rgba(15, 118, 110, 0.10), rgba(180, 83, 54, 0.08));
    }}

    a {{
      color: var(--accent);
      text-decoration: none;
    }}

    a:hover {{
      text-decoration: underline;
    }}

    .shell {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 28px;
    }}

    .hero {{
      background: linear-gradient(135deg, rgba(255, 255, 252, 0.98), rgba(239, 247, 243, 0.94));
      border: 1px solid rgba(255, 255, 255, 0.7);
      box-shadow: var(--shadow);
      border-radius: 12px;
      padding: 32px;
      position: relative;
      overflow: hidden;
    }}

    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(15, 123, 114, 0.10);
      color: var(--accent);
      font-size: 13px;
      letter-spacing: 0;
      text-transform: uppercase;
    }}

    h1, h2, h3, h4 {{
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      letter-spacing: 0;
      margin: 0;
    }}

    h1 {{
      margin-top: 18px;
      font-size: 3.6rem;
      line-height: 0.95;
      max-width: 11ch;
    }}

    .hero-grid {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 28px;
      margin-top: 22px;
      position: relative;
      z-index: 1;
    }}

    .hero-copy p {{
      max-width: 70ch;
      line-height: 1.65;
      color: var(--muted);
      font-size: 1.02rem;
    }}

    .hero-notes {{
      border-radius: 8px;
      padding: 22px;
      background: rgba(23, 33, 29, 0.03);
      border: 1px solid rgba(23, 33, 29, 0.08);
      align-self: end;
    }}

    .hero-notes dl {{
      margin: 0;
      display: grid;
      gap: 14px;
    }}

    .hero-notes dt {{
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--muted);
    }}

    .hero-notes dd {{
      margin: 4px 0 0 0;
      font-size: 1.05rem;
      font-weight: 600;
    }}

    .sticky-nav {{
      position: sticky;
      top: 0;
      z-index: 10;
      margin: 22px 0 18px;
      padding: 12px;
      border-radius: 8px;
      backdrop-filter: blur(18px);
      background: rgba(247, 250, 247, 0.88);
      border: 1px solid rgba(215, 221, 214, 0.9);
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}

    .sticky-nav a {{
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(23, 33, 29, 0.05);
      color: var(--ink);
      font-size: 0.92rem;
    }}

    section {{
      margin-top: 22px;
      background: transparent;
      border: 0;
      border-top: 1px solid rgba(215, 221, 214, 0.9);
      box-shadow: none;
      border-radius: 0;
      padding: 28px 0;
    }}

    section > p {{
      line-height: 1.68;
      color: var(--muted);
      max-width: 80ch;
    }}

    .section-heading {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 18px;
    }}

    .section-heading .tag {{
      color: var(--accent-2);
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.78rem;
    }}

    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 16px;
    }}

    .stat-card {{
      padding: 18px;
      border-radius: 8px;
      background: var(--surface-strong);
      border: 1px solid var(--line);
    }}

    .stat-card a {{
      color: inherit;
      text-decoration: underline;
      text-decoration-color: rgba(15, 123, 114, 0.35);
      text-underline-offset: 0.12em;
    }}

    .stat-label {{
      color: var(--muted);
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0;
    }}

    .stat-value {{
      margin-top: 10px;
      font-size: 1.65rem;
      line-height: 1.05;
      font-weight: 700;
    }}

    .stat-subtext {{
      margin-top: 10px;
      color: var(--muted);
      line-height: 1.5;
    }}

    .theme-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}

    .theme-card {{
      padding: 20px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255, 253, 248, 1), rgba(247, 241, 231, 0.96));
    }}

    .theme-card h3 {{
      margin-bottom: 10px;
      font-size: 1.25rem;
    }}

    .theme-card p {{
      margin: 0;
      line-height: 1.65;
      color: var(--muted);
    }}

    .split {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 18px;
    }}

    .table-wrap {{
      padding: 18px;
      border-radius: 8px;
      background: var(--surface-strong);
      border: 1px solid var(--line);
      overflow: auto;
    }}

    .table-wrap h4 {{
      margin-bottom: 12px;
      font-size: 1.1rem;
    }}

    .metric-table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 560px;
    }}

    .metric-table th,
    .metric-table td {{
      padding: 11px 10px;
      border-top: 1px solid rgba(215, 208, 194, 0.8);
      vertical-align: top;
      text-align: left;
      font-size: 0.94rem;
    }}

    .metric-table thead th {{
      border-top: none;
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0;
    }}

    .bar-cell {{
      position: relative;
      min-width: 180px;
      height: 28px;
      border-radius: 999px;
      background: rgba(15, 123, 114, 0.08);
      overflow: hidden;
    }}

    .bar-fill {{
      position: absolute;
      inset: 0 auto 0 0;
      background: linear-gradient(90deg, var(--accent), #3d9189);
      border-radius: 999px;
    }}

    .bar-value {{
      position: absolute;
      inset: 0 10px 0 auto;
      display: inline-flex;
      align-items: center;
      font-weight: 700;
      color: var(--ink);
    }}

    .bar-link {{
      display: block;
      color: inherit;
      text-decoration: none;
    }}

    details {{
      margin-top: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 252, 245, 0.8);
      overflow: hidden;
    }}

    summary {{
      cursor: pointer;
      padding: 16px 18px;
      font-weight: 600;
      list-style: none;
    }}

    summary::-webkit-details-marker {{
      display: none;
    }}

    details > div {{
      padding: 0 18px 18px;
    }}

    .highlight-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}

    .highlight-card {{
      padding: 18px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--surface-strong);
    }}

    .highlight-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
    }}

    .highlight-meta {{
      color: var(--accent-2);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0;
      margin-bottom: 10px;
    }}

    .highlight-card h4 {{
      font-size: 1.08rem;
      margin-bottom: 10px;
    }}

    .highlight-summary {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}

    .highlight-card ul {{
      margin: 12px 0 0 18px;
      padding: 0;
      color: var(--muted);
      line-height: 1.6;
    }}

    .highlight-card p {{
      color: var(--muted);
      line-height: 1.6;
    }}

    .mute-button {{
      flex: 0 0 auto;
      border: 1px solid rgba(23, 33, 29, 0.12);
      background: rgba(15, 123, 114, 0.08);
      color: var(--ink);
      border-radius: 8px;
      padding: 8px 12px;
      font: inherit;
      font-size: 0.84rem;
      cursor: pointer;
      transition: background 120ms ease, opacity 120ms ease;
    }}

    .mute-button:hover {{
      background: rgba(15, 123, 114, 0.16);
    }}

    .mute-button:disabled {{
      cursor: wait;
      opacity: 0.65;
    }}

    .mute-note,
    .mute-feedback {{
      color: var(--muted);
      line-height: 1.6;
    }}

    .mute-feedback {{
      margin: 12px 0 16px;
      font-weight: 600;
    }}

    .method-list {{
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
      line-height: 1.68;
    }}

    .footer-note {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.6;
    }}

    @media (max-width: 1100px) {{
      .hero-grid,
      .split,
      .theme-grid,
      .highlight-grid,
      .stats-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    @media (max-width: 760px) {{
      .shell {{
        padding: 16px;
      }}

      .hero {{
        padding: 18px;
      }}

      section {{
        padding: 22px 0;
      }}

      h1 {{
        max-width: none;
        font-size: 2.5rem;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <div class="eyebrow">{esc(window_label)}</div>
      <div class="hero-grid">
        <div class="hero-copy">
          <h1>Convergint weekly activity, stitched across tools.</h1>
          <p>
            We pulled GitHub, Linear, Datadog, Slack, and Notion into one weekly readout because the individual tools only tell part of the story.
            The useful signal this week came from where they lined up: delivery work stayed active, reliability work kept surfacing,
            support loops showed up in the open, and the docs carried real operating context instead of trailing behind the code.
          </p>
          <p>
            GitHub stayed broad but clustered, with <strong>{link_text(str(github_data["prs_created"]), report_page("github-prs-created.html"))}</strong> PRs opened and
            <strong>{link_text(str(github_data["prs_merged"]), report_page("github-prs-merged.html"))}</strong> merged. Linear added
            <strong>{link_text(str(linear_data["issues_updated"]), report_page("linear-issues-updated.html"))}</strong> sampled issue updates, led by
            <strong>{link_text(top_linear_team, linear_team_page(top_linear_team_key))}</strong> with <strong>{link_text(str(top_linear_team_count), linear_team_page(top_linear_team_key))}</strong> updates.
            Datadog put the reliability signal next to that delivery story, while Slack and Notion filled in the why, who, and what's changing underneath the raw counts.
          </p>
        </div>
        <aside class="hero-notes">
          <dl>
            <div>
              <dt>Most active GitHub repo by PR creation</dt>
              <dd>{link_text(github_top_repo, gh_pr_search_url(repo=github_top_repo))} ({link_text(str(github_top_repo_count), gh_pr_search_url(repo=github_top_repo))})</dd>
            </div>
            <div>
              <dt>Datadog stance</dt>
              <dd>{esc(datadog_stance)}</dd>
            </div>
            <div>
              <dt>Slack stance</dt>
              <dd>{esc(slack_stance)}</dd>
            </div>
            <div>
              <dt>Notion stance</dt>
              <dd>{esc(notion_stance)}</dd>
            </div>
            <div>
              <dt>Generated</dt>
              <dd>{esc(generated_label())}</dd>
            </div>
          </dl>
        </aside>
      </div>
    </header>

    <nav class="sticky-nav">
      <a href="#summary">Summary</a>
      <a href="#themes">Cross-system themes</a>
      <a href="#github">GitHub</a>
      <a href="#linear">Linear</a>
      <a href="#datadog">Datadog</a>
      <a href="#slack">Slack</a>
      <a href="#notion">Notion</a>
      <a href="#method">Methodology</a>
    </nav>

    <section id="summary">
      <div class="section-heading">
        <h2>Summary</h2>
        <span class="tag">Executive readout</span>
      </div>
      <div class="stats-grid">{executive_cards}</div>
    </section>

    <section id="themes">
      <div class="section-heading">
        <h2>Cross-system themes</h2>
        <span class="tag">Where the signals line up</span>
      </div>
      <div class="theme-grid">{theme_html}</div>
    </section>

    <section id="github">
      <div class="section-heading">
        <h2>GitHub</h2>
        <span class="tag">Hard activity counts</span>
      </div>
      <p>
        We saw pushes across {link_text(str(github_data["repos_active_week"]) + " repos", report_page("github-active-repos.html"))} this week.
        PR creation concentrated in {link_text(github_top_repo, gh_pr_search_url(repo=github_top_repo))}, with the rest of the activity clustering around delivery, data, and enablement work.
        The issue stream stayed quiet; the work showed up more clearly as PR movement, Linear execution, and cross-tool coordination.
      </p>
      <div class="split">
        {github_opened_table}
        {github_merged_table}
      </div>
      <details open>
        <summary>Open the GitHub drill-down</summary>
        <div>
          <div class="split">
            {github_authors_table}
            {github_issue_repos_table}
          </div>
          <div class="split" style="margin-top:16px;">
            {render_github_pr_table(github_data["interesting_merged"])}
            {github_pushes_table}
          </div>
        </div>
      </details>
    </section>

    <section id="linear">
      <div class="section-heading">
        <h2>Linear</h2>
        <span class="tag">Planning and execution flow</span>
      </div>
      <p>
        We captured {link_text(str(linear_data["issues_updated"]) + " issue updates", report_page("linear-issues-updated.html"))}
        in the Linear sample this week, along with {link_text(str(linear_data["issues_created"]) + " newly created issues", report_page("linear-issues-created.html"))}.
        {link_text(top_linear_team, linear_team_page(top_linear_team_key))} carried the most visible update volume, but the better read is in the issues worth opening:
        platform observability, app hardening, data operating discipline, and customer-facing rollout work all showed up clearly.
      </p>
      {linear_interest_html}
      <div class="split">
        {linear_teams_table}
        {linear_states_table}
      </div>
      <details open>
        <summary>Open the Linear drill-down</summary>
        <div>
          <div class="split">
            {render_linear_issue_table("Most recently created issues", linear_data["recent_created"])}
            {render_linear_issue_table("Completed-state issues updated this week", linear_data["recent_done_like"])}
          </div>
          <div style="margin-top:16px;">
            {render_projects_table(linear_data["projects_created"] or linear_data["projects_updated"])}
          </div>
        </div>
      </details>
    </section>

    <section id="datadog">
      <div class="section-heading">
        <h2>Datadog</h2>
        <span class="tag">Operational signal</span>
      </div>
      <p>
        {esc(datadog_intro)}
      </p>
      <div class="split">
        {datadog_highlights_html}
        {datadog_event_table}
      </div>
      <details>
        <summary>Open the Datadog lowlights</summary>
        <div>
          {datadog_lowlights_html}
        </div>
      </details>
    </section>

    <section id="slack">
      <div class="section-heading">
        <h2>Slack</h2>
        <span class="tag">Channel and search signals</span>
      </div>
      <p>
        {esc(slack_intro)}
      </p>
      <p class="mute-note">
        Click <strong>Mute channel</strong> if you want to stop carrying a channel in future report runs.
        <span data-muted-count>{len(muted_slack_channels)}</span> channel(s) are currently muted.
      </p>
      <div id="mute-feedback" class="mute-feedback" hidden></div>
      {slack_highlights_html}
    </section>

    <section id="notion">
      <div class="section-heading">
        <h2>Notion</h2>
        <span class="tag">Docs as workflow</span>
      </div>
      <p>
        {esc(notion_intro)}
      </p>
      {render_highlight_cards(notion_highlights, "url")}
    </section>

    <section id="method">
      <div class="section-heading">
        <h2>Methodology and caveats</h2>
        <span class="tag">How to read this page</span>
      </div>
      {methodology}
      <p class="footer-note">
        GitHub, Linear, and Datadog carry most of the quantitative weight here.
        Slack and Notion tell us what people were coordinating around, which docs were shaping behavior, and where the work was getting more structured.
      </p>
    </section>
  </div>
  <script>
    const muteServerOrigin = {json.dumps(REPORT_SERVER_ORIGIN)};
    const muteButtons = document.querySelectorAll(".mute-button");
    const muteFeedback = document.getElementById("mute-feedback");
    const mutedCount = document.querySelector("[data-muted-count]");

    /**
     * Displays the local mute operation result near the Slack section.
     *
     * @param message User-facing status text for the report reader.
     * @param isError Whether the feedback should use the error treatment.
     * @returns Nothing; the page is updated in place.
     */
    function showMuteFeedback(message, isError = false) {{
      if (!muteFeedback) return;
      muteFeedback.hidden = false;
      muteFeedback.textContent = message;
      muteFeedback.style.color = isError ? "#be6435" : "#0f7b72";
    }}

    /**
     * Persists a Slack channel mute through the local report server.
     *
     * @param button The mute button whose channel data attribute should be hidden.
     * @returns A promise that resolves after the UI reflects the mute request.
     */
    async function muteSlackChannel(button) {{
      const channel = button.dataset.channel;
      if (!channel) return;
      const confirmed = window.confirm(`Mute ${{channel}} and hide it from future report runs?`);
      if (!confirmed) return;

      button.disabled = true;
      button.textContent = "Muting...";

      try {{
        const response = await fetch(`${{muteServerOrigin}}/mute`, {{
          method: "POST",
          headers: {{
            "Content-Type": "application/json"
          }},
          body: JSON.stringify({{ channel }})
        }});

        if (!response.ok) {{
          throw new Error(`Mute failed with status ${{response.status}}`);
        }}

        const payload = await response.json();
        const card = button.closest(".highlight-card");
        if (card) {{
          card.remove();
        }}
        if (mutedCount) {{
          mutedCount.textContent = String(payload.muted_count);
        }}

        showMuteFeedback(
          `${{channel}} muted. Reload the page to see the regenerated report. Total muted: ${{payload.muted_count}}.`
        );
      }} catch (error) {{
        button.disabled = false;
        button.textContent = "Mute channel";
        showMuteFeedback(
          "Mute failed. Make sure the local report server is running on " + muteServerOrigin + ".",
          true
        );
      }}
    }}

    muteButtons.forEach((button) => {{
      button.addEventListener("click", () => muteSlackChannel(button));
    }});
  </script>
</body>
</html>
"""


def evidence_link(label: str, href: str) -> str:
    return f'<a href="{esc(href)}">{esc(label)}</a>'


def render_evidence_links(items: list[tuple[str, str]]) -> str:
    if not items:
        return ""
    return (
        '<div class="evidence-links">'
        + "".join(evidence_link(label, href) for label, href in items)
        + "</div>"
    )


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", crc32(kind + data) & 0xFFFFFFFF)
    )


def blend_pixel(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    if x < 0 or x >= width or y < 0 or y >= height:
        return
    alpha = max(0.0, min(1.0, alpha))
    index = (y * width + x) * 3
    for offset, channel in enumerate(color):
        pixels[index + offset] = round(pixels[index + offset] * (1 - alpha) + channel * alpha)


def draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    alpha: float,
    thickness: int = 1,
) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    radius = max(0, thickness // 2)

    while True:
        for py in range(y0 - radius, y0 + radius + 1):
            for px in range(x0 - radius, x0 + radius + 1):
                blend_pixel(pixels, width, height, px, py, color, alpha)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def draw_circle(
    pixels: bytearray,
    width: int,
    height: int,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    cx, cy = center
    radius_sq = radius * radius
    inner_sq = max(0, radius - 2) ** 2
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            dist_sq = (x - cx) ** 2 + (y - cy) ** 2
            if dist_sq <= radius_sq:
                local_alpha = alpha if dist_sq >= inner_sq else alpha * 0.55
                blend_pixel(pixels, width, height, x, y, color, local_alpha)


def write_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    rows = []
    stride = width * 3
    for y in range(height):
        rows.append(b"\x00" + bytes(pixels[y * stride : (y + 1) * stride]))
    raw = b"".join(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + png_chunk(b"IEND", b"")
    )


def generate_hero_image() -> None:
    width = 1600
    height = 900
    pixels = bytearray(width * height * 3)
    for y in range(height):
        y_ratio = y / (height - 1)
        for x in range(width):
            x_ratio = x / (width - 1)
            glow = max(0.0, 1 - ((x_ratio - 0.78) ** 2 + (y_ratio - 0.42) ** 2) / 0.16)
            warm = max(0.0, 1 - ((x_ratio - 0.95) ** 2 + (y_ratio - 0.16) ** 2) / 0.12)
            base = (
                round(12 + 12 * x_ratio + 10 * glow),
                round(26 + 38 * x_ratio + 34 * glow + 16 * warm),
                round(28 + 32 * x_ratio + 30 * glow + 6 * warm),
            )
            index = (y * width + x) * 3
            pixels[index : index + 3] = bytes(base)

    grid_color = (103, 142, 135)
    for x in range(520, width, 92):
        draw_line(pixels, width, height, (x, 115), (x - 170, 780), grid_color, 0.08)
    for y in range(130, 790, 72):
        draw_line(pixels, width, height, (460, y), (1490, y + 70), grid_color, 0.08)

    nodes = [
        (785, 210),
        (965, 178),
        (1160, 236),
        (1360, 198),
        (720, 382),
        (920, 430),
        (1125, 392),
        (1320, 462),
        (790, 626),
        (1045, 656),
        (1275, 612),
        (1450, 700),
    ]
    links = [
        (0, 1),
        (1, 2),
        (2, 3),
        (0, 4),
        (4, 5),
        (5, 6),
        (6, 7),
        (4, 8),
        (8, 9),
        (9, 10),
        (10, 11),
        (2, 6),
        (6, 10),
        (7, 11),
    ]
    for first, second in links:
        draw_line(pixels, width, height, nodes[first], nodes[second], (72, 180, 168), 0.42, 3)
        draw_line(pixels, width, height, nodes[first], nodes[second], (225, 245, 238), 0.16, 1)
    for node in nodes:
        draw_circle(pixels, width, height, node, 18, (21, 118, 110), 0.65)
        draw_circle(pixels, width, height, node, 7, (241, 249, 244), 0.92)

    for x, y, w, h, color in [
        (1010, 84, 310, 58, (226, 236, 230)),
        (1190, 520, 260, 46, (180, 83, 54)),
        (660, 704, 270, 52, (79, 111, 49)),
        (1240, 300, 230, 40, (226, 236, 230)),
    ]:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                border = xx in {x, x + w - 1} or yy in {y, y + h - 1}
                blend_pixel(pixels, width, height, xx, yy, color, 0.22 if border else 0.08)

    for y in range(height):
        vignette = (y / height) * 0.18
        for x in range(0, 620):
            alpha = 0.34 + (1 - x / 620) * 0.38 + vignette
            blend_pixel(pixels, width, height, x, y, (5, 14, 15), min(alpha, 0.78))

    write_png(HERO_IMAGE_PATH, width, height, pixels)


def render_workstream_bodies() -> str:
    workstreams = [
        {
            "kicker": "CTC financials",
            "title": "The dashboard work became a demo-ready platform application path.",
            "body": (
                "Hari's CTC financial dashboard started as a useful internal tool. Chad turned the week "
                "into repo access, production-readiness notes, CI, agent tooling, and a consolidation path "
                "for the dashboard app. Wendy and Chad kept the SSO and platform-hosting path explicit, "
                "and Chad held the database-table change until the team understood the data behavior. "
                "It is now a visible example of how an internal dashboard can move onto the platform."
            ),
            "proof": "10 Chad-authored PRs in convergint/ctc-financials, with EE-980, EE-983, and EE-985 carrying the Linear trail.",
            "demo_note": "Demo angle: repo-backed app path, CI, agent image, production-readiness notes, and dashboard consolidation.",
            "evidence": [
                ("Planning notes", "https://app.notion.com/p/3815f445bd31806f8634d7d6abdc70b4"),
                ("PR #1", "https://github.com/convergint/ctc-financials/pull/1"),
                ("PR #2", "https://github.com/convergint/ctc-financials/pull/2"),
                ("PR #8", "https://github.com/convergint/ctc-financials/pull/8"),
                ("PR #9", "https://github.com/convergint/ctc-financials/pull/9"),
                ("PR #10", "https://github.com/convergint/ctc-financials/pull/10"),
                (
                    "Slack thread",
                    "https://convergint.enterprise.slack.com/archives/C0AQHKE74MT/p1781818845350249?thread_ts=1781818845.350249&cid=C0AQHKE74MT",
                ),
            ],
        },
        {
            "kicker": "Windows platform support",
            "title": "Windows Server 2025 support made the iQuote platform path concrete.",
            "body": (
                "Chad added Windows Server 2025 node-pool support for iQuote container hosting in platform "
                "AKS. The work keeps the capacity managed through IaC, uses explicit scheduling controls "
                "for the w2025 pool, preserves existing Linux workload behavior, and documents the "
                "host/image compatibility app teams need to understand."
            ),
            "proof": "EE-981 is Done and ee-monorepo PR #1603 merged after adding the Windows Server 2025 AKS node pool.",
            "demo_note": "Demo angle: a Windows workload can target platform capacity through explicit AKS scheduling instead of a one-off hosting path.",
            "evidence": [
                (
                    "EE-981",
                    "https://linear.app/convergint/issue/EE-981/add-windows-server-2025-node-pool-support-for-iquote-container-hosting",
                ),
                ("PR #1603", "https://github.com/convergint/ee-monorepo/pull/1603"),
            ],
        },
        {
            "kicker": "IT and Infrastructure support",
            "title": "Saviynt audit ingest and iCare access turned IT support into working platform code.",
            "body": (
                "Chad's open it-monorepo PR #67 built the MVP Saviynt audit-log ingest path for the IT "
                "and Infrastructure team: a Go Temporal worker reads the Saviynt runtime-control API, stores "
                "a compact cursor in Azure Table Storage, and submits confirmed pages as OTLP logs to Datadog. "
                "The same workstream includes EE-961 and the iCare private-link DNS follow-through, so the "
                "report shows both the security ingest app and the access plumbing."
            ),
            "proof": "EE-962 is In Review with it-monorepo PR #67 open; EE-961 is Done, PR #68 merged, and PR #69 kept the iCare domain follow-up visible.",
            "demo_note": "Demo angle: Saviynt audit rows flow through a Temporal collector into Datadog with cursoring, infrastructure, and CI/CD attached.",
            "evidence": [
                (
                    "EE-962",
                    "https://linear.app/convergint/issue/EE-962/add-saviynt-audit-log-collector",
                ),
                ("it-monorepo #67", "https://github.com/convergint/it-monorepo/pull/67"),
                (
                    "EE-961",
                    "https://linear.app/convergint/issue/EE-961/onboard-it-and-infrastructure-to-platform",
                ),
                ("it-monorepo #68", "https://github.com/convergint/it-monorepo/pull/68"),
                ("it-monorepo #69", "https://github.com/convergint/it-monorepo/pull/69"),
                (
                    "Infrastructure thread",
                    "https://convergint.enterprise.slack.com/archives/C07GXTS5YP8/p1781813650447989?thread_ts=1781813349.829749&cid=C07GXTS5YP8",
                ),
            ],
        },
        {
            "kicker": "Platform runtime and agent tooling",
            "title": "The runtime and tooling work kept delivery from becoming bespoke.",
            "body": (
                "Dependency pinning, Cursor Cloud fixes, the CTC agent image, and the spend-control discussion "
                "all sit in the same bucket: reduce surprises before teams depend on the platform. Chad treated "
                "agent tooling like production developer experience, including removing a brittle 1Password skill "
                "when it stopped helping."
            ),
            "proof": "EE-976, PR #1596, and the CTC Cursor image PR formed the concrete trail behind the runtime cleanup.",
            "evidence": [
                (
                    "EE-976",
                    "https://linear.app/convergint/issue/EE-976/chore-pin-dependency-versions",
                ),
                ("PR #1596", "https://github.com/convergint/ee-monorepo/pull/1596"),
                ("CTC PR #8", "https://github.com/convergint/ctc-financials/pull/8"),
                (
                    "Spend controls",
                    "https://convergint.enterprise.slack.com/archives/C08PAQARM8E/p1781812786634649",
                ),
                (
                    "Skill removal",
                    "https://convergint.enterprise.slack.com/archives/C08PAQARM8E/p1781814755410889",
                ),
            ],
        },
        {
            "kicker": "Observability and data reliability",
            "title": "The Datadog and SQLMesh work kept reliability tied to evidence.",
            "body": (
                "Chad fixed Datadog award-row reads for the certification dashboard, helped narrow an "
                "Insights Service Catalog 403, and kept SQLMesh alerting tied to the self-hosting plan. "
                "This is the connective tissue between dashboards, DBM, Slack alerts, and model freshness: "
                "the team can only operate what it can trust and explain."
            ),
            "proof": "EE-966 closed, the certification dashboard had a cleaner data path, and the SQLMesh RFC carried Datadog follow-up into the plan.",
            "evidence": [
                (
                    "EE-966",
                    "https://linear.app/convergint/issue/EE-966/fix-datadog-award-row-reads",
                ),
                ("PR #1578", "https://github.com/convergint/ee-monorepo/pull/1578"),
                ("Cert dashboard", "https://us3.datadoghq.com/dashboard/vtg-s2b-mv2"),
                (
                    "Datadog thread",
                    "https://convergint.enterprise.slack.com/archives/C08MGCF1FHN/p1781816378224209?thread_ts=1781816378.224209&cid=C08MGCF1FHN",
                ),
                ("SQLMesh RFC", "https://app.notion.com/p/3735f445bd31818591c4c181cdfa90a9"),
                (
                    "Data alert",
                    "https://convergint.enterprise.slack.com/archives/C08BFTMLYM9/p1781619942362409",
                ),
            ],
        },
    ]

    articles = []
    for index, workstream in enumerate(workstreams, start=1):
        demo_note = workstream.get("demo_note")
        article_class = "body-card demo-card" if demo_note else "body-card"
        demo_ribbon = '<div class="demo-ribbon">Demo-worthy</div>' if demo_note else ""
        demo_line = f'<p class="demo-line">{esc(demo_note)}</p>' if demo_note else ""
        articles.append(
            f'<article class="{article_class}">'
            f"{demo_ribbon}"
            f'<div class="body-index">{index}</div>'
            '<div class="body-content">'
            f'<div class="work-kicker">{esc(workstream["kicker"])}</div>'
            f"<h3>{esc(workstream['title'])}</h3>"
            f"<p>{esc(workstream['body'])}</p>"
            f"{demo_line}"
            f'<p class="proof-line">{esc(workstream["proof"])}</p>'
            f"{render_evidence_links(workstream['evidence'])}"
            "</div>"
            "</article>"
        )
    return '<div class="body-grid">' + "".join(articles) + "</div>"


def render_evidence_index(summary: dict) -> str:
    github_data = summary["github"]
    linear_data = summary["linear"]
    return (
        '<div class="split evidence-index">'
        + render_personal_pr_table(
            "Chad-authored PRs opened",
            github_data["personal_created_items"],
            "createdAt",
        )
        + render_personal_linear_table(
            "Chad-assigned Linear issues updated",
            linear_data["personal_updated"],
        )
        + "</div>"
    )


def render_personal_workstreams() -> str:
    workstreams = [
        {
            "kicker": "Internal tools",
            "title": "CTC financials moved from a local dashboard into a platform path",
            "body": (
                "Chad got the repo, access, production-readiness notes, tooling, CI, Cursor image, "
                "and consolidation work moving in one week. The important bit is the sequence: make the "
                "tool real enough for the platform to own, then keep the data-table questions visible "
                "while the app comes together."
            ),
            "evidence": [
                ("CTC planning notes", "https://app.notion.com/p/3815f445bd31806f8634d7d6abdc70b4"),
                ("PR #1 readiness", "https://github.com/convergint/ctc-financials/pull/1"),
                ("PR #8 Cursor image", "https://github.com/convergint/ctc-financials/pull/8"),
                ("PR #9 app consolidation", "https://github.com/convergint/ctc-financials/pull/9"),
                (
                    "Slack thread",
                    "https://convergint.enterprise.slack.com/archives/C0AQHKE74MT/p1781818845350249?thread_ts=1781818845.350249&cid=C0AQHKE74MT",
                ),
            ],
        },
        {
            "kicker": "Platform enablement",
            "title": "Access, hosting, and onboarding chores turned into real throughput",
            "body": (
                "The week included Windows Server 2025 node-pool support for iQuote, GitHub access for "
                "CTC financials and internal tools, production-readiness docs, and IT/Infrastructure "
                "onboarding. None of that reads like a launch post, but it clears the path for other "
                "teams to ship without waiting on one-off platform help."
            ),
            "evidence": [
                (
                    "EE-981",
                    "https://linear.app/convergint/issue/EE-981/add-windows-server-2025-node-pool-support-for-iquote-container-hosting",
                ),
                ("PR #1603", "https://github.com/convergint/ee-monorepo/pull/1603"),
                (
                    "EE-961",
                    "https://linear.app/convergint/issue/EE-961/onboard-it-and-infrastructure-to-platform",
                ),
                ("PR #1575", "https://github.com/convergint/ee-monorepo/pull/1575"),
                (
                    "EE Linear feed",
                    "https://convergint.enterprise.slack.com/archives/C08LEH1L08P/p1781822325307929",
                ),
            ],
        },
        {
            "kicker": "Datadog",
            "title": "Datadog work stayed close to the people depending on it",
            "body": (
                "Chad fixed award-row reads for the certification dashboard, helped debug an Insights "
                "Service Catalog 403, and kept Datadog evidence tied to the Insights migration and CSP "
                "work. The thread across those items is practical observability: dashboards and alerts "
                "need trustworthy data before anyone can use them to make decisions."
            ),
            "evidence": [
                (
                    "EE-966",
                    "https://linear.app/convergint/issue/EE-966/fix-datadog-award-row-reads",
                ),
                ("PR #1578", "https://github.com/convergint/ee-monorepo/pull/1578"),
                ("Cert dashboard", "https://us3.datadoghq.com/dashboard/vtg-s2b-mv2"),
                (
                    "Datadog debug thread",
                    "https://convergint.enterprise.slack.com/archives/C08MGCF1FHN/p1781816378224209?thread_ts=1781816378.224209&cid=C08MGCF1FHN",
                ),
            ],
        },
        {
            "kicker": "AI and agents",
            "title": "Agent tooling got better defaults and fewer sharp edges",
            "body": (
                "The Cursor Cloud fixes, CTC agent image, spend-control discussion, and removal of a "
                "brittle 1Password skill all point in the same direction. Chad kept the AI work useful "
                "by treating the tools like production-facing developer experience, with cost controls "
                "and failure modes on the table."
            ),
            "evidence": [
                ("PR #1596", "https://github.com/convergint/ee-monorepo/pull/1596"),
                ("PR #8", "https://github.com/convergint/ctc-financials/pull/8"),
                (
                    "Spend controls",
                    "https://convergint.enterprise.slack.com/archives/C08PAQARM8E/p1781812786634649",
                ),
                (
                    "Skill removal",
                    "https://convergint.enterprise.slack.com/archives/C08PAQARM8E/p1781814755410889",
                ),
            ],
        },
        {
            "kicker": "Advisory work",
            "title": "A lot of the week was making other teams less stuck",
            "body": (
                "Chad helped with Tailscale onboarding, nudged the Insights review flow toward review "
                "requests instead of approval theater, and kept SQLMesh observability connected to real "
                "failure alerts. This is the part of senior platform work that rarely gets a clean ticket "
                "title but shows up everywhere in the evidence."
            ),
            "evidence": [
                (
                    "Infrastructure thread",
                    "https://convergint.enterprise.slack.com/archives/C07GXTS5YP8/p1781813650447989?thread_ts=1781813349.829749&cid=C07GXTS5YP8",
                ),
                (
                    "Insights review thread",
                    "https://convergint.enterprise.slack.com/archives/C07GQS4J4D8/p1781810184442699?thread_ts=1781809027.744309&cid=C07GQS4J4D8",
                ),
                ("Insights planning", "https://app.notion.com/p/3765f445bd31806da273f0e033bc528d"),
                ("SQLMesh RFC", "https://app.notion.com/p/3735f445bd31818591c4c181cdfa90a9"),
            ],
        },
    ]

    cards = []
    for workstream in workstreams:
        cards.append(
            '<article class="work-card">'
            f'<div class="work-kicker">{esc(workstream["kicker"])}</div>'
            f"<h3>{esc(workstream['title'])}</h3>"
            f"<p>{esc(workstream['body'])}</p>"
            f"{render_evidence_links(workstream['evidence'])}"
            "</article>"
        )
    return '<div class="work-grid">' + "".join(cards) + "</div>"


def render_personal_lowlights() -> str:
    lowlights = [
        (
            "CTC financials still had data-table uncertainty.",
            "The consolidation work moved, but Chad held a database change until the team understood "
            "the table behavior. That restraint belongs in the report because it protected the app from "
            "a fast but brittle decision.",
            "https://convergint.enterprise.slack.com/archives/C0AQHKE74MT/p1781818845350249?thread_ts=1781818845.350249&cid=C0AQHKE74MT",
        ),
        (
            "SQLMesh and Tobiko failures kept showing up in alerts.",
            "The failures made the migration risks concrete. The follow-up is already in the SQLMesh RFC: "
            "Slack alerts, Datadog logs, freshness metrics, and GitHub Actions failure coverage.",
            "https://convergint.enterprise.slack.com/archives/C08BFTMLYM9/p1781619942362409",
        ),
    ]

    cards = []
    for title, body, href in lowlights:
        cards.append(
            '<article class="lowlight-card">'
            f"<h4>{link_text(title, href)}</h4>"
            f"<p>{esc(body)}</p>"
            "</article>"
        )
    return '<div class="lowlight-grid">' + "".join(cards) + "</div>"


def render_personal_pr_table(title: str, items: list[dict], date_field: str) -> str:
    rows = []
    for pr in items:
        repo = repo_name(pr)
        rows.append(
            "<tr>"
            f"<td>{esc(fmt_datetime(pr.get(date_field)))}</td>"
            f"<td>{link_text(repo, gh_repo_url(repo))}</td>"
            f'<td><a href="{esc(pr.get("url"))}">{esc(pr.get("title"))}</a></td>'
            f"<td>{esc(pr.get('state', '-'))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        f"<h4>{esc(title)}</h4>"
        '<table class="metric-table"><thead><tr><th>Date</th><th>Repo</th><th>Pull request</th><th>State</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_personal_linear_table(title: str, items: list[dict]) -> str:
    rows = []
    for issue in items:
        rows.append(
            "<tr>"
            f"<td>{esc(fmt_datetime(issue.get('updatedAt')))}</td>"
            f'<td><a href="{esc(issue.get("url"))}">{esc(issue.get("identifier"))}</a></td>'
            f"<td>{esc(issue.get('state', {}).get('name', '-'))}</td>"
            f'<td><a href="{esc(issue.get("url"))}">{esc(issue.get("title"))}</a></td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap">'
        f"<h4>{esc(title)}</h4>"
        '<table class="metric-table"><thead><tr><th>Updated</th><th>Issue</th><th>State</th><th>Title</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def build_personal_html(summary: dict) -> str:
    github_data = summary["github"]
    linear_data = summary["linear"]
    datadog_data = summary["datadog"]
    slack_highlights = summary["slack_highlights"]
    notion_highlights = summary["notion_highlights"]
    window_label = report_window_label()

    primary_repo = (
        github_data["personal_top_pr_repos"][0][0]
        if github_data["personal_top_pr_repos"]
        else "n/a"
    )
    primary_repo_count = (
        github_data["personal_top_pr_repos"][0][1] if github_data["personal_top_pr_repos"] else 0
    )
    completed_label = (
        f"{linear_data['personal_issues_done_like']} done, "
        f"{linear_data['personal_issues_in_review']} in review"
    )
    datadog_touchpoints = datadog_data["touchpoint_count"]

    executive_cards = "".join(
        [
            stat_card(
                "GitHub",
                link_text(
                    f"{github_data['personal_prs_created']} PRs opened",
                    report_page("personal-github-prs-created.html"),
                ),
                f"{link_text(str(github_data['personal_prs_merged']) + ' merged', report_page('personal-github-prs-merged.html'))}; {github_data['personal_prs_open']} still open",
            ),
            stat_card(
                "Linear",
                link_text(
                    f"{linear_data['personal_issues_updated']} assigned issues moved",
                    report_page("personal-linear-issues.html"),
                ),
                esc(completed_label),
            ),
            stat_card(
                "Datadog",
                link_text(
                    f"{datadog_touchpoints} linked touchpoints",
                    report_page("personal-datadog-evidence.html"),
                ),
                "Award rows, dashboards, DBM, CSP, and debugging evidence",
            ),
            stat_card(
                "Slack",
                link_text(f"{len(slack_highlights)} evidence threads", "#slack"),
                "Support, review guidance, AI tooling, data alerts, and platform coordination",
            ),
            stat_card(
                "Notion",
                link_text(f"{len(notion_highlights)} source docs", "#notion"),
                "Planning notes, RFCs, migration rules, and handoff context",
            ),
        ]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(REPORT_TITLE)}</title>
  <style>
    :root {{
      --bg: #f6f8f7;
      --panel: #ffffff;
      --ink: #14201f;
      --muted: #5b6866;
      --line: #d9e0dd;
      --teal: #0f766e;
      --blue: #1d4f8f;
      --rust: #b45336;
      --green: #4f6f31;
      --soft-teal: rgba(15, 118, 110, 0.08);
      --soft-blue: rgba(29, 79, 143, 0.08);
      --soft-rust: rgba(180, 83, 54, 0.08);
      --shadow: 0 18px 48px rgba(20, 32, 31, 0.08);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      background:
        linear-gradient(180deg, rgba(244, 250, 248, 0.96), rgba(249, 250, 248, 1)),
        linear-gradient(90deg, var(--soft-teal), var(--soft-rust));
    }}

    a {{
      color: var(--teal);
      text-decoration: underline;
      text-decoration-color: rgba(15, 118, 110, 0.35);
      text-underline-offset: 0.14em;
    }}

    .shell {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 28px;
    }}

    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 0.95fr) minmax(420px, 1.05fr);
      gap: 28px;
      align-items: end;
      padding: 30px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(239, 247, 244, 0.94)),
        linear-gradient(90deg, var(--soft-blue), transparent);
      box-shadow: var(--shadow);
    }}

    .eyebrow,
    .kicker,
    .work-kicker,
    .section-heading .tag {{
      color: var(--rust);
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.78rem;
      font-weight: 700;
    }}

    h1, h2, h3, h4 {{
      margin: 0;
      letter-spacing: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
    }}

    h1 {{
      margin-top: 14px;
      font-size: 3.45rem;
      line-height: 0.98;
      max-width: 11ch;
    }}

    .lede {{
      margin-top: 18px;
      max-width: 70ch;
      color: var(--muted);
      line-height: 1.65;
      font-size: 1.02rem;
    }}

    .impact-panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.72);
      padding: 20px;
    }}

    .impact-panel h2 {{
      font-size: 1.35rem;
      margin-bottom: 12px;
    }}

    .impact-panel p {{
      color: var(--muted);
      line-height: 1.6;
      margin: 0 0 14px;
    }}

    .impact-list {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}

    .impact-list li {{
      display: grid;
      grid-template-columns: 110px minmax(0, 1fr);
      gap: 14px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      line-height: 1.45;
    }}

    .impact-list strong {{
      color: var(--ink);
    }}

    .sticky-nav {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 18px 0 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(246, 248, 247, 0.9);
      backdrop-filter: blur(16px);
    }}

    .sticky-nav a {{
      text-decoration: none;
      color: var(--ink);
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(20, 32, 31, 0.05);
    }}

    section {{
      padding: 28px 0;
      border-top: 1px solid var(--line);
    }}

    .section-heading {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 18px;
    }}

    section > p {{
      max-width: 82ch;
      color: var(--muted);
      line-height: 1.68;
    }}

    .stats-grid,
    .work-grid,
    .lowlight-grid,
    .highlight-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(245px, 1fr));
      gap: 16px;
    }}

    .stat-card,
    .work-card,
    .lowlight-card,
    .highlight-card,
    .table-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 10px 28px rgba(20, 32, 31, 0.05);
    }}

    .stat-card {{
      padding: 18px;
    }}

    .stat-label {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.8rem;
    }}

    .stat-value {{
      margin-top: 10px;
      font-size: 1.55rem;
      line-height: 1.08;
      font-weight: 800;
    }}

    .stat-subtext {{
      margin-top: 10px;
      color: var(--muted);
      line-height: 1.5;
    }}

    .work-card,
    .lowlight-card,
    .highlight-card {{
      padding: 18px;
    }}

    .work-card {{
      min-height: 310px;
      display: flex;
      flex-direction: column;
    }}

    .work-card h3 {{
      margin-top: 8px;
      font-size: 1.28rem;
      line-height: 1.18;
    }}

    .work-card p,
    .lowlight-card p,
    .highlight-card p,
    .highlight-card ul {{
      color: var(--muted);
      line-height: 1.62;
    }}

    .work-card p {{
      flex: 1 1 auto;
    }}

    .evidence-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      font-size: 0.92rem;
    }}

    .split {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 16px;
    }}

    .table-wrap {{
      padding: 18px;
      overflow: auto;
    }}

    .table-wrap h4 {{
      margin-bottom: 12px;
      font-size: 1.08rem;
    }}

    .metric-table {{
      width: 100%;
      min-width: 660px;
      border-collapse: collapse;
    }}

    .metric-table th,
    .metric-table td {{
      padding: 11px 10px;
      text-align: left;
      vertical-align: top;
      border-top: 1px solid var(--line);
      font-size: 0.94rem;
    }}

    .metric-table thead th {{
      border-top: none;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.78rem;
    }}

    .highlight-card h4,
    .lowlight-card h4 {{
      font-size: 1.05rem;
      margin-bottom: 10px;
    }}

    .highlight-meta {{
      color: var(--rust);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0;
      margin-bottom: 10px;
    }}

    .highlight-card ul {{
      padding-left: 18px;
      margin: 12px 0 0;
    }}

    .method-list {{
      color: var(--muted);
      line-height: 1.68;
      margin: 0;
      padding-left: 20px;
    }}

    @media (max-width: 980px) {{
      .hero,
      .split {{
        grid-template-columns: 1fr;
      }}

      .hero {{
        padding: 22px;
      }}
    }}

    @media (max-width: 640px) {{
      .shell {{
        padding: 16px;
      }}

      h1 {{
        max-width: none;
        font-size: 2.45rem;
      }}

      .impact-list li {{
        grid-template-columns: 1fr;
        gap: 4px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <div>
        <div class="eyebrow">{esc(window_label)}</div>
        <h1>Chad's week in platform work.</h1>
        <p class="lede">
          This report is scoped to Chad's direct activity and the threads where he shaped the outcome.
          The week reads like senior platform work usually reads: some code, some access, some Datadog,
          some careful review pressure, and a lot of making other people's work less stuck.
        </p>
        <p class="lede">
          The center of gravity was CTC financials and Engineering Enablement. Chad opened
          <strong>{github_data["personal_prs_created"]}</strong> PRs, merged
          <strong>{github_data["personal_prs_merged"]}</strong>, and moved
          <strong>{linear_data["personal_issues_updated"]}</strong> assigned Linear issues through the week.
          The largest GitHub surface was <strong>{link_text(primary_repo, gh_pr_search_url(repo=primary_repo))}</strong>
          with <strong>{primary_repo_count}</strong> PRs.
        </p>
      </div>
      <aside class="impact-panel">
        <div class="kicker">Impact read</div>
        <h2>What changed because Chad was in the loop</h2>
        <p>
          CTC financials became deployable platform work, Datadog evidence got cleaner, agent tooling got sharper,
          and support threads resolved into concrete next steps instead of floating around Slack.
        </p>
        <ul class="impact-list">
          <li><strong>Shipped</strong><span>{linear_data["personal_issues_done_like"]} assigned Linear issues reached Done, including iQuote hosting, Datadog award rows, access, and CTC tooling.</span></li>
          <li><strong>Still moving</strong><span>{linear_data["personal_issues_in_review"]} assigned issues are in review, led by CTC financials consolidation and Saviynt audit-log collection.</span></li>
          <li><strong>Evidence</strong><span>Slack, Notion, GitHub, Linear, and Datadog all point at the same workstreams instead of five unrelated activity feeds.</span></li>
          <li><strong>Generated</strong><span>{esc(generated_label())}</span></li>
        </ul>
      </aside>
    </header>

    <nav class="sticky-nav">
      <a href="#summary">Summary</a>
      <a href="#workstreams">Workstreams</a>
      <a href="#proof">Proof trail</a>
      <a href="#lowlights">Lowlights</a>
      <a href="#datadog">Datadog</a>
      <a href="#slack">Slack</a>
      <a href="#notion">Notion</a>
      <a href="#method">Methodology</a>
    </nav>

    <section id="summary">
      <div class="section-heading">
        <h2>Summary</h2>
        <span class="tag">Personal scope</span>
      </div>
      <div class="stats-grid">{executive_cards}</div>
    </section>

    <section id="workstreams">
      <div class="section-heading">
        <h2>Workstreams</h2>
        <span class="tag">Where Chad moved the work</span>
      </div>
      {render_personal_workstreams()}
    </section>

    <section id="proof">
      <div class="section-heading">
        <h2>Proof trail</h2>
        <span class="tag">GitHub and Linear</span>
      </div>
      <p>
        The raw activity is narrower now: Chad-authored GitHub PRs and Chad-assigned Linear issues.
        Org-wide volume stays out of the headline because it doesn't prove personal impact.
      </p>
      <div class="split">
        {render_personal_pr_table("Chad-authored PRs opened", github_data["personal_created_items"], "createdAt")}
        {render_personal_linear_table("Chad-assigned Linear issues updated", linear_data["personal_updated"])}
      </div>
    </section>

    <section id="lowlights">
      <div class="section-heading">
        <h2>Lowlights</h2>
        <span class="tag">Briefly, with links</span>
      </div>
      {render_personal_lowlights()}
    </section>

    <section id="datadog">
      <div class="section-heading">
        <h2>Datadog</h2>
        <span class="tag">Personal touchpoints</span>
      </div>
      <p>
        Datadog is included where Chad touched the work: award-row correctness, certification dashboarding,
        Insights debugging, CSP monitoring, and SQLMesh follow-up. Generic incident volume is off the stage.
      </p>
      <div class="highlight-grid">
        {render_highlight_cards(datadog_data["highlights"], "url")}
      </div>
    </section>

    <section id="slack">
      <div class="section-heading">
        <h2>Slack</h2>
        <span class="tag">Where Chad showed up</span>
      </div>
      <p>
        Slack evidence is sampled from the threads that show Chad helping, deciding, unblocking, or keeping the work honest.
        It isn't a workspace-wide digest.
      </p>
      {render_highlight_cards(slack_highlights, "url")}
    </section>

    <section id="notion">
      <div class="section-heading">
        <h2>Notion</h2>
        <span class="tag">Planning context</span>
      </div>
      <p>
        The Notion slice covers docs that explain the work Chad was shaping: CTC financials, Insights migration,
        SQLMesh self-hosting, Salesforce migration rules, and data quality.
      </p>
      {render_highlight_cards(notion_highlights, "url")}
    </section>

    <section id="method">
      <div class="section-heading">
        <h2>Methodology</h2>
        <span class="tag">How to read it</span>
      </div>
      <ul class="method-list">
        <li>GitHub is filtered to PRs authored by {esc(PERSON_GITHUB_LOGIN)} from {esc(window_label)}.</li>
        <li>Linear is filtered to issues assigned to {esc(PERSON_LINEAR_ASSIGNEE)} and updated in the same window.</li>
        <li>Slack and Notion are connector-backed samples from the threads and docs where Chad appears to be directly involved.</li>
        <li>Datadog is limited to Chad-linked dashboard, monitor, debugging, and observability evidence.</li>
      </ul>
    </section>
  </div>
</body>
</html>
"""


def build_streamlined_personal_html(summary: dict) -> str:
    github_data = summary["github"]
    linear_data = summary["linear"]
    window_label = report_window_label()
    primary_repo = (
        github_data["personal_top_pr_repos"][0][0]
        if github_data["personal_top_pr_repos"]
        else "n/a"
    )
    primary_repo_count = (
        github_data["personal_top_pr_repos"][0][1] if github_data["personal_top_pr_repos"] else 0
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(REPORT_TITLE)}</title>
  <style>
    :root {{
      --bg: #f5f8f6;
      --panel: #ffffff;
      --ink: #15211f;
      --muted: #5c6866;
      --line: #d8e0dc;
      --teal: #0f766e;
      --rust: #b45336;
      --green: #4f6f31;
      --shadow: 0 18px 48px rgba(20, 32, 31, 0.08);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      background:
        linear-gradient(180deg, rgba(244, 250, 248, 0.96), rgba(250, 251, 249, 1)),
        linear-gradient(90deg, rgba(15, 118, 110, 0.08), rgba(180, 83, 54, 0.06));
    }}

    a {{
      color: var(--teal);
      text-decoration: underline;
      text-decoration-color: rgba(15, 118, 110, 0.35);
      text-underline-offset: 0.14em;
    }}

    .shell {{
      max-width: 1360px;
      margin: 0 auto;
      padding: 28px;
    }}

    .hero {{
      min-height: 560px;
      display: flex;
      align-items: end;
      position: relative;
      overflow: hidden;
      border-radius: 8px;
      border: 1px solid rgba(216, 224, 220, 0.9);
      background-image:
        linear-gradient(90deg, rgba(5, 14, 15, 0.92) 0%, rgba(5, 14, 15, 0.78) 34%, rgba(5, 14, 15, 0.26) 68%, rgba(5, 14, 15, 0.08) 100%),
        linear-gradient(180deg, rgba(5, 14, 15, 0.12), rgba(5, 14, 15, 0.72)),
        url("assets/platform-work-hero.png");
      background-size: cover;
      background-position: center;
      box-shadow: var(--shadow);
    }}

    .hero-content {{
      width: min(760px, 100%);
      padding: 42px;
      color: #f8fbf7;
    }}

    .eyebrow,
    .kicker,
    .work-kicker,
    .section-heading .tag {{
      color: #d27b55;
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.78rem;
      font-weight: 800;
    }}

    h1, h2, h3, h4 {{
      margin: 0;
      letter-spacing: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
    }}

    h1 {{
      margin-top: 14px;
      font-size: 4rem;
      line-height: 0.96;
      max-width: 10ch;
    }}

    .lede {{
      margin: 20px 0 0;
      max-width: 66ch;
      color: rgba(248, 251, 247, 0.82);
      line-height: 1.65;
      font-size: 1.04rem;
    }}

    .hero a {{
      color: #8ee2d6;
      text-decoration-color: rgba(142, 226, 214, 0.45);
    }}

    .metric-strip {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 24px;
      max-width: 760px;
    }}

    .metric {{
      min-height: 92px;
      padding: 14px;
      border-radius: 8px;
      border: 1px solid rgba(248, 251, 247, 0.18);
      background: rgba(248, 251, 247, 0.08);
      backdrop-filter: blur(8px);
    }}

    .metric strong {{
      display: block;
      color: #f8fbf7;
      font-size: 1.55rem;
      line-height: 1.05;
    }}

    .metric span {{
      display: block;
      margin-top: 6px;
      color: rgba(248, 251, 247, 0.74);
      line-height: 1.35;
      font-size: 0.92rem;
    }}

    .sticky-nav {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 18px 0 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(246, 248, 247, 0.9);
      backdrop-filter: blur(16px);
    }}

    .sticky-nav a {{
      text-decoration: none;
      color: var(--ink);
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(20, 32, 31, 0.05);
    }}

    section {{
      padding: 30px 0;
      border-top: 1px solid var(--line);
      scroll-margin-top: 92px;
    }}

    .section-heading {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 18px;
    }}

    section > p {{
      max-width: 84ch;
      color: var(--muted);
      line-height: 1.68;
    }}

    .body-grid {{
      display: grid;
      gap: 16px;
    }}

    .body-card {{
      display: grid;
      grid-template-columns: 72px minmax(0, 1fr);
      gap: 18px;
      padding: 22px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: 0 10px 28px rgba(20, 32, 31, 0.05);
      overflow: hidden;
      position: relative;
    }}

    .demo-card {{
      border-color: rgba(210, 123, 85, 0.55);
      box-shadow: 0 14px 34px rgba(210, 123, 85, 0.13);
    }}

    .demo-ribbon {{
      position: absolute;
      top: 16px;
      right: -42px;
      width: 172px;
      padding: 6px 0;
      transform: rotate(34deg);
      background: #d27b55;
      color: #fff9f4;
      text-align: center;
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.72rem;
      font-weight: 900;
      box-shadow: 0 8px 18px rgba(20, 32, 31, 0.16);
    }}

    .demo-line {{
      width: fit-content;
      max-width: 86ch;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid rgba(210, 123, 85, 0.36);
      background: rgba(210, 123, 85, 0.1);
      color: var(--ink) !important;
      font-weight: 700;
    }}

    .body-index {{
      width: 52px;
      height: 52px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      color: var(--teal);
      background: rgba(15, 118, 110, 0.1);
      font-weight: 800;
      font-size: 1.25rem;
    }}

    .body-card h3 {{
      margin-top: 8px;
      font-size: 1.5rem;
      line-height: 1.16;
    }}

    .body-card p {{
      max-width: 86ch;
      color: var(--muted);
      line-height: 1.64;
    }}

    .proof-line {{
      padding-left: 14px;
      border-left: 3px solid rgba(15, 118, 110, 0.35);
      color: var(--ink) !important;
    }}

    .evidence-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      font-size: 0.93rem;
    }}

    .discussion-card {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: center;
      padding: 22px;
      border-radius: 8px;
      border: 1px solid rgba(15, 118, 110, 0.38);
      background:
        linear-gradient(135deg, rgba(15, 118, 110, 0.1), rgba(210, 123, 85, 0.08)),
        var(--panel);
      box-shadow: 0 14px 34px rgba(20, 32, 31, 0.07);
    }}

    .discussion-card h3 {{
      margin-top: 8px;
      font-size: 1.5rem;
      line-height: 1.16;
    }}

    .discussion-card p {{
      max-width: 86ch;
      color: var(--muted);
      line-height: 1.64;
    }}

    .discussion-badge {{
      align-self: start;
      padding: 9px 11px;
      border-radius: 8px;
      background: #0f766e;
      color: #f8fbf7;
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.72rem;
      font-weight: 900;
      white-space: nowrap;
    }}

    .lowlight-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}

    .lowlight-card,
    .table-wrap {{
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: 0 10px 28px rgba(20, 32, 31, 0.05);
    }}

    .lowlight-card {{
      padding: 18px;
    }}

    .lowlight-card h4 {{
      font-size: 1.08rem;
      margin-bottom: 10px;
    }}

    .lowlight-card p {{
      color: var(--muted);
      line-height: 1.62;
    }}

    details {{
      border-radius: 8px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.72);
      overflow: hidden;
    }}

    summary {{
      cursor: pointer;
      padding: 16px 18px;
      font-weight: 800;
    }}

    summary::-webkit-details-marker {{
      display: none;
    }}

    .evidence-panel {{
      padding: 0 18px 18px;
    }}

    .split {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 16px;
    }}

    .table-wrap {{
      padding: 18px;
      overflow: auto;
    }}

    .table-wrap h4 {{
      margin-bottom: 12px;
      font-size: 1.08rem;
    }}

    .metric-table {{
      width: 100%;
      min-width: 660px;
      border-collapse: collapse;
    }}

    .metric-table th,
    .metric-table td {{
      padding: 11px 10px;
      text-align: left;
      vertical-align: top;
      border-top: 1px solid var(--line);
      font-size: 0.94rem;
    }}

    .metric-table thead th {{
      border-top: none;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.78rem;
    }}

    .method-list {{
      color: var(--muted);
      line-height: 1.68;
      margin: 0;
      padding-left: 20px;
    }}

    @media (max-width: 980px) {{
      .metric-strip,
      .split,
      .lowlight-grid {{
        grid-template-columns: 1fr 1fr;
      }}

      .discussion-card {{
        grid-template-columns: 1fr;
      }}

      .hero {{
        min-height: 660px;
        background-position: 64% center;
      }}
    }}

    @media (max-width: 640px) {{
      .shell {{
        padding: 16px;
      }}

      .hero-content {{
        padding: 24px;
      }}

      h1 {{
        max-width: none;
        font-size: 2.65rem;
      }}

      .metric-strip,
      .split,
      .lowlight-grid,
      .body-card {{
        grid-template-columns: 1fr;
      }}

      .body-index {{
        width: 44px;
        height: 44px;
      }}

      .demo-ribbon {{
        top: 16px;
        right: 16px;
        width: auto;
        padding: 7px 9px;
        transform: none;
        border-radius: 8px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <div class="hero-content">
        <div class="eyebrow">{esc(window_label)}</div>
        <h1>Chad's week in platform work.</h1>
        <p class="lede">
          The bigger story this week wasn't raw activity volume. It was five bodies of work moving together:
          CTC financials, Windows support, IT and Infrastructure support, platform runtime/tooling, and
          observability. The raw count still matters: Chad opened <strong>{github_data["personal_prs_created"]}</strong> PRs, merged
          <strong>{github_data["personal_prs_merged"]}</strong>, and moved
          <strong>{linear_data["personal_issues_updated"]}</strong> assigned Linear issues.
        </p>
        <div class="metric-strip">
          <div class="metric"><strong>{github_data["personal_prs_created"]}</strong><span>PRs opened, mostly in {esc(primary_repo)} ({primary_repo_count})</span></div>
          <div class="metric"><strong>{linear_data["personal_issues_done_like"]}</strong><span>assigned Linear issues moved to Done</span></div>
          <div class="metric"><strong>5</strong><span>major bodies of work carried the week</span></div>
          <div class="metric"><strong>3</strong><span>demo-worthy threads ready to show</span></div>
        </div>
      </div>
    </header>

    <nav class="sticky-nav">
      <a href="#discussion">Discuss this week</a>
      <a href="#workstreams">Bodies of work</a>
      <a href="#lowlights">Lowlights</a>
      <a href="#evidence">Evidence index</a>
      <a href="#method">Methodology</a>
    </nav>

    <section id="discussion">
      <div class="section-heading">
        <h2>Discuss this week</h2>
        <span class="tag">Bring forward</span>
      </div>
      <article class="discussion-card">
        <div>
          <div class="work-kicker">Temporal for data jobs</div>
          <h3>The Sergio Botero pairing session is a cross-team adoption thread worth raising.</h3>
          <p>
            Chad gave Sergio admin access to the data and analytics Temporal namespaces, walked through the
            current Temporal UI and worker model, and connected the discussion to the open Saviynt collector as
            a concrete reference. The follow-up is practical: Sergio can wrap one or two years of an existing
            DLT/Airflow historical data load in Temporal, test heartbeat/checkpoint behavior for paginated API
            failures, and schedule another pairing session once he starts building.
          </p>
          <div class="evidence-links">
            <a href="https://app.notion.com/p/3825f445bd31807eb469c3e3e8d1f184">Notion transcript</a>
            <a href="https://github.com/convergint/it-monorepo/pull/67">Saviynt reference PR</a>
          </div>
        </div>
        <div class="discussion-badge">Discuss this week</div>
      </article>
    </section>

    <section id="workstreams">
      <div class="section-heading">
        <h2>Bodies of work</h2>
        <span class="tag">The main story</span>
      </div>
      {render_workstream_bodies()}
    </section>

    <section id="lowlights">
      <div class="section-heading">
        <h2>Lowlights</h2>
        <span class="tag">Kept short</span>
      </div>
      {render_personal_lowlights()}
    </section>

    <section id="evidence">
      <div class="section-heading">
        <h2>Evidence index</h2>
        <span class="tag">Raw trail</span>
      </div>
      <p>
        The main sections link to the most relevant evidence inline. This index keeps the raw GitHub and Linear trail available without making the report read like a ledger.
      </p>
      <details>
        <summary>Open the GitHub and Linear tables</summary>
        <div class="evidence-panel">
          {render_evidence_index(summary)}
        </div>
      </details>
    </section>

    <section id="method">
      <div class="section-heading">
        <h2>Methodology</h2>
        <span class="tag">How to read it</span>
      </div>
      <ul class="method-list">
        <li>GitHub is filtered to PRs authored by {esc(PERSON_GITHUB_LOGIN)} from {esc(window_label)}, with it-monorepo evidence added where it explains Chad's IT and Infrastructure support work.</li>
        <li>Linear is filtered to issues assigned to {esc(PERSON_LINEAR_ASSIGNEE)} and updated in the same window.</li>
        <li>Slack, Notion, and Datadog links are used as supporting evidence inside the relevant bodies of work instead of repeated as separate digest sections. The Sergio Botero pairing transcript is called out separately because it is a discussion item for this week.</li>
        <li>The hero image is a locally generated PNG asset created by the report generator.</li>
      </ul>
    </section>
  </div>
</body>
</html>
"""


def build_demo_brief_html(summary: dict) -> str:
    github_data = summary["github"]
    linear_data = summary["linear"]
    datadog_data = summary["datadog"]
    slack_highlights = summary["slack_highlights"]
    notion_highlights = summary["notion_highlights"]
    window_label = report_window_label()

    primary_repo = (
        github_data["personal_top_pr_repos"][0][0]
        if github_data["personal_top_pr_repos"]
        else "n/a"
    )
    primary_repo_count = (
        github_data["personal_top_pr_repos"][0][1] if github_data["personal_top_pr_repos"] else 0
    )

    demo_items = [
        {
            "label": "Demo 01",
            "title": "CTC financials is the clearest show-and-tell.",
            "body": (
                "The app moved from a Dallas-server dashboard into a platform path with GitHub, "
                "CI, SSO planning, and a real data fix. The SQL root cause is concrete enough "
                "to explain, and the product value is easy to see."
            ),
            "evidence": [
                ("Planning notes", "https://app.notion.com/p/3815f445bd31806f8634d7d6abdc70b4"),
                (
                    "convergint/ctc-financials PR #11",
                    "https://github.com/convergint/ctc-financials/pull/11",
                ),
                (
                    "CTC thread",
                    "https://convergint.enterprise.slack.com/archives/C0AQHKE74MT/p1782516215054649?thread_ts=1781818845.350249&cid=C0AQHKE74MT",
                ),
            ],
        },
        {
            "label": "Demo 02",
            "title": "Temporal is ready to discuss beyond Engineering Enablement.",
            "body": (
                "Dual auth landed, the Temporal CLI path is documented, and the alert-fatigue "
                "worker gives a practical example of durable execution for scheduled operations."
            ),
            "evidence": [
                ("Temporal guide", "https://app.notion.com/p/3105f445bd3180759f1bd60b89bb79ef"),
                (
                    "convergint/ee-monorepo PR #1637",
                    "https://github.com/convergint/ee-monorepo/pull/1637",
                ),
                (
                    "convergint/ee-monorepo PR #1617",
                    "https://github.com/convergint/ee-monorepo/pull/1617",
                ),
            ],
        },
        {
            "label": "Demo 03",
            "title": "Datadog work has visible before-and-after evidence.",
            "body": (
                "The certification cohort dashboard was corrected, the observability canary "
                "alerts got quieter, and the onboarding CLI made a small operational path much faster."
            ),
            "evidence": [
                ("Cert dashboard", "https://us3.datadoghq.com/dashboard/vtg-s2b-mv2"),
                (
                    "convergint/ee-monorepo PR #1643",
                    "https://github.com/convergint/ee-monorepo/pull/1643",
                ),
                (
                    "Monitor thread",
                    "https://convergint.enterprise.slack.com/archives/C08N2ALU6PL/p1782775561265779?thread_ts=1782738515.678839&cid=C08N2ALU6PL",
                ),
            ],
        },
        {
            "label": "Demo 04",
            "title": "Mulesoft CloudHub support is a clean platform-assist story.",
            "body": (
                "A Slack support ask became DNS, Terraform, Cloudflare origin certificates, "
                "and Anypoint TLS context modeling. It is small enough to explain quickly."
            ),
            "evidence": [
                (
                    "convergint/mulesoft-integrations PR #2270",
                    "https://github.com/convergint/mulesoft-integrations/pull/2270",
                ),
                (
                    "convergint/mulesoft-integrations PR #2271",
                    "https://github.com/convergint/mulesoft-integrations/pull/2271",
                ),
                (
                    "Support thread",
                    "https://convergint.enterprise.slack.com/archives/C07EN6LGE5C/p1782918629548409",
                ),
            ],
        },
    ]

    work_lanes = [
        {
            "marker": "01",
            "title": "CTC financials moved from app rescue into platform ownership.",
            "body": (
                "Chad carried the repo, SQL correction, review loop, and hosting path together. "
                "The key technical fix was replacing view behavior that depended on dbo.FF_Company() "
                "with a clearer SQL path for the new read-only user."
            ),
            "proof": "EE-985 reached Done, convergint/ctc-financials PR #11 is the current implementation trail, and Hari confirmed the fix made sense while asking for a live number comparison.",
            "evidence": [
                (
                    "EE-985",
                    "https://linear.app/convergint/issue/EE-985/consolidate-ctc-financial-dashboards",
                ),
                (
                    "convergint/ctc-financials PR #11",
                    "https://github.com/convergint/ctc-financials/pull/11",
                ),
                ("Planning", "https://app.notion.com/p/3815f445bd31806f8634d7d6abdc70b4"),
            ],
        },
        {
            "marker": "02",
            "title": "Delivery rails got more reusable.",
            "body": (
                "The CD pipeline can run bespoke mise tasks as deploy targets, stable mise settings "
                "were swept across repos, and Temporal Cloud now supports API-key CLI access while "
                "workers keep platform-managed mTLS."
            ),
            "proof": "convergint/ee-monorepo PRs #1637, #1638, #1639, #1651, and #1652 form the visible trail behind the runtime and delivery-system work.",
            "evidence": [
                (
                    "convergint/ee-monorepo PR #1637",
                    "https://github.com/convergint/ee-monorepo/pull/1637",
                ),
                (
                    "convergint/ee-monorepo PR #1638",
                    "https://github.com/convergint/ee-monorepo/pull/1638",
                ),
                (
                    "convergint/ee-monorepo PR #1651",
                    "https://github.com/convergint/ee-monorepo/pull/1651",
                ),
                (
                    "convergint/ee-monorepo PR #1652",
                    "https://github.com/convergint/ee-monorepo/pull/1652",
                ),
            ],
        },
        {
            "marker": "03",
            "title": "Datadog stayed close to decisions people could act on.",
            "body": (
                "Chad fixed the certification dashboard data path, pushed the alert-fatigue worker "
                "toward a durable weekly process, and kept monitor tuning tied to actual alert volume."
            ),
            "proof": "The certification dashboard resolves in Datadog, the canary monitors are OK, and the staging alert volume dropped from roughly 52 per day to about 2 per day in the follow-up thread.",
            "evidence": [
                ("Dashboard", "https://us3.datadoghq.com/dashboard/vtg-s2b-mv2"),
                (
                    "convergint/ee-monorepo PR #1643",
                    "https://github.com/convergint/ee-monorepo/pull/1643",
                ),
                (
                    "EE-992",
                    "https://linear.app/convergint/issue/EE-992/run-alert-triage-as-a-temporal-worker",
                ),
            ],
        },
        {
            "marker": "04",
            "title": "Support work turned into auditable platform changes.",
            "body": (
                "Mulesoft QA DNS and TLS work, Salesforce repository governance, Oracle access, "
                "and the repo archive-candidate pass all moved through links people can review later."
            ),
            "proof": "The Salesforce repo is now managed by Terraform in ee-monorepo, Mulesoft DNS/TLS work is in review, and the stale-repo archive pass went to #engineering for owner input.",
            "evidence": [
                (
                    "convergint/mulesoft-integrations PR #2270",
                    "https://github.com/convergint/mulesoft-integrations/pull/2270",
                ),
                (
                    "convergint/mulesoft-integrations PR #2271",
                    "https://github.com/convergint/mulesoft-integrations/pull/2271",
                ),
                (
                    "convergint/ee-monorepo PR #1630",
                    "https://github.com/convergint/ee-monorepo/pull/1630",
                ),
                (
                    "Repo cleanup",
                    "https://convergint.enterprise.slack.com/archives/C07EUS59F7C/p1782941607475929?thread_ts=1782941607.475929&cid=C07EUS59F7C",
                ),
            ],
        },
        {
            "marker": "05",
            "title": "AI and agent operations got more measurable.",
            "body": (
                "Chad worked through Claude analytics API-key ownership for Datadog AI-agent telemetry, "
                "kept cloud-agent behavior in the open, and treated agent tooling as operational infrastructure."
            ),
            "proof": "The week includes Datadog AI Agents Console setup, Claude access support, public discussion in #vibe-coding, and alert triage as a managed-agent workflow.",
            "evidence": [
                ("AI Agents Console", "https://us3.datadoghq.com/llm/ai-agents-console/dashboard"),
                (
                    "Agent discussion",
                    "https://convergint.enterprise.slack.com/archives/C08PAQARM8E/p1782939414689819",
                ),
                (
                    "convergint/ee-monorepo PR #1617",
                    "https://github.com/convergint/ee-monorepo/pull/1617",
                ),
            ],
        },
    ]

    watch_items = [
        {
            "title": "CTC financials still needs a live comparison pass.",
            "body": (
                "Hari accepted the direction and still wants to compare numbers against the Dallas "
                "server in real time. That is the right next check before this becomes boring platform work."
            ),
            "url": "https://convergint.enterprise.slack.com/archives/C0AQHKE74MT/p1782772916255239?thread_ts=1782772916.255239&cid=C0AQHKE74MT",
        },
        {
            "title": "DBM setup is still too manual.",
            "body": (
                "The current docs ask developers to understand too much about extensions and explain-plan "
                "helpers. Chad called out the need to hide more of that behind the platform."
            ),
            "url": "https://convergint.enterprise.slack.com/archives/C08MGCF1FHN/p1782857180822179?thread_ts=1782856555.937059&cid=C08MGCF1FHN",
        },
        {
            "title": "Mulesoft TLS contexts are still in review.",
            "body": (
                "The DNS zone landed enough for validation, and the TLS context work is the follow-up "
                "that turns the support thread into repeatable Terraform."
            ),
            "url": "https://github.com/convergint/mulesoft-integrations/pull/2271",
        },
    ]

    def render_demo_items() -> str:
        cards = []
        for item in demo_items:
            cards.append(
                '<article class="agenda-item">'
                f'<div class="agenda-label">{esc(item["label"])}</div>'
                f"<h3>{esc(item['title'])}</h3>"
                f"<p>{esc(item['body'])}</p>"
                f"{render_evidence_links(item['evidence'])}"
                "</article>"
            )
        return '<div class="agenda-grid">' + "".join(cards) + "</div>"

    def render_work_lanes() -> str:
        lanes = []
        for lane in work_lanes:
            lanes.append(
                '<article class="lane">'
                f'<div class="lane-marker">{esc(lane["marker"])}</div>'
                '<div class="lane-body">'
                f"<h3>{esc(lane['title'])}</h3>"
                f"<p>{esc(lane['body'])}</p>"
                f'<p class="proof-note">{esc(lane["proof"])}</p>'
                f"{render_evidence_links(lane['evidence'])}"
                "</div>"
                "</article>"
            )
        return '<div class="lane-stack">' + "".join(lanes) + "</div>"

    def render_watch_items() -> str:
        items = []
        for item in watch_items:
            items.append(
                '<article class="watch-item">'
                f"<h3>{link_text(item['title'], item['url'])}</h3>"
                f"<p>{esc(item['body'])}</p>"
                "</article>"
            )
        return '<div class="watch-grid">' + "".join(items) + "</div>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(REPORT_TITLE)}</title>
  <style>
    :root {{
      --paper: #fbf8f0;
      --paper-2: #f3efe5;
      --ink: #161918;
      --muted: #606763;
      --line: #d9d0c0;
      --rail: #151b22;
      --teal: #0f766e;
      --blue: #315a8c;
      --red: #b54d3b;
      --gold: #9a6b18;
      --green: #496f37;
      --panel: #fffdf8;
      --shadow: 0 18px 44px rgba(22, 25, 24, 0.08);
    }}

    * {{
      box-sizing: border-box;
    }}

    html {{
      scroll-behavior: smooth;
    }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      background:
        linear-gradient(180deg, rgba(251, 248, 240, 0.96), rgba(243, 239, 229, 1)),
        var(--paper);
    }}

    a {{
      color: var(--teal);
      text-decoration: underline;
      text-decoration-color: rgba(15, 118, 110, 0.35);
      text-underline-offset: 0.14em;
      overflow-wrap: anywhere;
    }}

    h1, h2, h3, h4 {{
      margin: 0;
      letter-spacing: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
    }}

    p {{
      line-height: 1.62;
    }}

    .brief-shell {{
      display: grid;
      grid-template-columns: 292px minmax(0, 1fr);
      gap: 28px;
      max-width: 1480px;
      margin: 0 auto;
      padding: 24px;
    }}

    .side-rail {{
      position: sticky;
      top: 24px;
      align-self: start;
      min-height: calc(100vh - 48px);
      padding: 22px;
      border-radius: 8px;
      background: var(--rail);
      color: #f8f4ec;
      box-shadow: var(--shadow);
    }}

    .rail-label,
    .chapter-label,
    .agenda-label,
    .metric-label,
    .tag {{
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.76rem;
      font-weight: 900;
    }}

    .rail-label {{
      color: #e0a35f;
    }}

    .rail-title {{
      margin-top: 12px;
      font-size: 2rem;
      line-height: 1;
    }}

    .rail-meta {{
      margin: 14px 0 22px;
      color: rgba(248, 244, 236, 0.72);
      line-height: 1.5;
    }}

    .rail-nav {{
      display: grid;
      gap: 8px;
      margin: 22px 0;
    }}

    .rail-nav a {{
      display: block;
      padding: 10px 12px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.08);
      color: #f8f4ec;
      text-decoration: none;
    }}

    .rail-nav a:hover {{
      background: rgba(255, 255, 255, 0.14);
    }}

    .rail-fact {{
      display: grid;
      gap: 10px;
      padding-top: 18px;
      border-top: 1px solid rgba(255, 255, 255, 0.16);
    }}

    .rail-fact div {{
      display: grid;
      grid-template-columns: 56px minmax(0, 1fr);
      gap: 12px;
      align-items: baseline;
    }}

    .rail-fact strong {{
      color: #f8f4ec;
      font-size: 1.35rem;
    }}

    .rail-fact span {{
      color: rgba(248, 244, 236, 0.72);
      line-height: 1.35;
    }}

    .main {{
      min-width: 0;
    }}

    .masthead {{
      min-height: 440px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 280px;
      gap: 26px;
      align-items: stretch;
      padding: 28px 0 34px;
      border-bottom: 2px solid var(--ink);
    }}

    .masthead-copy {{
      display: flex;
      flex-direction: column;
      justify-content: end;
    }}

    .chapter-label {{
      color: var(--red);
    }}

    h1 {{
      margin-top: 14px;
      max-width: 13ch;
      font-size: 5rem;
      line-height: 0.92;
    }}

    .lede {{
      max-width: 78ch;
      margin: 22px 0 0;
      color: var(--muted);
      font-size: 1.04rem;
    }}

    .visual-strip {{
      min-height: 360px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background-image:
        linear-gradient(180deg, rgba(22, 25, 24, 0.08), rgba(22, 25, 24, 0.48)),
        url("assets/platform-work-hero.png");
      background-size: cover;
      background-position: center;
    }}

    .metric-row {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 18px 0 0;
    }}

    .metric-tile {{
      min-height: 110px;
      padding: 15px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 10px 24px rgba(22, 25, 24, 0.05);
    }}

    .metric-label {{
      color: var(--muted);
    }}

    .metric-value {{
      margin-top: 8px;
      font-size: 2rem;
      font-weight: 900;
      line-height: 1;
    }}

    .metric-note {{
      margin-top: 8px;
      color: var(--muted);
      line-height: 1.35;
      font-size: 0.92rem;
    }}

    .chapter {{
      padding: 32px 0;
      border-bottom: 1px solid var(--line);
      scroll-margin-top: 20px;
    }}

    .chapter-head {{
      display: grid;
      grid-template-columns: minmax(0, 0.75fr) minmax(280px, 0.25fr);
      gap: 24px;
      align-items: end;
      margin-bottom: 18px;
    }}

    .chapter-head h2 {{
      margin-top: 8px;
      font-size: 2.2rem;
      line-height: 1.04;
    }}

    .chapter-head p,
    .chapter-note {{
      color: var(--muted);
    }}

    .tag {{
      justify-self: end;
      color: var(--blue);
    }}

    .agenda-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}

    .agenda-item,
    .watch-item,
    .highlight-card,
    .table-wrap,
    details {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 10px 24px rgba(22, 25, 24, 0.05);
    }}

    .agenda-item {{
      padding: 18px;
    }}

    .agenda-label {{
      color: var(--gold);
    }}

    .agenda-item h3,
    .watch-item h3,
    .lane-body h3 {{
      margin-top: 8px;
      font-size: 1.32rem;
      line-height: 1.16;
    }}

    .agenda-item p,
    .watch-item p,
    .lane-body p,
    .highlight-card p,
    .highlight-card ul {{
      color: var(--muted);
    }}

    .lane-stack {{
      display: grid;
      gap: 16px;
    }}

    .lane {{
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr);
      gap: 18px;
      padding: 20px 0;
      border-top: 1px solid var(--line);
    }}

    .lane:first-child {{
      border-top: 0;
      padding-top: 0;
    }}

    .lane-marker {{
      width: 64px;
      height: 64px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      background: var(--ink);
      color: #fffaf1;
      font-weight: 900;
    }}

    .proof-note {{
      padding: 12px 14px;
      border-left: 4px solid var(--teal);
      background: rgba(15, 118, 110, 0.07);
      color: var(--ink) !important;
      font-weight: 700;
    }}

    .evidence-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      font-size: 0.93rem;
    }}

    .watch-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }}

    .watch-item {{
      padding: 18px;
      border-top: 4px solid var(--red);
    }}

    .signal-columns {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }}

    .signal-block h3 {{
      margin-bottom: 12px;
      color: var(--ink);
      font-size: 1.2rem;
    }}

    .highlight-grid {{
      display: grid;
      gap: 12px;
    }}

    .highlight-card {{
      padding: 16px;
    }}

    .highlight-meta {{
      color: var(--red);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0;
      font-weight: 900;
      margin-bottom: 9px;
    }}

    .highlight-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
    }}

    .highlight-card h4 {{
      font-size: 1.05rem;
      line-height: 1.18;
    }}

    .highlight-card ul {{
      padding-left: 18px;
    }}

    details {{
      overflow: hidden;
    }}

    summary {{
      cursor: pointer;
      padding: 16px 18px;
      font-weight: 900;
    }}

    summary::-webkit-details-marker {{
      display: none;
    }}

    .evidence-panel {{
      padding: 0 18px 18px;
    }}

    .split {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 16px;
    }}

    .table-wrap {{
      padding: 18px;
      overflow: auto;
    }}

    .table-wrap h4 {{
      margin-bottom: 12px;
      font-size: 1.08rem;
    }}

    .metric-table {{
      width: 100%;
      min-width: 660px;
      border-collapse: collapse;
    }}

    .metric-table th,
    .metric-table td {{
      padding: 11px 10px;
      text-align: left;
      vertical-align: top;
      border-top: 1px solid var(--line);
      font-size: 0.94rem;
    }}

    .metric-table thead th {{
      border-top: 0;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.78rem;
    }}

    .method-list {{
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
      line-height: 1.68;
    }}

    @media (max-width: 1120px) {{
      .brief-shell {{
        grid-template-columns: 1fr;
      }}

      .side-rail {{
        position: static;
        min-height: 0;
      }}

      .rail-nav {{
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }}

      .masthead,
      .chapter-head {{
        grid-template-columns: 1fr;
      }}

      .visual-strip {{
        min-height: 220px;
      }}

      .tag {{
        justify-self: start;
      }}
    }}

    @media (max-width: 780px) {{
      .brief-shell {{
        padding: 16px;
      }}

      h1 {{
        max-width: none;
        font-size: 3.2rem;
      }}

      .rail-nav,
      .metric-row,
      .agenda-grid,
      .watch-grid,
      .signal-columns,
      .split {{
        grid-template-columns: 1fr;
      }}

      .lane {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="brief-shell">
    <aside class="side-rail">
      <div class="rail-label">Demo meeting brief</div>
      <h2 class="rail-title">Chad's week in platform work</h2>
      <p class="rail-meta">{esc(window_label)}<br>{esc(generated_label())}</p>
      <nav class="rail-nav">
        <a href="#agenda">Agenda</a>
        <a href="#lanes">Work lanes</a>
        <a href="#watch">Watch items</a>
        <a href="#signals">Signals</a>
        <a href="#evidence">Evidence</a>
        <a href="#method">Method</a>
        <a href="demo-meeting-activity-brief.pdf">PDF handout</a>
      </nav>
      <div class="rail-fact">
        <div><strong>{github_data["personal_prs_created"]}</strong><span>PRs opened by Chad</span></div>
        <div><strong>{github_data["personal_prs_merged"]}</strong><span>Chad-authored PRs merged</span></div>
        <div><strong>{linear_data["personal_issues_done_like"]}</strong><span>assigned Linear issues moved to Done</span></div>
        <div><strong>{len(slack_highlights)}</strong><span>Slack evidence threads sampled</span></div>
      </div>
    </aside>

    <main class="main">
      <header class="masthead">
        <div class="masthead-copy">
          <div class="chapter-label">Personal activity report</div>
          <h1>Demo Meeting Activity Brief</h1>
          <p class="lede">
            This version uses a meeting-brief format for the demo meeting.
            The report starts with what is worth showing tomorrow, then walks through the
            work lanes and the evidence behind them.
          </p>
          <p class="lede">
            The week centered on CTC financials, Temporal, Datadog, delivery rails, and a
            handful of support threads that became auditable platform changes. Chad opened
            <strong>{github_data["personal_prs_created"]}</strong> PRs, moved
            <strong>{linear_data["personal_issues_updated"]}</strong> assigned Linear issues,
            and spent most of the GitHub surface in
            <strong>{link_text(primary_repo, gh_pr_search_url(repo=primary_repo))}</strong>
            with <strong>{primary_repo_count}</strong> PRs.
          </p>
        </div>
        <div class="visual-strip" aria-label="Generated platform work visual"></div>
      </header>

      <section class="metric-row" aria-label="Weekly metrics">
        <div class="metric-tile">
          <div class="metric-label">Primary repo</div>
          <div class="metric-value">{esc(primary_repo)}</div>
          <div class="metric-note">{primary_repo_count} Chad-authored PRs opened there this week.</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Linear movement</div>
          <div class="metric-value">{linear_data["personal_issues_done_like"]} done</div>
          <div class="metric-note">{linear_data["personal_issues_in_review"]} more assigned issues are in review.</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Datadog</div>
          <div class="metric-value">{datadog_data["dashboard_count"]} dashboard</div>
          <div class="metric-note">{datadog_data["incident_count"]} incidents found in the scoped Datadog incident read.</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Sources</div>
          <div class="metric-value">{len(notion_highlights)} docs</div>
          <div class="metric-note">Slack, Notion, GitHub, Linear, and Datadog all refreshed for this run.</div>
        </div>
      </section>

      <section id="agenda" class="chapter">
        <div class="chapter-head">
          <div>
            <div class="chapter-label">Start here</div>
            <h2>Demo candidates</h2>
            <p>These are the four topics that will be easiest to talk through in the meeting.</p>
          </div>
          <div class="tag">Show first</div>
        </div>
        {render_demo_items()}
      </section>

      <section id="lanes" class="chapter">
        <div class="chapter-head">
          <div>
            <div class="chapter-label">Main story</div>
            <h2>Five work lanes</h2>
            <p>Each lane groups code, planning, Slack decisions, and operational evidence together.</p>
          </div>
          <div class="tag">Personal scope</div>
        </div>
        {render_work_lanes()}
      </section>

      <section id="watch" class="chapter">
        <div class="chapter-head">
          <div>
            <div class="chapter-label">Keep visible</div>
            <h2>Watch items</h2>
            <p>These are the items worth naming without letting them take over the meeting.</p>
          </div>
          <div class="tag">Follow-up</div>
        </div>
        {render_watch_items()}
      </section>

      <section id="signals" class="chapter">
        <div class="chapter-head">
          <div>
            <div class="chapter-label">Source signals</div>
            <h2>Evidence pulled into the story</h2>
            <p>Connector-backed snapshots are sampled below. They support the work lanes rather than acting as separate digest sections.</p>
          </div>
          <div class="tag">Snapshot backed</div>
        </div>
        <div class="signal-columns">
          <div class="signal-block">
            <h3>Slack</h3>
            {render_highlight_cards(slack_highlights, "url")}
          </div>
          <div class="signal-block">
            <h3>Notion</h3>
            {render_highlight_cards(notion_highlights, "url")}
          </div>
          <div class="signal-block">
            <h3>Datadog</h3>
            {render_highlight_cards(datadog_data["highlights"], "url")}
          </div>
        </div>
      </section>

      <section id="evidence" class="chapter">
        <div class="chapter-head">
          <div>
            <div class="chapter-label">Raw trail</div>
            <h2>GitHub and Linear index</h2>
            <p>The brief keeps tables collapsed so the meeting starts with the story and still has the audit trail one click away.</p>
          </div>
          <div class="tag">Expandable</div>
        </div>
        <details>
          <summary>Open Chad-authored PRs and Chad-assigned Linear issues</summary>
          <div class="evidence-panel">
            {render_evidence_index(summary)}
          </div>
        </details>
      </section>

      <section id="method" class="chapter">
        <div class="chapter-head">
          <div>
            <div class="chapter-label">Methodology</div>
            <h2>How this was built</h2>
          </div>
          <div class="tag">Current run</div>
        </div>
        <ul class="method-list">
          <li>GitHub is filtered to PRs authored by {esc(PERSON_GITHUB_LOGIN)} from {esc(window_label)}.</li>
          <li>Linear is filtered to issues assigned to {esc(PERSON_LINEAR_ASSIGNEE)} and updated in the same window.</li>
          <li>Slack and Notion were refreshed from tracked seeds, then widened through a bounded discovery pass for CTC financials, Temporal, Datadog, Mulesoft, Salesforce, and repo governance.</li>
          <li>Datadog evidence came from scoped dashboard, monitor, and incident MCP reads plus Chad-linked Slack, GitHub, Linear, and Notion evidence.</li>
          <li>The report window is {esc(WINDOW_START)} through {esc(WINDOW_END)} in {esc(str(REPORT_TIMEZONE))}.</li>
        </ul>
      </section>
    </main>
  </div>
</body>
</html>
"""


def build_detail_html(title: str, intro: str, body_html: str, back_href: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>
    :root {{
      --surface: #fffdf8;
      --ink: #17211d;
      --muted: #5f6d66;
      --accent: #0f7b72;
      --line: #d7d0c2;
      --shadow: 0 24px 60px rgba(23, 33, 29, 0.08);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      background: linear-gradient(180deg, rgba(237, 245, 241, 0.96), #f9faf8);
    }}

    a {{
      color: var(--accent);
      text-decoration: none;
    }}

    a:hover {{
      text-decoration: underline;
    }}

    .shell {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 28px;
    }}

    .hero,
    .table-wrap {{
      background: var(--surface);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 8px;
    }}

    .hero {{
      padding: 24px;
    }}

    .eyebrow {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.8rem;
    }}

    h1, h2, h3, h4 {{
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      letter-spacing: 0;
      margin: 0;
    }}

    h1 {{
      margin-top: 12px;
      font-size: 2.8rem;
    }}

    p {{
      color: var(--muted);
      line-height: 1.68;
      max-width: 80ch;
    }}

    .back-link {{
      display: inline-block;
      margin-top: 16px;
      font-weight: 600;
    }}

    .table-wrap {{
      margin-top: 22px;
      padding: 18px;
      overflow: auto;
    }}

    .metric-table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
    }}

    .metric-table th,
    .metric-table td {{
      padding: 11px 10px;
      border-top: 1px solid rgba(215, 208, 194, 0.8);
      vertical-align: top;
      text-align: left;
      font-size: 0.94rem;
    }}

    .metric-table thead th {{
      border-top: none;
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="eyebrow">Convergint weekly drill-down</div>
      <h1>{esc(title)}</h1>
      <p>{esc(intro)}</p>
      <a class="back-link" href="{esc(back_href)}">Back to the main report</a>
    </section>
    {body_html}
  </div>
</body>
</html>
"""


def write_detail_pages() -> None:
    github_repos = load_json("github_repos.json")
    github_prs_created = load_json("github_prs_created.json")
    github_prs_merged = load_json("github_prs_merged.json")
    linear_issues = load_json("linear_issues_updated.json")
    linear_projects = load_json("linear_projects_month.json")
    datadog_data = datadog_summary()

    active_repos = sorted(
        [repo for repo in github_repos if in_window(parse_dt(repo.get("pushedAt")))],
        key=lambda repo: parse_dt(repo.get("pushedAt")) or START,
        reverse=True,
    )
    prs_created = sorted(
        github_prs_created,
        key=lambda pr: parse_dt(pr.get("createdAt")) or START,
        reverse=True,
    )
    prs_merged = sorted(
        github_prs_merged,
        key=lambda pr: parse_dt(pr.get("closedAt")) or START,
        reverse=True,
    )
    linear_updated = sorted(
        [issue for issue in linear_issues if in_window(parse_dt(issue.get("updatedAt")))],
        key=lambda issue: parse_dt(issue.get("updatedAt")) or START,
        reverse=True,
    )
    linear_created = sorted(
        [issue for issue in linear_issues if in_window(parse_dt(issue.get("createdAt")))],
        key=lambda issue: parse_dt(issue.get("createdAt")) or START,
        reverse=True,
    )
    projects_created = sorted(
        [project for project in linear_projects if in_window(parse_dt(project.get("createdAt")))],
        key=lambda project: parse_dt(project.get("createdAt")) or START,
        reverse=True,
    )
    projects_updated = sorted(
        [project for project in linear_projects if in_window(parse_dt(project.get("updatedAt")))],
        key=lambda project: parse_dt(project.get("updatedAt")) or START,
        reverse=True,
    )

    detail_pages = {
        "github-prs-created.html": build_detail_html(
            "GitHub PRs opened",
            f"All pull requests opened in the Convergint organization between {WINDOW_START} and {WINDOW_END}.",
            render_github_item_list("All PRs opened", prs_created, "createdAt", "Created"),
            "index.html#github",
        ),
        "github-prs-merged.html": build_detail_html(
            "GitHub PRs merged",
            f"All pull requests merged in the Convergint organization between {WINDOW_START} and {WINDOW_END}.",
            render_github_item_list("All PRs merged", prs_merged, "closedAt", "Merged"),
            "index.html#github",
        ),
        "github-active-repos.html": build_detail_html(
            "GitHub repos with pushes this week",
            f"Repositories with at least one push between {WINDOW_START} and {WINDOW_END}.",
            render_active_repo_list("Active repositories", active_repos),
            "index.html#github",
        ),
        "linear-issues-updated.html": build_detail_html(
            "Linear issues updated this week",
            f"Sampled Linear issues updated between {WINDOW_START} and {WINDOW_END}.",
            render_linear_issue_list(
                "All sampled updated issues", linear_updated, "updatedAt", "Updated"
            ),
            "index.html#linear",
        ),
        "linear-issues-created.html": build_detail_html(
            "Linear issues created this week",
            f"Sampled Linear issues created between {WINDOW_START} and {WINDOW_END}.",
            render_linear_issue_list(
                "All sampled newly created issues", linear_created, "createdAt", "Created"
            ),
            "index.html#linear",
        ),
        "linear-projects.html": build_detail_html(
            "Linear projects in motion",
            f"Projects created or updated in the same reporting window between {WINDOW_START} and {WINDOW_END}.",
            render_projects_table(projects_created or projects_updated),
            "index.html#linear",
        ),
        "linear-interesting-issues.html": build_detail_html(
            "Selected interesting Linear issues",
            "A judgment-based cut of the Linear issues that best represent the week's themes.",
            render_linear_issue_list(
                "Selected issues worth opening", linear_updated[:0], "updatedAt", "Updated"
            ),
            "index.html#linear",
        ),
        "datadog-evidence.html": build_detail_html(
            "Datadog evidence",
            f"Datadog highlights and lowlights pulled for {report_window_label()}.",
            render_datadog_item_table("Highlights", datadog_data["highlights"])
            + render_datadog_item_table("Lowlights", datadog_data["lowlights"]),
            "index.html#datadog",
        ),
    }

    for team_key in sorted(
        {
            issue.get("team", {}).get("key")
            for issue in linear_updated
            if issue.get("team", {}).get("key")
        }
    ):
        team_issues = [
            issue for issue in linear_updated if issue.get("team", {}).get("key") == team_key
        ]
        if not team_issues:
            continue
        detail_pages[linear_team_page(team_key)] = build_detail_html(
            f"{team_name(team_issues[0].get('team'))} issue updates",
            f"Sampled issues updated for {team_name(team_issues[0].get('team'))} between {WINDOW_START} and {WINDOW_END}.",
            render_linear_issue_list(
                f"{team_name(team_issues[0].get('team'))} updated issues",
                team_issues,
                "updatedAt",
                "Updated",
            ),
            "index.html#linear-teams",
        )

    for state_name in sorted(
        {issue.get("state", {}).get("name", "Unknown") for issue in linear_updated}
    ):
        state_issues = [
            issue
            for issue in linear_updated
            if issue.get("state", {}).get("name", "Unknown") == state_name
        ]
        if not state_issues:
            continue
        detail_pages[linear_state_page(state_name)] = build_detail_html(
            f"{state_name} Linear issues",
            f"Sampled issues in the {state_name} state that were updated between {WINDOW_START} and {WINDOW_END}.",
            render_linear_issue_list(
                f"{state_name} updated issues",
                state_issues,
                "updatedAt",
                "Updated",
            ),
            "index.html#linear-states",
        )

    interesting_by_id = {item["identifier"] for item in linear_summary()["interesting"]}
    interesting_issues = [
        issue for issue in linear_updated if issue.get("identifier") in interesting_by_id
    ]
    if interesting_issues:
        detail_pages["linear-interesting-issues.html"] = build_detail_html(
            "Selected interesting Linear issues",
            "A judgment-based cut of the Linear issues that best represent the week's themes.",
            render_linear_issue_list(
                "Selected issues worth opening",
                interesting_issues,
                "updatedAt",
                "Updated",
            ),
            "index.html#linear",
        )

    for name, html_doc in detail_pages.items():
        output_path(name).write_text(html_doc)


def reset_output_dir() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_file() and path.suffix in {".html", ".json"}:
            path.unlink()


def write_personal_detail_pages(summary: dict) -> None:
    github_data = summary["github"]
    linear_data = summary["linear"]
    datadog_data = summary["datadog"]

    detail_pages = {
        "personal-github-prs-created.html": build_detail_html(
            "Chad-authored PRs opened",
            f"Pull requests opened by {PERSON_GITHUB_LOGIN} between {WINDOW_START} and {WINDOW_END}.",
            render_personal_pr_table(
                "Chad-authored PRs opened",
                github_data["personal_created_items"],
                "createdAt",
            ),
            "index.html#evidence",
        ),
        "personal-github-prs-merged.html": build_detail_html(
            "Chad-authored PRs merged",
            f"Pull requests authored by {PERSON_GITHUB_LOGIN} and merged between {WINDOW_START} and {WINDOW_END}.",
            render_personal_pr_table(
                "Chad-authored PRs merged",
                github_data["personal_merged_items"],
                "closedAt",
            ),
            "index.html#evidence",
        ),
        "personal-linear-issues.html": build_detail_html(
            "Chad-assigned Linear issues",
            f"Linear issues assigned to {PERSON_LINEAR_ASSIGNEE} and updated between {WINDOW_START} and {WINDOW_END}.",
            render_personal_linear_table(
                "Chad-assigned Linear issues",
                linear_data["personal_updated"],
            ),
            "index.html#evidence",
        ),
        "personal-datadog-evidence.html": build_detail_html(
            "Chad-linked Datadog evidence",
            f"Datadog highlights and lowlights tied to Chad's week for {report_window_label()}.",
            render_datadog_item_table("Highlights", datadog_data["highlights"])
            + render_datadog_item_table("Lowlights", datadog_data["lowlights"]),
            "index.html#evidence",
        ),
    }

    for name, html_doc in detail_pages.items():
        output_path(name).write_text(html_doc)


def main() -> None:
    validate_data_dir()
    reset_output_dir()
    generate_hero_image()
    github_data = github_summary()
    linear_data = linear_summary()
    datadog_data = datadog_summary()
    slack_highlights = load_slack_highlights()
    notion_highlights = load_notion_highlights()
    muted_slack_channels = sorted(load_muted_slack_channels())
    slack_highlights = filtered_slack_highlights(slack_highlights)
    summary = {
        "title": REPORT_TITLE,
        "start": START.isoformat(),
        "end": END.isoformat(),
        "github": github_data,
        "linear": linear_data,
        "datadog": datadog_data,
        "slack_highlights": slack_highlights,
        "muted_slack_channels": muted_slack_channels,
        "notion_highlights": notion_highlights,
        "themes": [],
    }

    output_path("summary.json").write_text(json.dumps(summary, indent=2))
    output_path("index.html").write_text(build_demo_brief_html(summary))
    write_personal_detail_pages(summary)


if __name__ == "__main__":
    main()
