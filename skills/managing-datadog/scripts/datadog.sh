#!/usr/bin/env bash

set -euo pipefail

# This script manages Datadog dashboards, SLOs, and monitors - can push (create/update) or pull (download).
#
# Requirements:
#   jq - JSON processor (install via: brew install jq, apt-get install jq, etc.)
#   DD_API_KEY or DATADOG_API_KEY environment variable
#   DD_APP_KEY or DATADOG_APP_KEY environment variable
# Optional:
#   DD_SITE or DATADOG_SITE (defaults to us3.datadoghq.com)
#
# IMPORTANT: Use `op run` to inject credentials from 1Password:
#   op run -- ./datadog.sh dashboard push path/to/dashboard.json
#   op run -- ./datadog.sh slo push path/to/slo.json
#   op run -- ./datadog.sh monitor push path/to/monitor.json
#   op run -- ./datadog.sh dashboard pull <dashboard_id> [output_file.json]
#   op run -- ./datadog.sh slo pull <slo_id> [output_file.json]
#   op run -- ./datadog.sh monitor pull <monitor_id> [output_file.json]
#
# Usage examples:
#   op run -- ./datadog.sh dashboard push mulesoft-applications-overview.json
#   op run -- ./datadog.sh slo push mulesoft-api-availability-slo.json
#   op run -- ./datadog.sh monitor push mulesoft-api-availability-monitor.json
#   op run -- ./datadog.sh dashboard pull 24f-emr-yzt [output_file.json]
#   op run -- ./datadog.sh slo pull <slo_id> [output_file.json]
#   op run -- ./datadog.sh monitor pull <monitor_id> [output_file.json]

PROGRAM_NAME="$(basename "$0")"

