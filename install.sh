#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.cursor/commands"

# shellcheck source=./setup-common.sh
source "$SCRIPT_DIR/setup-common.sh"

link_path_if_present "$SCRIPT_DIR/cursor-commands" "$TARGET_DIR"
ensure_bin_on_path "$SCRIPT_DIR/bin"
