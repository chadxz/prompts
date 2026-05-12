from __future__ import annotations

import html
import json
import math
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus

from report_config import (
    DATA_DIR,
    END,
    LINEAR_WORKSPACE,
    MUTED_SLACK_CHANNELS_FILE,
    NOTION_SNAPSHOT_FILE,
    ORG,
    OUTPUT_DIR,
    REPORT_SERVER_ORIGIN,
    REPORT_TITLE,
    REQUIRED_DATA_FILES,
    SLACK_SNAPSHOT_FILE,
    START,
    WINDOW_END,
    WINDOW_START,
)


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
    }


LINEAR_INTERESTING_NOTES = [
    (
        "EE-531",
        "Turns delivery health into a first-class platform signal by tying deploy success to dashboards and SLO work.",
    ),
    (
        "EE-881",
        "A strong example of platform work being driven by a real product incident: Cloudflare bot controls proposed as defense-in-depth for Gamma auth failures.",
    ),
    (
        "EE-883",
        "Small on paper, but strategically useful because it adds visibility to HR Master sync behavior that was also showing up in Slack support traffic.",
    ),
    (
        "GAM-1038",
        "The app-side auth failure that made the Cloudflare/WAF review feel urgent rather than theoretical.",
    ),
    (
        "GAM-1260",
        "Architectural restructuring inside iCare10 suggests the team is paying down design debt, not just shipping point fixes.",
    ),
    (
        "ALP-1858",
        "A concrete production performance issue that mixes API behavior, database locks, blob IO, and email side effects in one failure mode.",
    ),
    (
        "DAT-2399",
        "Matches the week's broader data-alert story: moving from one-off firefighting toward a clearer operating model for audit failures.",
    ),
    (
        "CUS-1234",
        "This is customer-facing rollout work with real operational surface area, so it matters beyond its single title.",
    ),
]


def filtered_slack_highlights(slack_highlights: list[dict]) -> list[dict]:
    muted = load_muted_slack_channels()
    return [item for item in slack_highlights if item["channel"] not in muted]