usage() {
  cat <<EOF
Usage: $PROGRAM_NAME <resource_type> <command> [arguments...]

Resource Types:
  dashboard Manage Dashboards
  slo       Manage Service Level Objectives
  monitor   Manage Monitors

Commands:
  push <file.json>              Push (create or update) from JSON file
  pull <id> [output_file.json]  Pull (download) by ID
  list [query]                  List all resources (optionally filtered by query)

Options:
  -h, --help              Show this help message.

Examples:
  $PROGRAM_NAME dashboard push mulesoft-applications-overview.json
  $PROGRAM_NAME slo push mulesoft-api-availability-slo.json
  $PROGRAM_NAME monitor push mulesoft-api-availability-monitor.json
  $PROGRAM_NAME dashboard pull 24f-emr-yzt [output_file.json]
  $PROGRAM_NAME slo pull <slo_id> [output_file.json]
  $PROGRAM_NAME monitor pull <monitor_id> [output_file.json]

Notes:
  • jq is required (install via: brew install jq, apt-get install jq, etc.)
  • Use \`op run\` to inject DD_API_KEY/DD_APP_KEY from 1Password (recommended).
  • Alternatively, set DD_API_KEY/DD_APP_KEY (or DATADOG_* variants) in your environment.
  • Override the Datadog site with DD_SITE (defaults to us3.datadoghq.com).
EOF
}

cleanup() {
  if [ -n "${TMP_JSON:-}" ] && [ -f "$TMP_JSON" ]; then
    rm -f "$TMP_JSON"
  fi
}

TMP_JSON=""
trap cleanup EXIT

# Check for jq early to provide clear error message
if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required but not found." >&2
  echo "Please install jq:" >&2
  echo "  macOS:   brew install jq" >&2
  echo "  Ubuntu:  apt-get install jq" >&2
  echo "  Fedora:  dnf install jq" >&2
  echo "  Or visit: https://stedolan.github.io/jq/download/" >&2
  exit 1
fi

API_KEY="${DD_API_KEY:-${DATADOG_API_KEY:-}}"
APP_KEY="${DD_APP_KEY:-${DATADOG_APP_KEY:-}}"
SITE="${DD_SITE:-${DATADOG_SITE:-us3.datadoghq.com}}"

SITE="${SITE#https://}"
SITE="${SITE#api.}"
API_BASE_URL="https://api.${SITE}"

validate_credentials() {
  if [ -z "$API_KEY" ]; then
    echo "Error: DD_API_KEY (or DATADOG_API_KEY) environment variable is not set" >&2
    echo "Please set it using: export DD_API_KEY='your_api_key'" >&2
    exit 1
  fi

  if [ -z "$APP_KEY" ]; then
    echo "Error: DD_APP_KEY (or DATADOG_APP_KEY) environment variable is not set" >&2
    echo "Please set it using: export DD_APP_KEY='your_app_key'" >&2
    exit 1
  fi

  echo "Validating Datadog API credentials..."

  VALIDATE_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET \
    -H "DD-API-KEY: ${API_KEY}" \
    -H "DD-APPLICATION-KEY: ${APP_KEY}" \
    "${API_BASE_URL}/api/v1/validate")

  VALIDATE_HTTP_CODE=$(echo "$VALIDATE_RESPONSE" | tail -n1)
  VALIDATE_BODY=$(echo "$VALIDATE_RESPONSE" | sed '$d')

  if [ "$VALIDATE_HTTP_CODE" -ne 200 ]; then
    echo "❌ API key validation failed. HTTP status code: $VALIDATE_HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$VALIDATE_BODY" | jq '.' 2>/dev/null || echo "$VALIDATE_BODY" >&2
    echo "" >&2
    echo "Please check:" >&2
    echo "  1. Your API key is correct" >&2
    echo "  2. Your Application key is correct" >&2
    echo "  3. Your Application key has the required scopes" >&2
    exit 1
  fi

  VALID=$(echo "$VALIDATE_BODY" | jq -r '.valid')

  if [ "$VALID" != "true" ]; then
    echo "❌ API credentials are invalid" >&2
    echo "Response:" >&2
    echo "$VALIDATE_BODY" | jq '.' 2>/dev/null || echo "$VALIDATE_BODY" >&2
    exit 1
  fi

  echo "✅ API credentials validated successfully"
}

push_slo() {
  local SLO_JSON="$1"

  if [ ! -f "$SLO_JSON" ]; then
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    RELATIVE_JSON="${SCRIPT_DIR}/$SLO_JSON"
    if [ -f "$RELATIVE_JSON" ]; then
      SLO_JSON="$RELATIVE_JSON"
    fi
  fi

  if [ ! -f "$SLO_JSON" ]; then
    echo "Error: SLO JSON file not found at $SLO_JSON" >&2
    exit 1
  fi

  JSON_SLO_ID=$(jq -r '.id // empty' "$SLO_JSON" 2>/dev/null || echo "")
  REQUEST_JSON="$SLO_JSON"

  if [ -n "$JSON_SLO_ID" ] && [ "$JSON_SLO_ID" != "null" ]; then
    TMP_JSON=$(mktemp)
    jq 'del(.id)' "$SLO_JSON" > "$TMP_JSON"
    REQUEST_JSON="$TMP_JSON"
    HTTP_METHOD="PUT"
    API_ENDPOINT="${API_BASE_URL}/api/v1/slo/${JSON_SLO_ID}"
    ACTION_VERB="Updating"
  else
    HTTP_METHOD="POST"
    API_ENDPOINT="${API_BASE_URL}/api/v1/slo"
    ACTION_VERB="Creating"
  fi

  echo "${ACTION_VERB} SLO from ${SLO_JSON} to Datadog site ${SITE}..."

  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X "${HTTP_METHOD}" \
    -H "Content-Type: application/json" \
    -H "DD-API-KEY: ${API_KEY}" \
    -H "DD-APPLICATION-KEY: ${APP_KEY}" \
    -d @"${REQUEST_JSON}" \
    "${API_ENDPOINT}")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    SLO_ID=$(echo "$BODY" | jq -r '.data[0].id // .data.id // .id // empty' 2>/dev/null)
    if [ -z "${SLO_ID:-}" ] || [ "$SLO_ID" = "null" ]; then
      SLO_ID=$(echo "$BODY" | grep -o '"id":"[^\"]*"' | head -1 | cut -d'"' -f4 || echo "")
    fi
    echo "✅ SLO pushed successfully!"
    if [ -n "$SLO_ID" ]; then
      echo "📊 SLO ID: ${SLO_ID}"
      echo "🔗 View SLO: https://${SITE}/slo/${SLO_ID}"

      # If this was a CREATE (POST), automatically pull the SLO back to save the ID
      if [ "$HTTP_METHOD" = "POST" ]; then
        echo "📥 Pulling SLO back to save ID..."
        PULL_RESPONSE=$(curl -s -w "\n%{http_code}" \
          -X GET \
          -H "DD-API-KEY: ${API_KEY}" \
          -H "DD-APPLICATION-KEY: ${APP_KEY}" \
          "${API_BASE_URL}/api/v1/slo/${SLO_ID}")

        PULL_HTTP_CODE=$(echo "$PULL_RESPONSE" | tail -n1)
        PULL_BODY=$(echo "$PULL_RESPONSE" | sed '$d')

        if [ "$PULL_HTTP_CODE" -ge 200 ] && [ "$PULL_HTTP_CODE" -lt 300 ]; then
          # Extract inner SLO object from data wrapper if present
          SLO_DATA=$(echo "$PULL_BODY" | jq '.data // .' 2>/dev/null)
          echo "$SLO_DATA" | jq '.' > "$SLO_JSON"
          echo "✅ SLO ID saved to ${SLO_JSON}"
        else
          echo "⚠️  Warning: Failed to pull SLO back. HTTP status code: $PULL_HTTP_CODE" >&2
        fi
      fi
    fi
  else
    echo "❌ Failed to push SLO. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

list_slos() {
  local SEARCH_QUERY="${1:-}"

  echo "Listing SLOs from Datadog site ${SITE}..."

  if [ -n "$SEARCH_QUERY" ]; then
    RESPONSE=$(curl -s -w "\n%{http_code}" \
      -X GET \
      -H "DD-API-KEY: ${API_KEY}" \
      -H "DD-APPLICATION-KEY: ${APP_KEY}" \
      "${API_BASE_URL}/api/v1/slo?query=${SEARCH_QUERY}&limit=1000")
  else
    RESPONSE=$(curl -s -w "\n%{http_code}" \
      -X GET \
      -H "DD-API-KEY: ${API_KEY}" \
      -H "DD-APPLICATION-KEY: ${APP_KEY}" \
      "${API_BASE_URL}/api/v1/slo?limit=1000")
  fi

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo "$BODY" | jq -r '.data[] | "\(.id)|\(.name)"' | sort
  else
    echo "❌ Failed to list SLOs. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

pull_slo() {
  local SLO_ID="$1"
  local OUTPUT_FILE="${2:-}"

  if [ -z "$SLO_ID" ]; then
    echo "Error: SLO ID is required" >&2
    usage
    exit 1
  fi

  echo "Pulling SLO ${SLO_ID} from Datadog site ${SITE}..."

  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET \
    -H "DD-API-KEY: ${API_KEY}" \
    -H "DD-APPLICATION-KEY: ${APP_KEY}" \
    "${API_BASE_URL}/api/v1/slo/${SLO_ID}")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    # Extract inner SLO object from data wrapper (Datadog GET returns {"data": {...}, "error": null})
    SLO_DATA=$(echo "$BODY" | jq '.data // .' 2>/dev/null)
    if [ -n "$OUTPUT_FILE" ]; then
      echo "$SLO_DATA" | jq '.' > "$OUTPUT_FILE"
      echo "✅ SLO pulled successfully!"
      echo "📄 Saved to: ${OUTPUT_FILE}"
    else
      echo "$SLO_DATA" | jq '.'
    fi
  else
    echo "❌ Failed to pull SLO. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

push_monitor() {
  local MONITOR_JSON="$1"

  if [ ! -f "$MONITOR_JSON" ]; then
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    RELATIVE_JSON="${SCRIPT_DIR}/$MONITOR_JSON"
    if [ -f "$RELATIVE_JSON" ]; then
      MONITOR_JSON="$RELATIVE_JSON"
    fi
  fi

  if [ ! -f "$MONITOR_JSON" ]; then
    echo "Error: Monitor JSON file not found at $MONITOR_JSON" >&2
    exit 1
  fi

  JSON_MONITOR_ID=$(jq -r '.id // empty' "$MONITOR_JSON" 2>/dev/null || echo "")
  REQUEST_JSON="$MONITOR_JSON"

  if [ -n "$JSON_MONITOR_ID" ] && [ "$JSON_MONITOR_ID" != "null" ]; then
    TMP_JSON=$(mktemp)
    jq 'del(.id)' "$MONITOR_JSON" > "$TMP_JSON"
    REQUEST_JSON="$TMP_JSON"
    HTTP_METHOD="PUT"
    API_ENDPOINT="${API_BASE_URL}/api/v1/monitor/${JSON_MONITOR_ID}"
    ACTION_VERB="Updating"
  else
    HTTP_METHOD="POST"
    API_ENDPOINT="${API_BASE_URL}/api/v1/monitor"
    ACTION_VERB="Creating"
  fi

  echo "${ACTION_VERB} monitor from ${MONITOR_JSON} to Datadog site ${SITE}..."

  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X "${HTTP_METHOD}" \
    -H "Content-Type: application/json" \
    -H "DD-API-KEY: ${API_KEY}" \
    -H "DD-APPLICATION-KEY: ${APP_KEY}" \
    -d @"${REQUEST_JSON}" \
    "${API_ENDPOINT}")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    MONITOR_ID=$(echo "$BODY" | jq -r '.id // empty' 2>/dev/null)
    if [ -z "${MONITOR_ID:-}" ] || [ "$MONITOR_ID" = "null" ]; then
      MONITOR_ID=$(echo "$BODY" | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2 || echo "")
    fi
    echo "✅ Monitor pushed successfully!"
    if [ -n "$MONITOR_ID" ]; then
      echo "📊 Monitor ID: ${MONITOR_ID}"
      echo "🔗 View monitor: https://${SITE}/monitors/${MONITOR_ID}"

      # If this was a CREATE (POST), automatically pull the monitor back to save the ID
      if [ "$HTTP_METHOD" = "POST" ]; then
        echo "📥 Pulling monitor back to save ID..."
        PULL_RESPONSE=$(curl -s -w "\n%{http_code}" \
          -X GET \
          -H "DD-API-KEY: ${API_KEY}" \
          -H "DD-APPLICATION-KEY: ${APP_KEY}" \
          "${API_BASE_URL}/api/v1/monitor/${MONITOR_ID}")

        PULL_HTTP_CODE=$(echo "$PULL_RESPONSE" | tail -n1)
        PULL_BODY=$(echo "$PULL_RESPONSE" | sed '$d')

        if [ "$PULL_HTTP_CODE" -ge 200 ] && [ "$PULL_HTTP_CODE" -lt 300 ]; then
          echo "$PULL_BODY" | jq '.' > "$MONITOR_JSON"
          echo "✅ Monitor ID saved to ${MONITOR_JSON}"
        else
          echo "⚠️  Warning: Failed to pull monitor back. HTTP status code: $PULL_HTTP_CODE" >&2
        fi
      fi
    fi
  else
    echo "❌ Failed to push monitor. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

list_monitors() {
  local SEARCH_QUERY="${1:-}"

  echo "Listing monitors from Datadog site ${SITE}..."

  if [ -n "$SEARCH_QUERY" ]; then
    RESPONSE=$(curl -s -w "\n%{http_code}" \
      -X GET \
      -H "DD-API-KEY: ${API_KEY}" \
      -H "DD-APPLICATION-KEY: ${APP_KEY}" \
      "${API_BASE_URL}/api/v1/monitor?name=${SEARCH_QUERY}")
  else
    RESPONSE=$(curl -s -w "\n%{http_code}" \
      -X GET \
      -H "DD-API-KEY: ${API_KEY}" \
      -H "DD-APPLICATION-KEY: ${APP_KEY}" \
      "${API_BASE_URL}/api/v1/monitor")
  fi

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo "$BODY" | jq -r '.[] | "\(.id)|\(.name)"' | sort
  else
    echo "❌ Failed to list monitors. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

pull_monitor() {
  local MONITOR_ID="$1"
  local OUTPUT_FILE="${2:-}"

  if [ -z "$MONITOR_ID" ]; then
    echo "Error: Monitor ID is required" >&2
    usage
    exit 1
  fi

  echo "Pulling monitor ${MONITOR_ID} from Datadog site ${SITE}..."

  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET \
    -H "DD-API-KEY: ${API_KEY}" \
    -H "DD-APPLICATION-KEY: ${APP_KEY}" \
    "${API_BASE_URL}/api/v1/monitor/${MONITOR_ID}")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    if [ -n "$OUTPUT_FILE" ]; then
      echo "$BODY" | jq '.' > "$OUTPUT_FILE"
      echo "✅ Monitor pulled successfully!"
      echo "📄 Saved to: ${OUTPUT_FILE}"
    else
      echo "$BODY" | jq '.'
    fi
  else
    echo "❌ Failed to pull monitor. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

push_dashboard() {
  local DASHBOARD_JSON="$1"

  if [ ! -f "$DASHBOARD_JSON" ]; then
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    RELATIVE_JSON="${SCRIPT_DIR}/$DASHBOARD_JSON"
    if [ -f "$RELATIVE_JSON" ]; then
      DASHBOARD_JSON="$RELATIVE_JSON"
    fi
  fi

  if [ ! -f "$DASHBOARD_JSON" ]; then
    echo "Error: Dashboard JSON file not found at $DASHBOARD_JSON" >&2
    exit 1
  fi

  JSON_DASHBOARD_ID=$(jq -r '.id // empty' "$DASHBOARD_JSON" 2>/dev/null || echo "")
  REQUEST_JSON="$DASHBOARD_JSON"

  if [ -n "$JSON_DASHBOARD_ID" ] && [ "$JSON_DASHBOARD_ID" != "null" ]; then
    TMP_JSON=$(mktemp)
    jq 'del(.id)' "$DASHBOARD_JSON" > "$TMP_JSON"
    REQUEST_JSON="$TMP_JSON"
    HTTP_METHOD="PUT"
    API_ENDPOINT="${API_BASE_URL}/api/v1/dashboard/${JSON_DASHBOARD_ID}"
    ACTION_VERB="Updating"
  else
    HTTP_METHOD="POST"
    API_ENDPOINT="${API_BASE_URL}/api/v1/dashboard"
    ACTION_VERB="Creating"
  fi

  echo "${ACTION_VERB} dashboard from ${DASHBOARD_JSON} to Datadog site ${SITE}..."

  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X "${HTTP_METHOD}" \
    -H "Content-Type: application/json" \
    -H "DD-API-KEY: ${API_KEY}" \
    -H "DD-APPLICATION-KEY: ${APP_KEY}" \
    -d @"${REQUEST_JSON}" \
    "${API_ENDPOINT}")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    DASHBOARD_ID=$(echo "$BODY" | jq -r '.id // empty')
    if [ -z "${DASHBOARD_ID:-}" ] || [ "$DASHBOARD_ID" = "null" ]; then
      DASHBOARD_ID=$(echo "$BODY" | grep -o '"id":"[^\"]*"' | head -1 | cut -d'"' -f4 || echo "")
    fi
    echo "✅ Dashboard pushed successfully!"
    if [ -n "$DASHBOARD_ID" ]; then
      echo "📊 Dashboard ID: ${DASHBOARD_ID}"
      echo "🔗 View dashboard: https://${SITE}/dashboard/${DASHBOARD_ID}"

      # If this was a CREATE (POST), automatically pull the dashboard back to save the ID
      if [ "$HTTP_METHOD" = "POST" ]; then
        echo "📥 Pulling dashboard back to save ID..."
        PULL_RESPONSE=$(curl -s -w "\n%{http_code}" \
          -X GET \
          -H "DD-API-KEY: ${API_KEY}" \
          -H "DD-APPLICATION-KEY: ${APP_KEY}" \
          "${API_BASE_URL}/api/v1/dashboard/${DASHBOARD_ID}")

        PULL_HTTP_CODE=$(echo "$PULL_RESPONSE" | tail -n1)
        PULL_BODY=$(echo "$PULL_RESPONSE" | sed '$d')

        if [ "$PULL_HTTP_CODE" -ge 200 ] && [ "$PULL_HTTP_CODE" -lt 300 ]; then
          echo "$PULL_BODY" | jq '.' > "$DASHBOARD_JSON"
          echo "✅ Dashboard ID saved to ${DASHBOARD_JSON}"
        else
          echo "⚠️  Warning: Failed to pull dashboard back. HTTP status code: $PULL_HTTP_CODE" >&2
        fi
      fi
    fi
  else
    echo "❌ Failed to push dashboard. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

list_dashboards() {
  local SEARCH_QUERY="${1:-}"

  echo "Listing dashboards from Datadog site ${SITE}..."

  if [ -n "$SEARCH_QUERY" ]; then
    RESPONSE=$(curl -s -w "\n%{http_code}" \
      -X GET \
      -H "DD-API-KEY: ${API_KEY}" \
      -H "DD-APPLICATION-KEY: ${APP_KEY}" \
      "${API_BASE_URL}/api/v1/dashboard?query=${SEARCH_QUERY}")
  else
    RESPONSE=$(curl -s -w "\n%{http_code}" \
      -X GET \
      -H "DD-API-KEY: ${API_KEY}" \
      -H "DD-APPLICATION-KEY: ${APP_KEY}" \
      "${API_BASE_URL}/api/v1/dashboard")
  fi

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo "$BODY" | jq -r '.dashboards[]? | "\(.id)|\(.title)"' | sort
  else
    echo "❌ Failed to list dashboards. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

pull_dashboard() {
  local DASHBOARD_ID="$1"
  local OUTPUT_FILE="${2:-}"

  if [ -z "$DASHBOARD_ID" ]; then
    echo "Error: Dashboard ID is required" >&2
    usage
    exit 1
  fi

  echo "Pulling dashboard ${DASHBOARD_ID} from Datadog site ${SITE}..."

  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET \
    -H "DD-API-KEY: ${API_KEY}" \
    -H "DD-APPLICATION-KEY: ${APP_KEY}" \
    "${API_BASE_URL}/api/v1/dashboard/${DASHBOARD_ID}")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    if [ -n "$OUTPUT_FILE" ]; then
      echo "$BODY" | jq '.' > "$OUTPUT_FILE"
      echo "✅ Dashboard pulled successfully!"
      echo "📄 Saved to: ${OUTPUT_FILE}"
    else
      echo "$BODY" | jq '.'
    fi
  else
    echo "❌ Failed to pull dashboard. HTTP status code: $HTTP_CODE" >&2
    echo "Response:" >&2
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY" >&2
    exit 1
  fi
}

# Main command handling
if [ "$#" -eq 0 ]; then
  usage
  exit 1
fi

RESOURCE_TYPE="$1"
shift

case "$RESOURCE_TYPE" in
  dashboard)
    if [ "$#" -eq 0 ]; then
      echo "Error: command is required" >&2
      usage
      exit 1
    fi
    COMMAND="$1"
    shift
    case "$COMMAND" in
      push)
        if [ "$#" -eq 0 ]; then
          echo "Error: Dashboard JSON path is required" >&2
          usage
          exit 1
        fi
        validate_credentials
        push_dashboard "$1"
        ;;
      pull)
        if [ "$#" -eq 0 ]; then
          echo "Error: Dashboard ID is required" >&2
          usage
          exit 1
        fi
        validate_credentials
        pull_dashboard "$1" "${2:-}"
        ;;
      list)
        validate_credentials
        list_dashboards "${1:-}"
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Error: Unknown command '$COMMAND'" >&2
        usage
        exit 1
        ;;
    esac
    ;;
  slo)
    if [ "$#" -eq 0 ]; then
      echo "Error: command is required" >&2
      usage
      exit 1
    fi
    COMMAND="$1"
    shift
    case "$COMMAND" in
      push)
        if [ "$#" -eq 0 ]; then
          echo "Error: SLO JSON path is required" >&2
          usage
          exit 1
        fi
        validate_credentials
        push_slo "$1"
        ;;
      pull)
        if [ "$#" -eq 0 ]; then
          echo "Error: SLO ID is required" >&2
          usage
          exit 1
        fi
        validate_credentials
        pull_slo "$1" "${2:-}"
        ;;
      list)
        validate_credentials
        list_slos "${1:-}"
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Error: Unknown command '$COMMAND'" >&2
        usage
        exit 1
        ;;
    esac
    ;;
  monitor)
    if [ "$#" -eq 0 ]; then
      echo "Error: command is required" >&2
      usage
      exit 1
    fi
    COMMAND="$1"
    shift
    case "$COMMAND" in
      push)
        if [ "$#" -eq 0 ]; then
          echo "Error: Monitor JSON path is required" >&2
          usage
          exit 1
        fi
        validate_credentials
        push_monitor "$1"
        ;;
      pull)
        if [ "$#" -eq 0 ]; then
          echo "Error: Monitor ID is required" >&2
          usage
          exit 1
        fi
        validate_credentials
        pull_monitor "$1" "${2:-}"
        ;;
      list)
        validate_credentials
        list_monitors "${1:-}"
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Error: Unknown command '$COMMAND'" >&2
        usage
        exit 1
        ;;
    esac
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    echo "Error: Unknown resource type '$RESOURCE_TYPE'" >&2
    echo "Valid resource types: dashboard, slo, monitor" >&2
    usage
    exit 1
    ;;
esac

