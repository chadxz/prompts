#!/bin/bash
# Setup symlinks for Claude Code configuration

PROMPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

ln -sf "$PROMPTS_DIR/AGENTS.md" ~/.claude/CLAUDE.md
ln -sf "$PROMPTS_DIR/commands" ~/.claude/commands
ln -sf "$PROMPTS_DIR/skills" ~/.claude/skills
