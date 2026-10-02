from __future__ import annotations

import html
import json
import math
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus

from agent_session_evidence import validate_agent_sessions
from report_config import (
    AGENT_SESSIONS_FILE,
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
    REPORT_TIMEZONE,
    REPORT_TITLE,
    REQUIRED_DATA_FILES,
    SLACK_SNAPSHOT_FILE,
    START,
    WINDOW_END,
    WINDOW_START,
)
from report_design import REPORT_CSS

PERSON_NAME = "Chad McElligott"
PERSON_GITHUB_LOGIN = "chadxz"
PERSON_LINEAR_ASSIGNEE = "Chad McElligott"


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
    for source in ["github", "linear", "slack", "notion", "datadog", "agent_sessions"]:
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
        "personal-agent-sessions.html": build_detail_html(
            "Agent session evidence",
            "Curated session evidence from Codex, Claude, and Cursor. "
            "Completed work and exploratory topics retain their verified status.",
            render_agent_session_table(summary["agent_sessions"]),
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


ECLIPSE_SVG = """
<svg class="eclipse" viewBox="0 0 400 400" role="img"
  aria-label="A dark eclipse with a faint red corona">
  <defs>
    <radialGradient id="corona">
      <stop offset="0.43" stop-color="#982532" stop-opacity="0"/>
      <stop offset="0.49" stop-color="#982532" stop-opacity=".7"/>
      <stop offset="0.54" stop-color="#982532" stop-opacity=".22"/>
      <stop offset="1" stop-color="#982532" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="200" cy="200" r="196" fill="url(#corona)"/>
  <circle cx="200" cy="200" r="95" fill="#0d0d0f" stroke="#76262e" stroke-width=".7"/>
  <path d="M45 200h54m202 0h54M200 45v54m0 202v54" stroke="#4d3034" stroke-width=".5"/>
  <circle cx="200" cy="200" r="145" fill="none" stroke="#2e2428"
    stroke-width=".5" stroke-dasharray="1 8"/>
</svg>
"""

MUTING_SCRIPT = """
<script>
/** Hide a Slack evidence channel after the local report server saves the choice. */
async function muteChannel(button) {
  const feedback = document.getElementById("mute-feedback");
  button.disabled = true;
  try {
    const response = await fetch("/mute", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({channel: button.dataset.channel})
    });
    if (!response.ok) throw new Error("The server couldn't save the mute.");
    button.closest(".highlight-card").remove();
    feedback.textContent = "Channel muted for future reports.";
  } catch (error) {
    button.disabled = false;
    feedback.textContent = error.message;
  }
}
document.querySelectorAll(".mute-button").forEach(button => {
  button.addEventListener("click", () => muteChannel(button));
});
</script>
"""


def load_agent_session_evidence() -> dict:
    """Load current agent evidence, preserving honest capture gaps."""

    snapshot = json.loads(AGENT_SESSIONS_FILE.read_text())
    if not isinstance(snapshot, dict):
        raise SystemExit("Agent session evidence must be a JSON object.")
    errors = validate_agent_sessions(snapshot, WINDOW_START, WINDOW_END, REPORT_TIMEZONE.key)
    if errors:
        raise SystemExit("\n".join(errors))
    return snapshot


def render_agent_session_table(snapshot: dict) -> str:
    """Render paraphrased evidence and status without exposing raw transcripts."""

    coverage = "".join(
        f"<li><strong>{esc(agent.title())}:</strong> {esc(entry['status'])}. "
        f"{esc(entry['detail'])}</li>"
        for agent, entry in snapshot["coverage"].items()
    )
    rows = []
    for entry in snapshot["sessions"]:
        evidence = [
            (item["label"], item["url"])
            for item in entry["evidence"]
            if item.get("label") and item.get("url")
        ]
        rows.append(
            "<tr>"
            f"<td>{esc(entry['agent'].title())}<br>{esc(fmt_date(entry['activity_at']))}</td>"
            f"<td><strong>{esc(entry['topic'])}</strong><br>{esc(entry['summary'])}</td>"
            f"<td>{esc(entry['status'].replace('_', ' '))}</td>"
            f"<td>{render_evidence_links(evidence)}</td>"
            "</tr>"
        )
    return (
        f'<ul class="method-list">{coverage}</ul>'
        '<div class="table-wrap"><table class="metric-table">'
        "<thead><tr><th>Source / date</th><th>Evidence</th><th>Work status</th>"
        "<th>Artifact</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def build_report_document(title: str, content: str, script: str = "") -> str:
    """Apply one accessible visual system to the report and all evidence pages."""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{REPORT_CSS}</style>
</head>
<body>
<a class="skip-link" href="#main-content">Skip to report</a>
<main id="main-content" class="shell">{content}</main>
{script}
</body>
</html>"""


def report_masthead() -> str:
    """Render the shared identity and exact reporting period."""

    return (
        '<div class="masthead"><div class="brand"><span class="brand-mark">CM</span>'
        "<span>Convergint<br>Platform engineering</span></div>"
        f'<span class="edition">Week in review<br>{esc(report_window_label())}</span></div>'
    )


def build_streamlined_personal_html(summary: dict) -> str:
    """Build the current personal narrative as a dark editorial dossier."""

    github = summary["github"]
    narrative = summary["narrative"]
    discussion = narrative["discussion"]
    exploration = narrative.get("exploration", [])
    discussion_evidence = [(item["label"], item["url"]) for item in discussion.get("evidence", [])]
    exploration_html = ""
    if exploration:
        exploration_html = (
            '<section id="exploration"><div class="section-heading">'
            '<h2><span class="section-no">03</span>What I\'m exploring</h2>'
            '<span class="tag">Open questions and proposals</span></div>'
            + render_snapshot_workstreams(exploration)
            + "</section>"
        )
    links = [
        ("PRs opened", "personal-github-prs-created.html"),
        ("PRs merged", "personal-github-prs-merged.html"),
        ("Linear activity", "personal-linear-issues.html"),
        ("Datadog evidence", "personal-datadog-evidence.html"),
        ("Agent session evidence", "personal-agent-sessions.html"),
        ("One-page PDF", "chad-weekly-activity-report-single-page.pdf"),
    ]
    archive = "".join(link_text(label, href) for label, href in links)
    content = f"""
{report_masthead()}
<header class="hero">
  <div class="hero-content">
    <div class="eyebrow">Personal activity / {esc(report_window_label())}</div>
    <h1>Chad's week in<br><span>platform work.</span></h1>
    <p class="lede">{esc(narrative["lede"])}</p>
  </div>
  {ECLIPSE_SVG}
</header>
<div class="metric-strip" aria-label="Report measures">
  <div class="metric"><strong>{github["personal_prs_created"]:02d}</strong>
    <span>Chad-authored PRs opened</span></div>
  <div class="metric"><strong>{github["personal_prs_merged"]:02d}</strong>
    <span>Chad-authored PRs merged</span></div>
  <div class="metric"><strong>{len(narrative["workstreams"]):02d}</strong>
    <span>Bodies of work, with status</span></div>
  <div class="metric"><strong>{len(exploration):02d}</strong>
    <span>Exploratory topics</span></div>
</div>
<nav class="sticky-nav" aria-label="Report sections">
  <a href="#discussion">Discuss</a><a href="#workstreams">Bodies of work</a>
  {"<a href='#exploration'>Exploration</a>" if exploration else ""}
  <a href="#lowlights">Open edges</a><a href="#evidence">Evidence</a>
  <a href="#method">Method</a>
</nav>
<section id="discussion">
  <div class="section-heading"><h2><span class="section-no">01</span>Discuss this week</h2>
    <span class="tag">Bring forward</span></div>
  <article class="discussion-card">
    <div class="work-kicker">{esc(discussion.get("kicker"))}</div>
    <h3>{esc(discussion["title"])}</h3><p>{esc(discussion["body"])}</p>
    {render_evidence_links(discussion_evidence)}
    <div class="discussion-badge">{esc(discussion.get("badge", "Discussion"))}</div>
  </article>
</section>
<section id="workstreams">
  <div class="section-heading"><h2><span class="section-no">02</span>Bodies of work</h2>
    <span class="tag">Delivered, prepared, investigated</span></div>
  {render_snapshot_workstreams(narrative["workstreams"])}
</section>
{exploration_html}
<section id="lowlights">
  <div class="section-heading"><h2><span class="section-no">04</span>Open edges</h2>
    <span class="tag">Still unresolved</span></div>
  {render_snapshot_lowlights(narrative["lowlights"])}
</section>
<section id="evidence">
  <div class="section-heading"><h2><span class="section-no">05</span>Evidence archive</h2>
    <span class="tag">Follow the work</span></div>
  <div class="archive-links">{archive}</div>
  <details><summary>GitHub and Linear records</summary>
    <div class="evidence-panel">{render_evidence_index(summary)}</div></details>
  <details><summary>Supporting Slack and Notion evidence</summary>
    <div class="evidence-panel">
      {render_highlight_cards(summary["slack_highlights"], "url", enable_mute=True)}
      <span id="mute-feedback" class="mute-feedback" role="status"></span>
      {render_highlight_cards(summary["notion_highlights"], "url")}
    </div></details>
</section>
<section id="method">
  <div class="section-heading"><h2><span class="section-no">06</span>Methodology</h2>
    <span class="tag">Scope and confidence</span></div>
  {render_snapshot_methodology(narrative["methodology"])}
</section>
<footer class="footer"><span>Chad McElligott / Convergint</span>
  <span>Snapshot: {esc(summary["refresh_manifest"]["refreshed_at"])}</span></footer>
"""
    return build_report_document(REPORT_TITLE, content, MUTING_SCRIPT)


def build_detail_html(title: str, intro: str, body_html: str, back_href: str) -> str:
    """Keep each evidence page in the report's shared visual system."""

    content = (
        report_masthead()
        + '<header class="detail-hero"><div class="eyebrow">Evidence archive</div>'
        + f"<h1>{esc(title)}</h1><p>{esc(intro)}</p>"
        + link_text("Back to week in review", back_href)
        + f"</header><section>{body_html}</section>"
    )
    return build_report_document(title, content)


def main() -> None:
    validate_data_dir()
    reset_output_dir()
    github_data = github_summary()
    linear_data = linear_summary()
    datadog_data = datadog_summary()
    refresh_manifest = load_refresh_manifest()
    narrative = load_personal_report()
    agent_sessions = load_agent_session_evidence()
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
        "agent_sessions": agent_sessions,
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
