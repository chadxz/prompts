from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from report_config import DATA_DIR, ORG, WINDOW_END, WINDOW_START

GITHUB_REPO_LIMIT = 200
GITHUB_PR_LIMIT = 1000
GITHUB_ISSUE_LIMIT = 500
LINEAR_PROJECT_LIMIT = 50
LINEAR_TEAM_ISSUE_LIMIT = 100
LINEAR_TEAM_DUMPS_DIR = DATA_DIR / "linear_team_dumps"


def require_command(command: str) -> None:
    if shutil.which(command):
        return

    raise SystemExit(
        f"Missing required command: {command}\n"
        "Install it locally before running the fetch step again."
    )


def run_json_command(args: list[str]) -> list | dict:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or "no output captured"
        raise SystemExit(f"Command failed while populating data:\n$ {' '.join(args)}\n{details}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Command returned invalid JSON while populating data:\n$ {' '.join(args)}\n{exc}"
        ) from exc


def write_json(path: Path, payload: list | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def dedupe_linear_issues(team_issue_lists: Iterable[list[dict]]) -> list[dict]:
    combined = [issue for issues in team_issue_lists for issue in issues if isinstance(issue, dict)]
    combined.sort(
        key=lambda issue: (parse_dt(issue.get("updatedAt")), issue.get("identifier") or ""),
        reverse=True,
    )

    deduped: list[dict] = []
    seen: set[str] = set()
    for issue in combined:
        identifier = issue.get("id") or issue.get("identifier")
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        deduped.append(issue)

    return deduped


def github_repos() -> list[dict]:
    payload = run_json_command(
        [
            "gh",
            "repo",
            "list",
            ORG,
            "--limit",
            str(GITHUB_REPO_LIMIT),
            "--json",
            "nameWithOwner,description,isPrivate,pushedAt",
        ]
    )
    return payload if isinstance(payload, list) else []


def github_prs_created() -> list[dict]:
    payload = run_json_command(
        [
            "gh",
            "search",
            "prs",
            "--owner",
            ORG,
            "--archived=false",
            "--created",
            f"{WINDOW_START}..{WINDOW_END}",
            "--sort",
            "created",
            "--order",
            "desc",
            "--limit",
            str(GITHUB_PR_LIMIT),
            "--json",
            ("author,commentsCount,createdAt,isDraft,number,repository,state,title,updatedAt,url"),
        ]
    )
    return payload if isinstance(payload, list) else []


def github_prs_merged() -> list[dict]:
    payload = run_json_command(
        [
            "gh",
            "search",
            "prs",
            "--owner",
            ORG,
            "--archived=false",
            "--merged",
            "--merged-at",
            f"{WINDOW_START}..{WINDOW_END}",
            "--sort",
            "updated",
            "--order",
            "desc",
            "--limit",
            str(GITHUB_PR_LIMIT),
            "--json",
            (
                "author,closedAt,commentsCount,createdAt,isDraft,number,"
                "repository,state,title,updatedAt,url"
            ),
        ]
    )
    return payload if isinstance(payload, list) else []


def github_issues_created() -> list[dict]:
    payload = run_json_command(
        [
            "gh",
            "search",
            "issues",
            "--owner",
            ORG,
            "--archived=false",
            "--created",
            f"{WINDOW_START}..{WINDOW_END}",
            "--sort",
            "created",
            "--order",
            "desc",
            "--limit",
            str(GITHUB_ISSUE_LIMIT),
            "--json",
            "author,commentsCount,createdAt,labels,number,repository,state,title,updatedAt,url",
        ]
    )
    return payload if isinstance(payload, list) else []


def github_issues_closed() -> list[dict]:
    payload = run_json_command(
        [
            "gh",
            "search",
            "issues",
            "--owner",
            ORG,
            "--archived=false",
            "--state",
            "closed",
            "--closed",
            f"{WINDOW_START}..{WINDOW_END}",
            "--sort",
            "updated",
            "--order",
            "desc",
            "--limit",
            str(GITHUB_ISSUE_LIMIT),
            "--json",
            "author,closedAt,commentsCount,createdAt,labels,number,repository,state,title,updatedAt,url",
        ]
    )
    return payload if isinstance(payload, list) else []


def linear_teams() -> list[dict]:
    payload = run_json_command(["linctl", "team", "list", "--json"])
    return payload if isinstance(payload, list) else []


def linear_projects() -> list[dict]:
    payload = run_json_command(
        [
            "linctl",
            "project",
            "list",
            "--json",
            "--include-completed",
            "--limit",
            str(LINEAR_PROJECT_LIMIT),
            "--sort",
            "updated",
            "--newer-than",
            "1_month_ago",
        ]
    )
    return payload if isinstance(payload, list) else []


def linear_team_issues(team_key: str) -> list[dict]:
    payload = run_json_command(
        [
            "linctl",
            "issue",
            "list",
            "--team",
            team_key,
            "--sort",
            "updated",
            "--limit",
            str(LINEAR_TEAM_ISSUE_LIMIT),
            "--newer-than",
            "all_time",
            "--include-completed",
            "--json",
        ]
    )
    return payload if isinstance(payload, list) else []


def clear_linear_team_dumps() -> None:
    LINEAR_TEAM_DUMPS_DIR.mkdir(parents=True, exist_ok=True)
    for existing in LINEAR_TEAM_DUMPS_DIR.glob("*.json"):
        existing.unlink()


def populate_github_snapshots() -> dict[str, int]:
    repos = github_repos()
    prs_created = github_prs_created()
    prs_merged = github_prs_merged()
    issues_created = github_issues_created()
    issues_closed = github_issues_closed()

    write_json(DATA_DIR / "github_repos.json", repos)
    write_json(DATA_DIR / "github_prs_created.json", prs_created)
    write_json(DATA_DIR / "github_prs_merged.json", prs_merged)
    write_json(DATA_DIR / "github_issues_created.json", issues_created)
    write_json(DATA_DIR / "github_issues_closed.json", issues_closed)

    return {
        "repos": len(repos),
        "prs_created": len(prs_created),
        "prs_merged": len(prs_merged),
        "issues_created": len(issues_created),
        "issues_closed": len(issues_closed),
    }


def populate_linear_snapshots() -> dict[str, int]:
    teams = linear_teams()
    projects = linear_projects()

    clear_linear_team_dumps()
    team_dumps: list[list[dict]] = []
    for team in teams:
        team_key = team.get("key")
        if not team_key:
            continue
        issues = linear_team_issues(team_key)
        team_dumps.append(issues)
        write_json(LINEAR_TEAM_DUMPS_DIR / f"{team_key}.json", issues)

    deduped_issues = dedupe_linear_issues(team_dumps)

    write_json(DATA_DIR / "linear_teams.json", teams)
    write_json(DATA_DIR / "linear_projects_month.json", projects)
    write_json(DATA_DIR / "linear_issues_updated.json", deduped_issues)

    return {
        "teams": len(teams),
        "projects": len(projects),
        "team_dumps": len(team_dumps),
        "issues_updated": len(deduped_issues),
    }


def main() -> None:
    require_command("gh")
    require_command("linctl")
    DATA_DIR.mkdir(exist_ok=True)

    github_counts = populate_github_snapshots()
    linear_counts = populate_linear_snapshots()

    print(
        "Populated report snapshots for "
        f"{WINDOW_START} through {WINDOW_END}.\n"
        f"GitHub: {github_counts['repos']} repos, "
        f"{github_counts['prs_created']} PRs opened, "
        f"{github_counts['prs_merged']} PRs merged, "
        f"{github_counts['issues_created']} issues opened, "
        f"{github_counts['issues_closed']} issues closed.\n"
        f"Linear: {linear_counts['teams']} teams, "
        f"{linear_counts['projects']} projects, "
        f"{linear_counts['issues_updated']} deduped issues from "
        f"{linear_counts['team_dumps']} team dumps."
    )


if __name__ == "__main__":
    main()
