#!/bin/bash
# Setup symlinks for Codex configuration

set -euo pipefail

PROMPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"

mkdir -p "$CODEX_DIR"
mkdir -p "$CODEX_DIR/skills"

ln -sfn "$PROMPTS_DIR" "$CODEX_DIR/prompts"
ln -sfn "$PROMPTS_DIR/AGENTS.md" "$CODEX_DIR/AGENTS.md"
ln -sfn "$PROMPTS_DIR/skills" "$CODEX_DIR/skills/personal"
rm -rf "$CODEX_DIR/skills/personal-commands"

# Add bin/ to PATH in .zshrc if not already present
BIN_LINE="export PATH=\"$PROMPTS_DIR/bin:\$PATH\""
if ! grep -qF "$PROMPTS_DIR/bin" "$HOME/.zshrc" 2>/dev/null; then
    echo "" >> "$HOME/.zshrc"
    echo "# prompts repo bin" >> "$HOME/.zshrc"
    echo "$BIN_LINE" >> "$HOME/.zshrc"
    echo "Added $PROMPTS_DIR/bin to ~/.zshrc"
else
    echo "$PROMPTS_DIR/bin already in PATH"
fi

echo "Symlinked Codex prompts, global AGENTS.md, and personal skills."
