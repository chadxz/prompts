#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")

usage() {
  cat <<USAGE
Usage: $SCRIPT_NAME --start YYYY-MM-DD --end YYYY-MM-DD

Fetch GitHub activity for the authenticated user within the convergint organization
between the provided inclusive date range.

Options:
  --start YYYY-MM-DD   Start date (UTC) for activity window (required).
  --end YYYY-MM-DD     End date (UTC) for activity window (required).
  -h, --help           Show this help message and exit.
USAGE
}

START=""
END=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start)
      if [[ $# -lt 2 ]]; then
        echo "Error: --start requires a value" >&2
        exit 1
      fi
      START="$2"
      shift 2
      ;;
    --end)
      if [[ $# -lt 2 ]]; then
        echo "Error: --end requires a value" >&2
        exit 1
      fi
      END="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown argument '$1'" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$START" || -z "$END" ]]; then
  echo "Error: --start and --end are required" >&2
  usage
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh CLI is required but not found in PATH" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required but not found in PATH" >&2
  exit 1
fi

AUTHOR=$(gh api user --jq '.login')
if [[ -z "$AUTHOR" ]]; then
  echo "Error: Unable to determine authenticated GitHub user" >&2
  exit 1
fi

DATE_RANGE="${START}..${END}"

AUTHORED_PRS=$(
  gh search prs \
    --owner convergint \
    --author "$AUTHOR" \
    --created "$DATE_RANGE" \
    --json number,title,body,repository,state,createdAt,updatedAt,closedAt,url \
  | jq '[.[] | {
        number,
        title,
        body,
        state,
        createdAt,
        updatedAt,
        closedAt: (if .closedAt == "0001-01-01T00:00:00Z" then null else .closedAt end),
        url,
        repository: .repository.nameWithOwner
      }]'
)

REVIEWED_PRS=$(
  gh search prs \
    --owner convergint \
    --reviewed-by "$AUTHOR" \
    --updated "$DATE_RANGE" \
    --json number,title,body,repository,state,createdAt,updatedAt,closedAt,url \
  | jq '[.[] | {
        number,
        title,
        body,
        state,
        createdAt,
        updatedAt,
        closedAt: (if .closedAt == "0001-01-01T00:00:00Z" then null else .closedAt end),
        url,
        repository: .repository.nameWithOwner
      }]'
)

GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

jq -n \
  --arg author "$AUTHOR" \
  --arg start "$START" \
  --arg end "$END" \
  --arg generatedAt "$GENERATED_AT" \
  --argjson authored "$AUTHORED_PRS" \
  --argjson reviewed "$REVIEWED_PRS" \
  '{
    author: $author,
    generatedAt: $generatedAt,
    range: {
      start: $start,
      end: $end
    },
    authoredPullRequests: $authored,
    reviewedPullRequests: $reviewed
  }'
