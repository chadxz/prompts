#!/bin/bash
# Setup symlinks for Claude Code configuration

set -euo pipefail

PROMPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./setup-common.sh
source "$PROMPTS_DIR/setup-common.sh"

setup_global_gitignore "$PROMPTS_DIR/.gitignore_global"
setup_git_clone_override "$PROMPTS_DIR/bin"
link_path "$PROMPTS_DIR/AGENTS.md" "$HOME/.claude/CLAUDE.md"
link_path_if_present "$PROMPTS_DIR/commands" "$HOME/.claude/commands"
link_path "$PROMPTS_DIR/skills" "$HOME/.claude/skills"
