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
    PERSONAL_REPORT_SNAPSHOT_FILE,
    REFRESH_MANIFEST_FILE,
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


def load_personal_report() -> dict:
    if not PERSONAL_REPORT_SNAPSHOT_FILE.exists():
        raise SystemExit(
            "Missing required personal report narrative snapshot.\n"
            f"- {PERSONAL_REPORT_SNAPSHOT_FILE.name}\n"
            "Refresh the current conclusions with $reporting-work-activity before building the report."
        )
    try:
        data = json.loads(PERSONAL_REPORT_SNAPSHOT_FILE.read_text())
    except json.JSONDecodeError:
        raise SystemExit(
            "Invalid personal report narrative snapshot JSON.\n"
            f"- {PERSONAL_REPORT_SNAPSHOT_FILE.name}\n"
            "Refresh the current conclusions with $reporting-work-activity before building the report."
        ) from None
    if not isinstance(data, dict):
        raise SystemExit(
            "Invalid personal report narrative snapshot shape.\n"
            f"- {PERSONAL_REPORT_SNAPSHOT_FILE.name}\n"
            "Expected an object with the current lede, discussion, workstreams, lowlights, and methodology."
        )

    lede = data.get("lede")
    window = data.get("window")
    discussion = data.get("discussion")
    workstreams = data.get("workstreams")
    lowlights = data.get("lowlights")
    methodology = data.get("methodology")
    if not isinstance(lede, str) or not lede.strip():
        raise SystemExit("Personal report narrative requires a non-empty `lede` string.")
    expected_window = {"start": WINDOW_START, "end": WINDOW_END}
    if (
        not isinstance(window, dict)
        or {
            "start": window.get("start"),
            "end": window.get("end"),
        }
        != expected_window
    ):
        raise SystemExit(
            "Personal report narrative window does not match the selected report window.\n"
            f"- expected: {WINDOW_START} through {WINDOW_END}\n"
            "Refresh `personal_report.json` from current evidence before building the report."
        )
    if not isinstance(discussion, dict):
        raise SystemExit("Personal report narrative requires a `discussion` object.")
    if not isinstance(workstreams, list) or not workstreams:
        raise SystemExit("Personal report narrative requires at least one workstream.")
    if not isinstance(lowlights, list) or not lowlights:
        raise SystemExit("Personal report narrative requires at least one lowlight.")
    if not isinstance(methodology, list) or not methodology:
        raise SystemExit("Personal report narrative requires methodology notes.")
    return data


