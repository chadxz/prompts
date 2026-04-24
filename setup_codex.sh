#!/bin/bash
# Setup symlinks for Codex configuration

set -euo pipefail

PROMPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"

# shellcheck source=./setup-common.sh
source "$PROMPTS_DIR/setup-common.sh"

mkdir -p "$CODEX_DIR"
mkdir -p "$CODEX_DIR/skills"

link_path "$PROMPTS_DIR" "$CODEX_DIR/prompts"
link_path "$PROMPTS_DIR/AGENTS.md" "$CODEX_DIR/AGENTS.md"
link_path "$PROMPTS_DIR/skills" "$CODEX_DIR/skills/personal"

LEGACY_COMMANDS_DIR="$CODEX_DIR/skills/personal-commands"
if [[ -L "$LEGACY_COMMANDS_DIR" ]]; then
  rm "$LEGACY_COMMANDS_DIR"
  echo "Removed legacy symlink $LEGACY_COMMANDS_DIR"
elif [[ -e "$LEGACY_COMMANDS_DIR" ]]; then
  echo "Leaving existing $LEGACY_COMMANDS_DIR in place"
fi

ensure_bin_on_path "$PROMPTS_DIR/bin"

echo "Symlinked Codex prompts, global AGENTS.md, and personal skills."
