#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: Required command not found: uv" >&2
  exit 1
fi

exec uv run "$SCRIPT_DIR/narrate.py" "$@"