def load_refresh_manifest() -> dict:
    if not REFRESH_MANIFEST_FILE.exists():
        raise SystemExit(
            "Missing required refresh manifest.\n"
            f"- {REFRESH_MANIFEST_FILE.name}\n"
            "Finish every evidence refresh and write its receipt before building the report."
        )
    try:
        data = json.loads(REFRESH_MANIFEST_FILE.read_text())
    except json.JSONDecodeError:
        raise SystemExit(
            "Invalid refresh manifest JSON.\n"
            f"- {REFRESH_MANIFEST_FILE.name}\n"
            "Rewrite the refresh receipt from the current evidence pass."
        ) from None
    if not isinstance(data, dict):
        raise SystemExit("Refresh manifest must be a JSON object.")

    window = data.get("window")
    expected_window = {
        "start": WINDOW_START,
        "end": WINDOW_END,
        "timezone": REPORT_TIMEZONE.key,
    }
    if window != expected_window:
        raise SystemExit(
            "Refresh manifest window does not match the selected report window.\n"
            f"- expected: {WINDOW_START} through {WINDOW_END} in {REPORT_TIMEZONE.key}\n"
            "Refresh every evidence source for the selected window before building the report."
        )

    sources = data.get("sources")
    if not isinstance(sources, dict):
        raise SystemExit("Refresh manifest requires a `sources` object.")
    allowed_statuses = {"refreshed", "confirmed_current"}
    for source in ["github", "linear", "slack", "notion", "datadog"]:
        receipt = sources.get(source)
        if not isinstance(receipt, dict) or receipt.get("status") not in allowed_statuses:
            raise SystemExit(
                f"Refresh manifest requires a current receipt for `{source}`.\n"
                "Use `refreshed`, or `confirmed_current` only when the user explicitly "
                "approved preserved cache."
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
        "EE-1057",
        "Removes a no-op tracing variable from every platform workload after the current Datadog injection path made the old setting obsolete.",
    ),
    (
        "EE-1058",
        "Keeps root mise installs reproducible by pinning the missing npm tool and resolving Nx from the workspace dependency.",
    ),
    (
        "VIB-47",
        "Closes the production secret-management prerequisite for the CTC Financials project.",
    ),
    (
        "EE-997",
        "Completes the managed GitHub access path for Salesforce contributors.",
    ),
    (
        "EE-959",
        "Connects the Salesforce access work to the wider SOC2 repository-permission cleanup.",
    ),
    (
        "EE-1044",
        "Renames the shared dependency review action around its support for both Dependabot and Renovate.",
    ),
    (
        "EE-1047",
        "Moves Linear invitations and Entra group assignment into the same onboarding CLI as the other engineering applications.",
    ),
    (
        "PE-5",
        "Closes the Salesforce governance discovery that informed the repository access model.",
    ),
    (
        "EE-1043",
        "Makes Terraform and managed teams the source of truth for Salesforce repository access.",
    ),
    (
        "EE-1041",
        "Turns the availability synthetics into code and adds the five-minute gate that removes short-lived pages.",
    ),
    (
        "EE-1039",
        "Encodes Claude's three spend-tier groups in the shared onboarding CLI.",
    ),
    (
        "EE-1012",
        "Makes approved and rejected 1Password references readable when platform manifest validation fails.",
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
            "kicker": "Alert management",
            "title": "Alert triage became a durable weekly product, and CD learned how to ship it.",
            "body": (
                "Chad merged the alert-fatigue-triage worker as a scheduled Go Temporal app. Each run "
                "reviews the prior week's Datadog monitor and SLO traffic, carries Slack feedback "
                "forward, asks a bounded judge for up to five recommendations, and posts one visible "
                "result. Shipping it also added mise-backed CD targets, phased deployment for the "
                "managed agent and worker, and the missing Anthropic secret path."
            ),
            "proof": "EE-992 closed; PRs #1617, #1631, #1638, and #1647 merged; the live worker path now has durable scheduling and repo-owned release steps.",
            "demo_note": "Demo angle: one weekly workflow connects Datadog evidence, Slack feedback, a managed-agent review, and a single actionable post.",
            "evidence": [
                (
                    "EE-992",
                    "https://linear.app/convergint/issue/EE-992/run-alert-triage-as-a-temporal-worker",
                ),
                ("Worker PR", "https://github.com/convergint/ee-monorepo/pull/1617"),
                ("CD ADR", "https://github.com/convergint/ee-monorepo/pull/1631"),
                ("CD implementation", "https://github.com/convergint/ee-monorepo/pull/1638"),
                ("Deploy secret fix", "https://github.com/convergint/ee-monorepo/pull/1647"),
                ("Datadog QBR", "https://app.notion.com/p/3905f445bd3180aa9461f1035d14393b"),
            ],
        },
        {
            "kicker": "Temporal self-service",
            "title": "Temporal access moved from a platform exception to a documented operator path.",
            "body": (
                "Chad moved every shared Temporal namespace to dual authentication, kept workers on "
                "platform-managed mTLS, and documented personal API-key access through the regional CLI "
                "endpoint. When that CLI path failed from the Huntsville office, he proved the account "
                "and namespace were healthy, isolated outbound port 7233, and worked with Michael Gorsuch "
                "to route Temporal through a Tailscale app connector."
            ),
            "proof": "EE-999 closed and PR #1637 left all 14 staging and production namespaces active with API-key-or-mTLS auth; it-monorepo PR #84 restored office access the same day.",
            "demo_note": "Demo angle: an engineer can create a personal API key, configure the CLI, inspect a workflow, and keep production workers on managed certificates.",
            "evidence": [
                (
                    "EE-999",
                    "https://linear.app/convergint/issue/EE-999/enable-dual-temporal-namespace-auth",
                ),
                ("Dual-auth PR", "https://github.com/convergint/ee-monorepo/pull/1637"),
                ("Temporal guide", "https://app.notion.com/p/3105f445bd3180759f1bd60b89bb79ef"),
                (
                    "Announcement",
                    "https://convergint.enterprise.slack.com/archives/C07EUS59F7C/p1782772398151829?thread_ts=1782772398.151829&cid=C07EUS59F7C",
                ),
                (
                    "Egress diagnosis",
                    "https://convergint.enterprise.slack.com/archives/C07GXTS5YP8/p1783011006872829?thread_ts=1783011006.872829&cid=C07GXTS5YP8",
                ),
                ("Tailscale route PR", "https://github.com/convergint/it-monorepo/pull/84"),
            ],
        },
        {
            "kicker": "Mulesoft QA ingress",
            "title": "A DNS question became an applied CloudHub path with Terraform-owned TLS contexts.",
            "body": (
                "Shamyr Bogossian asked how to register the new Mulesoft QA domain. Chad compared the "
                "existing environments, added and applied the Cloudflare zone, then followed the certificate "
                "problem into Anypoint. He imported the existing private spaces and TLS contexts, generated "
                "the QA Origin CA certificate, kept private keys out of Terraform state, and added "
                "infrastructure-scoped CI."
            ),
            "proof": "PR #2270 applied 9 DNS resources and merged in-window. PR #2271 opened in-window with the TLS ownership path and merged on July 7.",
            "demo_note": "Demo angle: start with a QA hostname, follow it through Cloudflare and Anypoint, and finish with a repeatable Terraform and CI path.",
            "evidence": [
                (
                    "Support thread",
                    "https://convergint.enterprise.slack.com/archives/C07EN6LGE5C/p1782918629548409?thread_ts=1782918629.548409&cid=C07EN6LGE5C",
                ),
                (
                    "EE-1006",
                    "https://linear.app/convergint/issue/EE-1006/add-qa-mulesoft-cloudhub-dns-zone",
                ),
                (
                    "EE-1007",
                    "https://linear.app/convergint/issue/EE-1007/capture-anypoint-tls-contexts",
                ),
                ("DNS PR", "https://github.com/convergint/mulesoft-integrations/pull/2270"),
                (
                    "TLS contexts PR",
                    "https://github.com/convergint/mulesoft-integrations/pull/2271",
                ),
            ],
        },
        {
            "kicker": "Shared delivery contracts",
            "title": "Support failures turned into fixes that improved the common platform path.",
            "body": (
                "A DATABASICS job exposed multiline JSON handling in the shared manifest schema. Chad fixed "
                "web app, worker, and job validation, then confirmed the original workflow passed. The same "
                "week included stable mise monorepo settings across three repositories, clearer deploy errors, "
                "OpenFGA CI and action repairs, .NET 10 runtime alignment, and Terraform ownership for Oracle "
                "repository access."
            ),
            "proof": "The DATABASICS rerun succeeded after PR #1656; 11 Chad-authored ee-monorepo PRs and nine more across five repos kept the shared path moving.",
            "evidence": [
                (
                    "DATABASICS thread",
                    "https://convergint.enterprise.slack.com/archives/C08LY5M58FM/p1783003547709159?thread_ts=1783003547.709159&cid=C08LY5M58FM",
                ),
                (
                    "EE-1011",
                    "https://linear.app/convergint/issue/EE-1011/fix-multiline-manifest-env-validation",
                ),
                ("Manifest fix", "https://github.com/convergint/ee-monorepo/pull/1656"),
                ("Stable mise", "https://github.com/convergint/ee-monorepo/pull/1651"),
                ("OpenFGA action", "https://github.com/convergint/customer-portal/pull/937"),
                ("OpenFGA build", "https://github.com/convergint/customer-portal/pull/938"),
                (".NET runtime", "https://github.com/convergint/platform-examples/pull/645"),
                ("Oracle access", "https://github.com/convergint/ee-monorepo/pull/1653"),
            ],
        },
        {
            "kicker": "Datadog operating model",
            "title": "Dashboard work and the first QBR made observability adoption measurable.",
            "body": (
                "Chad added a participant-by-participant course trend to the Datadog Certifications Cohort "
                "dashboard and fixed top lists that could show an older sparse snapshot. The first QBR then "
                "put numbers behind the wider work: monthly active users grew 186 percent, dashboards grew "
                "from 4 to 60, monitors grew from 4 to roughly 321, and Chad ranked second in active usage."
            ),
            "proof": "EE-1003 closed and PR #1643 merged after the live metric API confirmed Gustavo Vargas at 7 completed classes; the QBR set follow-up for product-level usage and spend visibility.",
            "evidence": [
                (
                    "EE-1003",
                    "https://linear.app/convergint/issue/EE-1003/add-datadog-participant-class-trend",
                ),
                ("Dashboard PR", "https://github.com/convergint/ee-monorepo/pull/1643"),
                ("Cert dashboard", "https://us3.datadoghq.com/dashboard/vtg-s2b-mv2"),
                ("QBR notes", "https://app.notion.com/p/3905f445bd3180aa9461f1035d14393b"),
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
            "Insights staging could not exercise the complete production path.",
            "The web app, database, and workers were deployed. MQTT still needed a dedicated broker and "
            "representative traffic, and the staging review found Datadog logs without traces or metrics.",
            "https://app.notion.com/p/3915f445bd31816a9a6eefc0fb32884a",
        ),
        (
            "Mulesoft QA TLS crossed the report boundary.",
            "The DNS zone applied and merged during the week. The TLS-context PR remained open at the "
            "end of the window, merged on July 7, and still needed an operational confirmation from the "
            "requesting team.",
            "https://github.com/convergint/mulesoft-integrations/pull/2271",
        ),
        (
            "CTC Fleet still depended on a Dallas-only manual upload.",
            "Hari Gunturu and Chad split Fleet from the other two dashboards. That decision narrowed the "
            "platform app scope and left a separate path to design for Fleet.",
            "https://convergint.enterprise.slack.com/archives/C0AQHKE74MT/p1782915645333609?thread_ts=1782915645.333609&cid=C0AQHKE74MT",
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


def render_snapshot_workstreams(workstreams: list[dict]) -> str:
    articles = []
    for index, workstream in enumerate(workstreams, start=1):
        demo_note = workstream.get("demo_note")
        article_class = "body-card demo-card" if demo_note else "body-card"
        demo_ribbon = '<div class="demo-ribbon">Demo-worthy</div>' if demo_note else ""
        demo_line = f'<p class="demo-line">{esc(demo_note)}</p>' if demo_note else ""
        evidence = [
            (item["label"], item["url"])
            for item in workstream.get("evidence", [])
            if isinstance(item, dict) and item.get("label") and item.get("url")
        ]
        articles.append(
            f'<article class="{article_class}">'
            f"{demo_ribbon}"
            f'<div class="body-index">{index}</div>'
            '<div class="body-content">'
            f'<div class="work-kicker">{esc(workstream.get("kicker"))}</div>'
            f"<h3>{esc(workstream.get('title'))}</h3>"
            f"<p>{esc(workstream.get('body'))}</p>"
            f"{demo_line}"
            f'<p class="proof-line">{esc(workstream.get("proof"))}</p>'
            f"{render_evidence_links(evidence)}"
            "</div>"
            "</article>"
        )
    return '<div class="body-grid">' + "".join(articles) + "</div>"


def render_snapshot_lowlights(lowlights: list[dict]) -> str:
    cards = []
    for lowlight in lowlights:
        cards.append(
            '<article class="lowlight-card">'
            f"<h4>{link_text(lowlight.get('title'), lowlight.get('url'))}</h4>"
            f"<p>{esc(lowlight.get('body'))}</p>"
            "</article>"
        )
    return '<div class="lowlight-grid">' + "".join(cards) + "</div>"


def render_snapshot_methodology(methodology: list[str]) -> str:
    return (
        '<ul class="method-list">'
        + "".join(f"<li>{esc(note)}</li>" for note in methodology if isinstance(note, str) and note)
        + "</ul>"
    )


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
    narrative = summary["narrative"]
    discussion = narrative["discussion"]
    window_label = report_window_label()
    primary_repo = (
        github_data["personal_top_pr_repos"][0][0]
        if github_data["personal_top_pr_repos"]
        else "n/a"
    )
    primary_repo_count = (
        github_data["personal_top_pr_repos"][0][1] if github_data["personal_top_pr_repos"] else 0
    )
    discussion_evidence = [
        (item["label"], item["url"])
        for item in discussion.get("evidence", [])
        if isinstance(item, dict) and item.get("label") and item.get("url")
    ]

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
  <style id="technical-brief-redesign">
    :root {{
      --void: #060b0d;
      --rail: #080f12;
      --surface: #0d171a;
      --surface-raised: #132125;
      --ink: #edf5f1;
      --muted: #8da19b;
      --line: #26373c;
      --acid: #c9ff4a;
      --cyan: #61d9e8;
      --coral: #ff765f;
      --black: #05090a;
      --display: "Arial Narrow", "Roboto Condensed", "Helvetica Neue", sans-serif;
      --body: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    }}

    html {{
      color-scheme: dark;
      scroll-behavior: smooth;
      background: var(--void);
    }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: var(--body);
      background-color: var(--void);
      background-image:
        linear-gradient(rgba(97, 217, 232, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(97, 217, 232, 0.035) 1px, transparent 1px);
      background-size: 48px 48px;
    }}

    body::before {{
      position: fixed;
      z-index: 50;
      top: 0;
      right: 0;
      left: 0;
      height: 3px;
      background: var(--acid);
      content: "";
    }}

    ::selection {{
      color: var(--black);
      background: var(--acid);
    }}

    a {{
      color: inherit;
      text-decoration-color: var(--cyan);
      text-decoration-thickness: 1px;
      text-underline-offset: 0.22em;
    }}

    a:focus-visible,
    summary:focus-visible {{
      outline: 2px solid var(--acid);
      outline-offset: 4px;
    }}

    .skip-link {{
      position: fixed;
      z-index: 100;
      top: 10px;
      left: 10px;
      padding: 10px 14px;
      color: var(--black);
      background: var(--acid);
      font: 800 0.76rem/1 var(--mono);
      text-transform: uppercase;
      transform: translateY(-160%);
    }}

    .skip-link:focus {{
      transform: translateY(0);
    }}

    .shell {{
      max-width: none;
      margin: 0;
      padding: 0 0 0 240px;
    }}

    .hero,
    section {{
      width: min(1380px, calc(100% - 96px));
      margin-inline: auto;
    }}

    .hero {{
      min-height: 720px;
      display: block;
      position: relative;
      isolation: isolate;
      margin-top: 48px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--surface);
      box-shadow: 14px 14px 0 rgba(97, 217, 232, 0.12);
    }}

    .hero::before {{
      position: absolute;
      z-index: -1;
      inset: 0;
      background:
        linear-gradient(90deg, transparent 49.9%, var(--line) 50%, transparent 50.1%),
        linear-gradient(transparent 49.9%, rgba(38, 55, 60, 0.7) 50%, transparent 50.1%);
      content: "";
      opacity: 0.6;
    }}

    .hero::after {{
      position: absolute;
      top: 24px;
      right: 28px;
      color: rgba(237, 245, 241, 0.06);
      content: "7D";
      font: 900 clamp(6rem, 13vw, 13rem)/0.8 var(--display);
      letter-spacing: -0.08em;
    }}

    .hero-content {{
      width: 100%;
      min-height: 718px;
      display: grid;
      grid-template-columns: minmax(0, 1.08fr) minmax(360px, 0.92fr);
      grid-template-rows: auto 1fr auto;
      gap: 42px 64px;
      align-items: end;
      padding: 64px;
      color: var(--ink);
    }}

    .eyebrow,
    .kicker,
    .work-kicker,
    .section-heading .tag {{
      color: var(--acid);
      font: 800 0.76rem/1.2 var(--mono);
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}

    .eyebrow {{
      grid-column: 1 / -1;
      align-self: start;
      width: fit-content;
      padding: 8px 10px;
      border: 1px solid var(--acid);
      background: rgba(201, 255, 74, 0.06);
    }}

    h1,
    h2,
    h3,
    h4 {{
      margin: 0;
      color: var(--ink);
      font-family: var(--display);
      letter-spacing: -0.035em;
    }}

    h1 {{
      grid-column: 1;
      grid-row: 2;
      align-self: end;
      max-width: 8.5ch;
      margin: 0;
      font-size: clamp(4.8rem, 8.5vw, 9rem);
      font-weight: 900;
      line-height: 0.82;
      text-transform: uppercase;
    }}

    h1 span {{
      color: var(--acid);
    }}

    .lede {{
      grid-column: 1;
      grid-row: 3;
      max-width: 62ch;
      margin: 0;
      color: var(--muted);
      font-size: 1.06rem;
      line-height: 1.72;
    }}

    .lede strong {{
      color: var(--ink);
      font-weight: 750;
    }}

    .metric-strip {{
      grid-column: 2;
      grid-row: 2 / span 2;
      align-self: end;
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 1px;
      width: 100%;
      max-width: none;
      margin: 0;
      border: 1px solid var(--line);
      background: var(--line);
    }}

    .metric {{
      min-height: 148px;
      grid-column: span 4;
      padding: 24px;
      border: 0;
      border-radius: 0;
      background: var(--surface-raised);
      backdrop-filter: none;
    }}

    .metric:first-child {{
      min-height: 260px;
      grid-column: 1 / -1;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      background: var(--acid);
    }}

    .metric strong {{
      display: block;
      color: var(--ink);
      font: 900 2.4rem/0.9 var(--display);
      letter-spacing: -0.05em;
    }}

    .metric:first-child strong {{
      color: var(--black);
      font-size: clamp(6.5rem, 10vw, 10rem);
    }}

    .metric span {{
      display: block;
      margin-top: 12px;
      color: var(--muted);
      font: 600 0.76rem/1.45 var(--mono);
      text-transform: uppercase;
    }}

    .metric:first-child span {{
      max-width: 36ch;
      color: rgba(5, 9, 10, 0.72);
    }}

    .sticky-nav {{
      position: fixed;
      z-index: 30;
      inset: 3px auto 0 0;
      width: 240px;
      height: calc(100vh - 3px);
      display: flex;
      flex-direction: column;
      flex-wrap: nowrap;
      gap: 0;
      margin: 0;
      padding: 28px 22px 24px;
      border: 0;
      border-right: 1px solid var(--line);
      border-radius: 0;
      background: var(--rail);
      backdrop-filter: none;
    }}

    .rail-brand {{
      display: grid;
      grid-template-columns: 52px 1fr;
      gap: 12px;
      align-items: center;
      margin-bottom: 42px;
    }}

    .brand-mark {{
      width: 52px;
      height: 52px;
      display: grid;
      place-items: center;
      color: var(--black);
      background: var(--acid);
      font: 900 1.15rem/1 var(--mono);
    }}

    .rail-brand strong,
    .rail-brand small {{
      display: block;
    }}

    .rail-brand strong {{
      color: var(--ink);
      font: 800 0.82rem/1.2 var(--mono);
      text-transform: uppercase;
    }}

    .rail-brand small {{
      margin-top: 4px;
      color: var(--muted);
      font: 600 0.66rem/1.2 var(--mono);
      text-transform: uppercase;
    }}

    .rail-label {{
      margin-bottom: 10px;
      color: var(--muted);
      font: 700 0.62rem/1 var(--mono);
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }}

    .sticky-nav a {{
      display: grid;
      grid-template-columns: 30px 1fr;
      gap: 8px;
      align-items: center;
      padding: 14px 0;
      border-top: 1px solid var(--line);
      border-radius: 0;
      color: var(--muted);
      background: none;
      font: 700 0.76rem/1.2 var(--mono);
      text-decoration: none;
      text-transform: uppercase;
      transition: color 160ms ease, padding-left 160ms ease;
    }}

    .sticky-nav a:last-of-type {{
      border-bottom: 1px solid var(--line);
    }}

    .sticky-nav a:hover {{
      padding-left: 8px;
      color: var(--acid);
    }}

    .sticky-nav a .nav-index {{
      color: var(--acid);
      font-size: 0.62rem;
    }}

    .rail-status {{
      display: grid;
      grid-template-columns: 10px 1fr;
      gap: 10px;
      align-items: start;
      margin-top: auto;
      padding-top: 18px;
      color: var(--muted);
      font: 600 0.68rem/1.45 var(--mono);
      text-transform: uppercase;
    }}

    .rail-status strong,
    .rail-status small {{
      display: block;
    }}

    .rail-status strong {{
      color: var(--ink);
    }}

    .status-dot {{
      width: 8px;
      height: 8px;
      margin-top: 2px;
      border-radius: 50%;
      background: var(--acid);
      box-shadow: 0 0 0 4px rgba(201, 255, 74, 0.1);
    }}

    section {{
      position: relative;
      padding: 112px 0;
      border-top: 1px solid var(--line);
      scroll-margin-top: 24px;
    }}

    .section-heading {{
      display: grid;
      grid-template-columns: 190px minmax(0, 1fr);
      gap: 28px;
      align-items: end;
      margin-bottom: 48px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }}

    .section-heading h2 {{
      grid-column: 2;
      grid-row: 1;
      font-size: clamp(3rem, 5.8vw, 6rem);
      font-weight: 900;
      line-height: 0.88;
      text-transform: uppercase;
    }}

    .section-heading .tag {{
      grid-column: 1;
      grid-row: 1;
      align-self: end;
      padding-bottom: 5px;
    }}

    section > p {{
      max-width: 76ch;
      margin: 0 0 34px 218px;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.72;
    }}

    .discussion-card {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 74px;
      gap: 0;
      align-items: stretch;
      padding: 0;
      border: 0;
      border-radius: 0;
      color: var(--black);
      background: var(--acid);
      box-shadow: 12px 12px 0 var(--cyan);
    }}

    .discussion-card > div:first-child {{
      padding: 52px 56px;
    }}

    .discussion-card .work-kicker {{
      color: rgba(5, 9, 10, 0.68);
    }}

    .discussion-card h3 {{
      max-width: 22ch;
      margin-top: 16px;
      color: var(--black);
      font-size: clamp(2.2rem, 4vw, 4.4rem);
      font-weight: 900;
      line-height: 0.96;
      text-transform: uppercase;
    }}

    .discussion-card p {{
      max-width: 78ch;
      margin: 24px 0 0;
      color: rgba(5, 9, 10, 0.72);
      font-size: 1.02rem;
      line-height: 1.68;
    }}

    .discussion-card .evidence-links {{
      border-top-color: rgba(5, 9, 10, 0.24);
    }}

    .discussion-card .evidence-links a {{
      border-color: rgba(5, 9, 10, 0.36);
      color: var(--black);
      background: rgba(5, 9, 10, 0.04);
    }}

    .discussion-badge {{
      min-height: 100%;
      display: grid;
      place-items: center;
      align-self: stretch;
      padding: 18px;
      border-radius: 0;
      color: var(--acid);
      background: var(--black);
      font: 900 0.72rem/1 var(--mono);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      white-space: nowrap;
      writing-mode: vertical-rl;
    }}

    .body-grid {{
      display: grid;
      gap: 0;
      border-top: 1px solid var(--line);
    }}

    .body-card {{
      min-height: 380px;
      display: grid;
      grid-template-columns: 140px minmax(0, 1fr);
      gap: 0;
      position: relative;
      padding: 0;
      overflow: hidden;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      background: rgba(13, 23, 26, 0.68);
      box-shadow: none;
      transition: background 180ms ease;
    }}

    .body-card:nth-child(even) {{
      background: rgba(19, 33, 37, 0.76);
    }}

    .body-card:hover {{
      background: var(--surface-raised);
    }}

    .demo-card {{
      border-color: var(--line);
      box-shadow: none;
    }}

    .body-index {{
      width: auto;
      height: auto;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding-top: 46px;
      border-right: 1px solid var(--line);
      border-radius: 0;
      color: rgba(141, 161, 155, 0.28);
      background: none;
      font: 900 4.8rem/1 var(--display);
      letter-spacing: -0.08em;
    }}

    .demo-card .body-index {{
      color: var(--acid);
    }}

    .body-content {{
      padding: 46px 64px 52px;
    }}

    .demo-card .body-content {{
      padding-right: 200px;
    }}

    .body-card h3 {{
      max-width: 28ch;
      margin-top: 14px;
      color: var(--ink);
      font-size: clamp(2rem, 3.4vw, 3.7rem);
      font-weight: 900;
      line-height: 0.98;
      text-transform: uppercase;
    }}

    .body-card p {{
      max-width: 82ch;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.72;
    }}

    .demo-ribbon {{
      position: absolute;
      z-index: 2;
      top: 36px;
      right: 0;
      width: auto;
      padding: 10px 16px;
      transform: none;
      color: var(--black);
      background: var(--acid);
      font: 900 0.68rem/1 var(--mono);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      box-shadow: -6px 6px 0 rgba(97, 217, 232, 0.75);
    }}

    .demo-line {{
      width: auto;
      max-width: 80ch;
      margin: 26px 0 0;
      padding: 16px 18px;
      border: 0;
      border-left: 4px solid var(--acid);
      border-radius: 0;
      color: var(--ink) !important;
      background: rgba(201, 255, 74, 0.06);
      font-weight: 700;
    }}

    .proof-line {{
      margin-top: 28px !important;
      padding: 20px 0 0;
      border-top: 1px solid var(--line);
      border-left: 0;
      color: var(--ink) !important;
      font-family: var(--mono);
      font-size: 0.82rem !important;
      line-height: 1.65 !important;
    }}

    .evidence-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 22px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }}

    .evidence-links a {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 9px 11px;
      border: 1px solid var(--line);
      color: var(--ink);
      background: var(--surface);
      font: 700 0.68rem/1 var(--mono);
      text-decoration: none;
      text-transform: uppercase;
      transition: border-color 140ms ease, color 140ms ease, transform 140ms ease;
    }}

    .evidence-links a::before {{
      width: 5px;
      height: 5px;
      background: var(--cyan);
      content: "";
    }}

    .evidence-links a:hover {{
      border-color: var(--acid);
      color: var(--acid);
      transform: translateY(-2px);
    }}

    .lowlight-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1px;
      border: 1px solid var(--line);
      background: var(--line);
    }}

    .lowlight-card,
    .table-wrap {{
      border: 0;
      border-radius: 0;
      background: var(--surface);
      box-shadow: none;
    }}

    .lowlight-card {{
      min-height: 300px;
      position: relative;
      padding: 64px 34px 34px;
    }}

    .lowlight-card::before {{
      position: absolute;
      top: 28px;
      left: 34px;
      color: var(--coral);
      content: "OPEN EDGE";
      font: 800 0.65rem/1 var(--mono);
      letter-spacing: 0.12em;
    }}

    .lowlight-card h4 {{
      margin: 0 0 18px;
      font-size: 1.55rem;
      font-weight: 850;
      line-height: 1.08;
      letter-spacing: -0.025em;
    }}

    .lowlight-card h4 a {{
      color: var(--ink);
      text-decoration: none;
    }}

    .lowlight-card h4 a:hover {{
      color: var(--coral);
    }}

    .lowlight-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.68;
    }}

    details {{
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--surface);
    }}

    summary {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px 22px;
      color: var(--black);
      background: var(--acid);
      cursor: pointer;
      font: 850 0.78rem/1 var(--mono);
      text-transform: uppercase;
    }}

    summary::after {{
      content: "+";
      font-size: 1.3rem;
    }}

    details[open] summary::after {{
      content: "x";
    }}

    .evidence-panel {{
      padding: 1px;
      background: var(--line);
    }}

    .split {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 1px;
    }}

    .table-wrap {{
      margin: 0;
      padding: 24px;
      overflow: auto;
    }}

    .table-wrap h4 {{
      margin-bottom: 18px;
      color: var(--ink);
      font-size: 1rem;
      font-family: var(--mono);
      letter-spacing: 0;
      text-transform: uppercase;
    }}

    .metric-table {{
      width: 100%;
      min-width: 660px;
      border-collapse: collapse;
    }}

    .metric-table th,
    .metric-table td {{
      padding: 13px 10px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.84rem;
      text-align: left;
      vertical-align: top;
    }}

    .metric-table td a {{
      color: var(--ink);
    }}

    .metric-table td a:hover {{
      color: var(--acid);
    }}

    .metric-table thead th {{
      border-top: 0;
      color: var(--cyan);
      font: 700 0.67rem/1 var(--mono);
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }}

    .method-list {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1px;
      margin: 0;
      padding: 1px;
      color: var(--muted);
      background: var(--line);
      counter-reset: method;
      list-style: none;
    }}

    .method-list li {{
      min-height: 170px;
      position: relative;
      padding: 32px 32px 32px 82px;
      background: var(--surface);
      counter-increment: method;
      line-height: 1.68;
    }}

    .method-list li::before {{
      position: absolute;
      top: 32px;
      left: 30px;
      color: var(--acid);
      content: "0" counter(method);
      font: 850 0.78rem/1 var(--mono);
    }}

    @media (max-width: 1160px) {{
      .shell {{
        padding-left: 0;
      }}

      .hero,
      section {{
        width: min(100% - 48px, 1100px);
      }}

      .sticky-nav {{
        position: sticky;
        inset: 0 auto auto;
        width: 100%;
        height: auto;
        flex-direction: row;
        align-items: center;
        overflow-x: auto;
        padding: 12px 18px;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }}

      .rail-brand {{
        grid-template-columns: 38px 1fr;
        min-width: 170px;
        margin: 0 22px 0 0;
      }}

      .brand-mark {{
        width: 38px;
        height: 38px;
        font-size: 0.8rem;
      }}

      .rail-label,
      .rail-status {{
        display: none;
      }}

      .sticky-nav a,
      .sticky-nav a:last-of-type {{
        min-width: max-content;
        padding: 12px 16px;
        border: 0;
        border-left: 1px solid var(--line);
      }}

      .sticky-nav a:hover {{
        padding-left: 16px;
      }}

      .hero {{
        margin-top: 24px;
      }}

      .hero-content {{
        grid-template-columns: 1fr;
        grid-template-rows: auto auto auto auto;
        gap: 34px;
      }}

      .eyebrow,
      h1,
      .lede,
      .metric-strip {{
        grid-column: 1;
        grid-row: auto;
      }}

      .metric-strip {{
        margin-top: 16px;
      }}
    }}

    @media (max-width: 760px) {{
      .hero,
      section {{
        width: calc(100% - 28px);
      }}

      .hero {{
        min-height: 0;
        box-shadow: 7px 7px 0 rgba(97, 217, 232, 0.12);
      }}

      .hero-content {{
        min-height: 0;
        padding: 34px 26px;
      }}

      .hero::after {{
        top: 24px;
        font-size: 5rem;
      }}

      h1 {{
        max-width: 9ch;
        font-size: clamp(3.5rem, 18vw, 6rem);
      }}

      .metric-strip {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}

      .metric,
      .metric:first-child {{
        min-height: 132px;
        grid-column: span 1;
      }}

      .metric:first-child {{
        grid-column: 1 / -1;
      }}

      .metric:first-child strong {{
        font-size: 5.5rem;
      }}

      section {{
        padding: 78px 0;
      }}

      .section-heading {{
        display: block;
        margin-bottom: 34px;
      }}

      .section-heading h2 {{
        margin-top: 14px;
        font-size: 3.4rem;
      }}

      section > p {{
        margin-left: 0;
      }}

      .discussion-card {{
        grid-template-columns: 1fr;
        box-shadow: 7px 7px 0 var(--cyan);
      }}

      .discussion-card > div:first-child {{
        padding: 34px 26px;
      }}

      .discussion-card h3 {{
        font-size: 2.55rem;
      }}

      .discussion-badge {{
        min-height: 0;
        padding: 14px;
        writing-mode: horizontal-tb;
      }}

      .body-card {{
        min-height: 0;
        grid-template-columns: 1fr;
      }}

      .body-index {{
        justify-content: flex-start;
        padding: 24px 26px;
        border-right: 0;
        border-bottom: 1px solid var(--line);
        font-size: 2.8rem;
      }}

      .body-content,
      .demo-card .body-content {{
        padding: 34px 26px 38px;
      }}

      .body-card h3 {{
        font-size: 2.35rem;
      }}

      .demo-ribbon {{
        top: 24px;
        font-size: 0.58rem;
      }}

      .lowlight-grid,
      .split,
      .method-list {{
        grid-template-columns: 1fr;
      }}

      .lowlight-card {{
        min-height: 0;
      }}
    }}

    @media (prefers-reduced-motion: reduce) {{
      html {{
        scroll-behavior: auto;
      }}

      *,
      *::before,
      *::after {{
        transition-duration: 0.01ms !important;
      }}
    }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to report</a>
  <main id="main-content" class="shell">
    <header class="hero">
      <div class="hero-content">
        <div class="eyebrow">Personal activity / {esc(window_label)}</div>
        <h1>Chad's week in <span>platform work.</span></h1>
        <p class="lede">
          {esc(narrative["lede"])} Chad opened <strong>{github_data["personal_prs_created"]}</strong> PRs, merged
          <strong>{github_data["personal_prs_merged"]}</strong>, and moved
          <strong>{linear_data["personal_issues_done_like"]}</strong> assigned Linear issues into completed states.
        </p>
        <div class="metric-strip">
          <div class="metric"><strong>{github_data["personal_prs_created"]}</strong><span>PRs opened, mostly in {esc(primary_repo)} ({primary_repo_count})</span></div>
          <div class="metric"><strong>{github_data["personal_prs_merged"]}</strong><span>Chad-authored PRs merged in the window</span></div>
          <div class="metric"><strong>{linear_data["personal_issues_done_like"]}</strong><span>assigned Linear issues reached completed states</span></div>
          <div class="metric"><strong>{len(narrative["workstreams"])}</strong><span>major bodies of work carried the window</span></div>
        </div>
      </div>
    </header>

    <nav class="sticky-nav" aria-label="Report sections">
      <div class="rail-brand">
        <span class="brand-mark">CM</span>
        <span><strong>Weekly activity</strong><small>Platform engineering</small></span>
      </div>
      <div class="rail-label">Sections</div>
      <a href="#discussion"><span class="nav-index">01</span><span>Discuss</span></a>
      <a href="#workstreams"><span class="nav-index">02</span><span>Workstreams</span></a>
      <a href="#lowlights"><span class="nav-index">03</span><span>Open edges</span></a>
      <a href="#evidence"><span class="nav-index">04</span><span>Evidence</span></a>
      <a href="#method"><span class="nav-index">05</span><span>Method</span></a>
      <div class="rail-status">
        <span class="status-dot"></span>
        <span><strong>Report online</strong><small>{esc(window_label)}</small></span>
      </div>
    </nav>

    <section id="discussion">
      <div class="section-heading">
        <h2>Discuss this week</h2>
        <span class="tag">Bring forward</span>
      </div>
      <article class="discussion-card">
        <div>
          <div class="work-kicker">{esc(discussion.get("kicker"))}</div>
          <h3>{esc(discussion.get("title"))}</h3>
          <p>{esc(discussion.get("body"))}</p>
          {render_evidence_links(discussion_evidence)}
        </div>
        <div class="discussion-badge">{esc(discussion.get("badge", "Discuss this week"))}</div>
      </article>
    </section>

    <section id="workstreams">
      <div class="section-heading">
        <h2>Bodies of work</h2>
        <span class="tag">The main story</span>
      </div>
      {render_snapshot_workstreams(narrative["workstreams"])}
    </section>

    <section id="lowlights">
      <div class="section-heading">
        <h2>Lowlights</h2>
        <span class="tag">Kept short</span>
      </div>
      {render_snapshot_lowlights(narrative["lowlights"])}
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
      {render_snapshot_methodology(narrative["methodology"])}
    </section>
  </main>
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
  <style id="technical-brief-detail-redesign">
    :root {{
      --void: #060b0d;
      --surface: #0d171a;
      --surface-raised: #132125;
      --ink: #edf5f1;
      --muted: #8da19b;
      --line: #26373c;
      --acid: #c9ff4a;
      --cyan: #61d9e8;
      --black: #05090a;
      --display: "Arial Narrow", "Roboto Condensed", "Helvetica Neue", sans-serif;
      --body: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    }}

    html {{
      color-scheme: dark;
      background: var(--void);
    }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: var(--body);
      background-color: var(--void);
      background-image:
        linear-gradient(rgba(97, 217, 232, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(97, 217, 232, 0.035) 1px, transparent 1px);
      background-size: 48px 48px;
    }}

    body::before {{
      position: fixed;
      z-index: 10;
      top: 0;
      right: 0;
      left: 0;
      height: 3px;
      background: var(--acid);
      content: "";
    }}

    ::selection {{
      color: var(--black);
      background: var(--acid);
    }}

    a {{
      color: var(--ink);
      text-decoration-color: var(--cyan);
      text-underline-offset: 0.2em;
    }}

    a:hover {{
      color: var(--acid);
      text-decoration: underline;
    }}

    a:focus-visible {{
      outline: 2px solid var(--acid);
      outline-offset: 4px;
    }}

    .shell {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 48px;
    }}

    .hero,
    .table-wrap {{
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--surface);
      box-shadow: none;
    }}

    .hero {{
      min-height: 430px;
      display: grid;
      align-content: end;
      position: relative;
      isolation: isolate;
      overflow: hidden;
      padding: 54px;
      box-shadow: 12px 12px 0 rgba(97, 217, 232, 0.12);
    }}

    .hero::before {{
      position: absolute;
      z-index: -1;
      inset: 0 auto 0 0;
      width: 14px;
      background: var(--acid);
      content: "";
    }}

    .hero::after {{
      position: absolute;
      z-index: -1;
      top: 28px;
      right: 34px;
      color: rgba(237, 245, 241, 0.045);
      content: "EVIDENCE";
      font: 900 clamp(4rem, 10vw, 10rem)/0.9 var(--display);
      letter-spacing: -0.07em;
    }}

    .eyebrow {{
      width: fit-content;
      padding: 8px 10px;
      border: 1px solid var(--acid);
      color: var(--acid);
      font: 800 0.7rem/1 var(--mono);
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}

    h1,
    h2,
    h3,
    h4 {{
      margin: 0;
      color: var(--ink);
      font-family: var(--display);
      letter-spacing: -0.035em;
    }}

    h1 {{
      max-width: 19ch;
      margin-top: 24px;
      font-size: clamp(3.3rem, 7vw, 7rem);
      font-weight: 900;
      line-height: 0.88;
      text-transform: uppercase;
    }}

    p {{
      max-width: 78ch;
      margin: 24px 0 0;
      color: var(--muted);
      font-size: 1.02rem;
      line-height: 1.7;
    }}

    .back-link {{
      display: inline-flex;
      width: fit-content;
      margin-top: 28px;
      padding: 11px 13px;
      border: 1px solid var(--acid);
      color: var(--acid);
      font: 800 0.7rem/1 var(--mono);
      text-decoration: none;
      text-transform: uppercase;
    }}

    .back-link:hover {{
      color: var(--black);
      background: var(--acid);
      text-decoration: none;
    }}

    .table-wrap {{
      margin-top: 28px;
      padding: 28px;
      overflow: auto;
    }}

    .table-wrap h4 {{
      margin-bottom: 20px;
      color: var(--cyan);
      font: 800 0.78rem/1 var(--mono);
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }}

    .metric-table {{
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
    }}

    .metric-table th,
    .metric-table td {{
      padding: 14px 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.88rem;
      text-align: left;
      vertical-align: top;
    }}

    .metric-table td a {{
      color: var(--ink);
    }}

    .metric-table td a:hover {{
      color: var(--acid);
    }}

    .metric-table thead th {{
      border-top: 0;
      color: var(--cyan);
      font: 750 0.68rem/1 var(--mono);
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }}

    @media (max-width: 760px) {{
      .shell {{
        padding: 22px 14px 36px;
      }}

      .hero {{
        min-height: 360px;
        padding: 32px 26px;
        box-shadow: 7px 7px 0 rgba(97, 217, 232, 0.12);
      }}

      .hero::after {{
        font-size: 4rem;
      }}

      h1 {{
        font-size: 3.4rem;
      }}

      .table-wrap {{
        padding: 20px 14px;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Convergint weekly drill-down</div>
      <h1>{esc(title)}</h1>
      <p>{esc(intro)}</p>
      <a class="back-link" href="{esc(back_href)}">Back to the main report</a>
    </section>
    {body_html}
  </main>
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
        if path.is_file() and path.suffix in {".html", ".json", ".pdf"}:
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
    refresh_manifest = load_refresh_manifest()
    narrative = load_personal_report()
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
        "refresh_manifest": refresh_manifest,
        "narrative": narrative,
        "slack_highlights": slack_highlights,
        "muted_slack_channels": muted_slack_channels,
        "notion_highlights": notion_highlights,
        "themes": [],
    }

    output_path("summary.json").write_text(json.dumps(summary, indent=2))
    output_path("index.html").write_text(build_streamlined_personal_html(summary))
    write_personal_detail_pages(summary)


if __name__ == "__main__":
    main()
