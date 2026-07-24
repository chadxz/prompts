#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURSOR_DIR="$HOME/.cursor"
COMMANDS_DIR="$CURSOR_DIR/commands"

# shellcheck source=./setup-common.sh
source "$SCRIPT_DIR/setup-common.sh"

setup_global_gitignore "$SCRIPT_DIR/.gitignore_global"
setup_git_clone_override "$SCRIPT_DIR/bin"
install_wt_stack "$SCRIPT_DIR"
link_path_if_present "$SCRIPT_DIR/cursor-commands" "$COMMANDS_DIR"
"$SCRIPT_DIR/bin/cursor-cli-config" install