def make_theme_cards(github_data: dict, linear_data: dict) -> list[dict]:
    top_repo_text = ", ".join(repo for repo, _ in github_data["top_pr_repos"][:3])
    top_linear_teams = ", ".join(
        linear_data["team_names"].get(team_key, team_key)
        for team_key, _ in linear_data["teams_updated"][:3]
    )
    return [
        {
            "title": "AI work is getting more structured",
            "body": (
                f"We saw that most clearly in {top_repo_text} and in the Forge RFC in Notion. "
                "This is moving from casual tool use into repo-owned workflows, review loops, and operating policy. "
                "Slack backed that up with ongoing discussion of Codex, Claude, Cursor Bugbot, and local LLM patterns."
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
                "We kept running into the same thread across tools: Datadog dashboards, SLO work, deploy-duration metrics, "
                "bot protection, Temporal monitors, and support-driven debugging. That story showed up in GitHub, Linear, Slack, and Notion."
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

    slack_stance = "Tracked channels refreshed from connector snapshots"
    notion_stance = "Tracked pages refreshed from connector snapshots"
    slack_summary_label = "Tracked channels + connector reads"
    slack_intro = "We built the Slack pass from tracked channels refreshed through connector reads. That gives us current coverage for the channels we care about most, but it's still deliberate sampling rather than a full workspace export."
    notion_intro = "The useful Notion pages this week carried live work. This slice was refreshed from tracked pages through connector fetches, so it reflects current doc state without pretending to be a workspace-wide crawl."

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
                link_text(f"{len(notion_highlights)} notable documents/pages", "#notion"),
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

    methodology = f"""
<ul class="method-list">
  <li>We pulled GitHub coverage from the Convergint org for May 4 through May 11, 2026, using repo lists plus PR and issue searches.</li>
  <li>We built the Linear slice from the 100 most recently updated issues per team, deduped into one sample of 1,445 issues, plus recent project records.</li>
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
      --bg: #f4efe4;
      --surface: rgba(255, 252, 245, 0.92);
      --surface-strong: #fffdf8;
      --ink: #17211d;
      --muted: #5f6d66;
      --accent: #0f7b72;
      --accent-2: #be6435;
      --accent-3: #697a2e;
      --line: #d7d0c2;
      --shadow: 0 24px 60px rgba(23, 33, 29, 0.08);
      --radius: 22px;
      --radius-sm: 14px;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(15, 123, 114, 0.10), transparent 34%),
        radial-gradient(circle at top right, rgba(190, 100, 53, 0.08), transparent 28%),
        linear-gradient(180deg, #f7f2e7 0%, #f2ebde 100%);
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
      background: linear-gradient(135deg, rgba(255, 252, 245, 0.95), rgba(246, 240, 230, 0.92));
      border: 1px solid rgba(255, 255, 255, 0.7);
      box-shadow: var(--shadow);
      border-radius: 32px;
      padding: 32px;
      position: relative;
      overflow: hidden;
    }}

    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -10% -50px auto;
      width: 380px;
      height: 220px;
      background: linear-gradient(135deg, rgba(15, 123, 114, 0.09), rgba(190, 100, 53, 0.08));
      filter: blur(10px);
      border-radius: 999px;
      transform: rotate(-8deg);
    }}

    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(15, 123, 114, 0.10);
      color: var(--accent);
      font-size: 13px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}

    h1, h2, h3, h4 {{
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      letter-spacing: -0.02em;
      margin: 0;
    }}

    h1 {{
      margin-top: 18px;
      font-size: clamp(2.5rem, 5vw, 4.4rem);
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
      border-radius: 24px;
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
      letter-spacing: 0.08em;
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
      border-radius: 18px;
      backdrop-filter: blur(18px);
      background: rgba(250, 246, 238, 0.84);
      border: 1px solid rgba(215, 208, 194, 0.9);
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}

    .sticky-nav a {{
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(23, 33, 29, 0.05);
      color: var(--ink);
      font-size: 0.92rem;
    }}

    section {{
      margin-top: 22px;
      background: var(--surface);
      border: 1px solid rgba(255, 255, 255, 0.85);
      box-shadow: var(--shadow);
      border-radius: var(--radius);
      padding: 24px;
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
      letter-spacing: 0.08em;
      font-size: 0.78rem;
    }}

    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
    }}

    .stat-card {{
      padding: 18px;
      border-radius: 18px;
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
      letter-spacing: 0.07em;
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
      border-radius: 18px;
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
      border-radius: 18px;
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
      letter-spacing: 0.08em;
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
      border-radius: 16px;
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
      border-radius: 18px;
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
      letter-spacing: 0.08em;
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
      border-radius: 999px;
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

      section,
      .hero {{
        padding: 18px;
      }}

      h1 {{
        max-width: none;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <div class="eyebrow">May 4 through May 11, 2026</div>
      <div class="hero-grid">
        <div class="hero-copy">
          <h1>Convergint weekly activity, stitched across tools.</h1>
          <p>
            We pulled GitHub, Linear, Slack, and Notion into one weekly readout because the individual tools only tell part of the story.
            The useful signal this week came from where they lined up: AI delivery work got more structured, reliability work kept surfacing,
            QA coverage kept getting more formal, and Notion carried real operating context instead of trailing behind the code.
          </p>
          <p>
            GitHub stayed broad but clustered, with <strong>{link_text(str(github_data["prs_created"]), report_page("github-prs-created.html"))}</strong> PRs opened and
            <strong>{link_text(str(github_data["prs_merged"]), report_page("github-prs-merged.html"))}</strong> merged. Linear added
            <strong>{link_text(str(linear_data["issues_updated"]), report_page("linear-issues-updated.html"))}</strong> sampled issue updates, led by
            <strong>{link_text(top_linear_team, linear_team_page(top_linear_team_key))}</strong> with <strong>{link_text(str(top_linear_team_count), linear_team_page(top_linear_team_key))}</strong> updates.
            Slack and Notion filled in the why, who, and what's changing underneath the raw counts.
          </p>
        </div>
        <aside class="hero-notes">
          <dl>
            <div>
              <dt>Most active GitHub repo by PR creation</dt>
              <dd>{link_text(github_top_repo, gh_pr_search_url(repo=github_top_repo))} ({link_text(str(github_top_repo_count), gh_pr_search_url(repo=github_top_repo))})</dd>
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
              <dd>May 11, 2026</dd>
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
        The issue stream told a tighter story and mostly looked like Forge planning work instead of a broad org-wide burst of new issues.
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
        GitHub and Linear carry most of the quantitative weight here.
        Slack and Notion tell us what people were coordinating around, which docs were shaping behavior, and where the work was getting more structured.
      </p>
    </section>
  </div>
  <script>
    const muteServerOrigin = {json.dumps(REPORT_SERVER_ORIGIN)};
    const muteButtons = document.querySelectorAll(".mute-button");
    const muteFeedback = document.getElementById("mute-feedback");
    const mutedCount = document.querySelector("[data-muted-count]");

    function showMuteFeedback(message, isError = false) {{
      if (!muteFeedback) return;
      muteFeedback.hidden = false;
      muteFeedback.textContent = message;
      muteFeedback.style.color = isError ? "#be6435" : "#0f7b72";
    }}

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
      background:
        radial-gradient(circle at top left, rgba(15, 123, 114, 0.10), transparent 34%),
        linear-gradient(180deg, #f7f2e7 0%, #f2ebde 100%);
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
      border-radius: 24px;
    }}

    .hero {{
      padding: 24px;
    }}

    .eyebrow {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.8rem;
    }}

    h1, h2, h3, h4 {{
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      letter-spacing: -0.02em;
      margin: 0;
    }}

    h1 {{
      margin-top: 12px;
      font-size: clamp(2rem, 4vw, 3.2rem);
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
      letter-spacing: 0.08em;
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


def main() -> None:
    validate_data_dir()
    OUTPUT_DIR.mkdir(exist_ok=True)
    github_data = github_summary()
    linear_data = linear_summary()
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
        "slack_highlights": slack_highlights,
        "muted_slack_channels": muted_slack_channels,
        "notion_highlights": notion_highlights,
        "themes": make_theme_cards(github_data, linear_data),
    }

    output_path("summary.json").write_text(json.dumps(summary, indent=2))
    output_path("index.html").write_text(build_html(summary))
    write_detail_pages()


if __name__ == "__main__":
    main()
